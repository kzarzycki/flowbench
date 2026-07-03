"""Driver contract, offline. We don't drive a live agent here (Task 1 + Task 7
cover that); we assert the interface contract and the pure transcript helpers."""

from pathlib import Path

from flowbench.runner.driver import (
    AgentDriver,
    OmnigentDriver,
    TurnResult,
    any_child_busy,
    dedup_items,
    is_control_message,
    last_assistant_text,
)


def test_omnigent_driver_satisfies_interface():
    d = OmnigentDriver(run_dir=Path("/tmp/x"), artifact_name="account_summary.md")
    assert isinstance(d, AgentDriver)
    for m in ("start", "send", "capture_session", "artifact_path", "close"):
        assert hasattr(d, m)


def test_last_assistant_text_picks_latest():
    items = [
        {"type": "message", "role": "user", "content": "hi"},
        {"type": "message", "role": "assistant", "content": [{"type": "text", "text": "first"}]},
        {"type": "function_call", "name": "Write"},
        {"type": "message", "role": "assistant", "content": [{"type": "text", "text": "second"}]},
    ]
    assert last_assistant_text(items) == "second"


def test_last_assistant_text_empty_when_none():
    assert last_assistant_text([{"type": "message", "role": "user", "content": "hi"}]) == ""


async def test_close_is_idempotent():
    d = OmnigentDriver(run_dir=Path("/tmp/x"), artifact_name="a.md")
    await d.close()
    await d.close()  # must not raise
    assert d._closed is True


def test_artifact_path_none_when_missing(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="account_summary.md")
    assert d.artifact_path() is None
    (tmp_path / "account_summary.md").write_text("hi")
    assert d.artifact_path() == tmp_path / "account_summary.md"


def test_conversation_url_built_from_captured_events(tmp_path):
    # the conv id is scraped from streamed events; the URL is the omnigent UI route
    # a human opens to browse + resume the (still-alive) SUT session.
    d = OmnigentDriver(
        run_dir=tmp_path, artifact_name="tasks.json", server_url="http://127.0.0.1:6767"
    )
    assert d.conversation_url() is None  # nothing captured yet
    d._captured = [
        {"__type__": "SessionUsageEvent"},
        {"__type__": "OutputTextDeltaEvent", "conversation_id": "conv_abc123"},
    ]
    assert d.conversation_url() == "http://127.0.0.1:6767/c/conv_abc123"


def test_turn_result_shape():
    r = TurnResult(status="idle", assistant_text="done", artifact_exists=True)
    assert (r.status, r.assistant_text, r.artifact_exists) == ("idle", "done", True)


# --- bug 1 (doubled messages) + bug 3-adjacent (control injections) -----------


def test_is_control_message_flags_task_notifications():
    assert is_control_message("<task-notification>sub-agent done</task-notification>")
    assert is_control_message("   <task-notification> with leading space")
    assert not is_control_message("a normal user reply")
    assert not is_control_message("the agent mentioned <task-notification> mid-sentence")


def test_dedup_items_collapses_omnigent_doubled_messages():
    # bug 1: omnigent records each injected message twice; the persisted transcript
    # must show it ONCE.
    items = [
        {"type": "message", "role": "user", "content": "build a todo app"},
        {"type": "message", "role": "user", "content": "build a todo app"},  # echo
        {"type": "message", "role": "assistant", "content": [{"type": "text", "text": "on it"}]},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "on it"}],
        },  # echo
    ]
    out = dedup_items(items)
    assert [(_role(i), _text(i)) for i in out] == [
        ("user", "build a todo app"),
        ("assistant", "on it"),
    ]


def test_dedup_items_keeps_a_genuine_repeat_separated_by_other_party():
    # a real "Continue." after the agent spoke is NOT a duplicate — only adjacent
    # same-(role,text) collapse.
    items = [
        {"type": "message", "role": "user", "content": "Continue."},
        {"type": "message", "role": "assistant", "content": "working..."},
        {"type": "message", "role": "user", "content": "Continue."},
    ]
    out = dedup_items(items)
    assert [_text(i) for i in out] == ["Continue.", "working...", "Continue."]


def test_dedup_items_drops_task_notifications_but_keeps_non_messages():
    items = [
        {"type": "message", "role": "user", "content": "<task-notification>x</task-notification>"},
        {"type": "function_call", "name": "Write"},
        {"type": "message", "role": "assistant", "content": "real reply"},
    ]
    out = dedup_items(items)
    assert {i.get("type") for i in out} == {"function_call", "message"}
    assert [_text(i) for i in out if i.get("type") == "message"] == ["real reply"]


def _child_ev(cid, busy):
    return {
        "__type__": "SessionChildSessionUpdatedEvent",
        "child_session_id": cid,
        "child": {"id": cid, "busy": busy},
    }


def test_any_child_busy_tracks_latest_per_child_state():
    # busy while a sub-agent runs ...
    assert any_child_busy([_child_ev("c1", True)]) is True
    # ... not busy once its latest update clears (a later event wins)
    assert any_child_busy([_child_ev("c1", True), _child_ev("c1", False)]) is False
    # one of several children still busy => busy
    assert any_child_busy([_child_ev("c1", False), _child_ev("c2", True)]) is True
    # non-child events are ignored
    assert any_child_busy([{"__type__": "SessionUsageEvent"}]) is False
    assert any_child_busy([]) is False


def _role(it):
    return it.get("role", "")


def _text(it):
    c = it.get("content")
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") for p in c if isinstance(p, dict))


# --- send() settle: idle observed before the reply item lands ---------------


class _FakeChat:
    """Status sequence pops once per refresh(), then stays on the last value."""

    session_id = "conv_test"

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.status = None

    async def refresh(self):
        if len(self._statuses) > 1:
            self.status = self._statuses.pop(0)
        else:
            self.status = self._statuses[0]

    def send(self, text):
        async def _gen():
            return
            yield  # pragma: no cover

        return _gen()


class _FakeSessions:
    """Item batches pop once per list_items(), then stay on the last batch."""

    def __init__(self, batches):
        self._batches = list(batches)

    async def list_items(self, session_id, order, limit):
        if len(self._batches) > 1:
            return self._batches.pop(0)
        return self._batches[0]


def _settle_driver(tmp_path, chat, batches):
    from types import SimpleNamespace

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d.settle_timeout_s = 1.0
    d.settle_poll_s = 0.01
    d._chat = chat
    d._client = SimpleNamespace(sessions=_FakeSessions(batches))
    return d


_USER = {"type": "message", "role": "user", "content": "grade these plans"}
_REPLY = {"type": "message", "role": "assistant", "content": "WINNER: B"}


async def test_send_settles_until_new_assistant_message(tmp_path, monkeypatch):
    # live-001: judge status read idle before the runner picked the turn up ->
    # empty verdict. send() must keep polling until a NEW assistant message lands.
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    chat = _FakeChat(["running", "idle"] * 10)  # every _wait_idle sees running->idle (fast path)
    # batches consumed in call order: n_before probe, post-wait fetch, settle polls
    d = _settle_driver(tmp_path, chat, [[], [_USER], [_USER], [_USER, _REPLY]])
    result = await d.send("grade these plans")
    assert result.status == "idle"
    assert result.assistant_text == "WINNER: B"


async def test_send_settle_expiry_is_a_timeout_not_a_stale_idle(tmp_path, monkeypatch):
    # todo-003: settle expired while the agent was still mid-turn behind a lying
    # idle; the old code returned idle+stale text, the loop injected into a busy
    # terminal and the run died. Expiry must read as an unfinished turn.
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    chat = _FakeChat(["running", "idle"] * 10)  # every _wait_idle sees running->idle (fast path)
    d = _settle_driver(tmp_path, chat, [[], [_USER]])  # reply never lands
    d.settle_timeout_s = 0.05
    result = await d.send("grade these plans")
    assert result.status == "timeout"


async def _instant_sleep(_secs):
    return None


async def test_read_retry_survives_transient_errors(tmp_path, monkeypatch):
    # a single ReadError during polling killed a live run; reads are idempotent
    import httpx

    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ReadError("boom")
        return "ok"

    assert await d._read_retry(flaky) == "ok"
    assert calls["n"] == 3

    async def always_fails():
        raise httpx.ReadError("down")

    import pytest as _pytest

    with _pytest.raises(httpx.ReadError):
        await d._read_retry(always_fails)
