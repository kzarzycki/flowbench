"""Driver contract, offline. We don't drive a live agent here (Task 1 + Task 7
cover that); we assert the interface contract and the pure transcript helpers."""

from pathlib import Path

from flowbench.runner.driver import AgentDriver, OmnigentDriver, TurnResult, any_child_busy
from flowbench.transcript import dedup_items, is_control_message, last_assistant_text


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


async def test_send_retries_undelivered_injection(tmp_path, monkeypatch):
    # runner_error "message was not delivered" = the inject never reached the
    # agent (busy terminal behind a lying idle) — re-sending is safe and required
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    outcomes = [
        TurnResult("failed", "", False),
        TurnResult("idle", "the plan is complete", False),
    ]
    sent = []

    async def fake_send_once(text):
        sent.append(text)
        return outcomes.pop(0)

    async def undelivered():
        return True

    d._send_once = fake_send_once
    d._injection_undelivered = undelivered
    result = await d.send("go on")
    assert result.status == "idle"
    assert sent == ["go on", "go on"]  # same text re-sent once


async def test_send_does_not_retry_delivered_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    sent = []

    async def fake_send_once(text):
        sent.append(text)
        return TurnResult("failed", "", False)

    async def delivered():
        return False  # a real failure, not an undelivered inject

    d._send_once = fake_send_once
    d._injection_undelivered = delivered
    result = await d.send("go on")
    assert result.status == "failed"
    assert sent == ["go on"]  # no blind retry


async def test_capture_session_includes_context_tokens(tmp_path):
    # cost signal: final context size from session labels lands in the capture
    class _FakeResp:
        def json(self):
            return {"labels": {"omnigent.last_context_tokens": "42072"}}

    class _FakeHttp:
        async def get(self, _url):
            return _FakeResp()

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = _FakeChat(["idle"])
    d._http = _FakeHttp()
    assert await d._context_tokens() == 42072


async def test_context_tokens_none_when_label_missing(tmp_path):
    class _FakeResp:
        def json(self):
            return {"labels": {}}

    class _FakeHttp:
        async def get(self, _url):
            return _FakeResp()

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = _FakeChat(["idle"])
    d._http = _FakeHttp()
    assert await d._context_tokens() is None


class _StallChat(_FakeChat):
    """Always running; refresh() returns a session snapshot with the stall signals."""

    def __init__(self, *, pending=0, beats=None):
        super().__init__(["running"])
        self.pending = pending
        self._beats = list(beats or [1])

    async def refresh(self):
        from types import SimpleNamespace

        await super().refresh()
        beat = self._beats.pop(0) if len(self._beats) > 1 else self._beats[0]
        return SimpleNamespace(pending_elicitations_count=self.pending, updated_at=beat)


async def test_pending_elicitation_stalls_the_turn_at_once(tmp_path, monkeypatch):
    # todo-app-001: a permission prompt nobody could answer sat until the turn cap
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    d = _settle_driver(tmp_path, _StallChat(pending=1), [[]])
    d._pane_tail = _pane("❯ Allow Bash(rm -rf build)? (y/n)")
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == ("stalled", "elicitation")
    assert "Allow Bash" in result.pane_tail


async def test_frozen_heartbeat_stalls_after_stall_s(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    d = _settle_driver(tmp_path, _StallChat(beats=[7]), [[]])
    d.stall_s = 0.05
    d._pane_tail = _pane(None)
    result = await d.send("build it")
    assert (result.status, result.stall_reason, result.pane_tail) == (
        "stalled",
        "no_progress",
        None,
    )


async def test_moving_heartbeat_is_not_a_stall(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", _instant_sleep)
    import itertools

    chat = _StallChat()
    chat._beats = itertools.count()  # every refresh a new updated_at
    chat.refresh = _counting_refresh(chat)
    d = _settle_driver(tmp_path, chat, [[]])
    d.stall_s = 0.05
    d.turn_timeout_s = 0.2
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == ("running", None)


def _counting_refresh(chat):
    async def refresh():
        from types import SimpleNamespace

        chat.status = "running"
        return SimpleNamespace(pending_elicitations_count=0, updated_at=next(chat._beats))

    return refresh


def _pane(text):
    async def _tail(lines=40):
        return text

    return _tail


async def test_pane_tail_is_best_effort(tmp_path):
    from types import SimpleNamespace

    class _Http:
        async def get(self, url):
            raise OSError("runner offline")

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_x")
    d._http = _Http()
    assert await d._pane_tail() is None


async def test_pane_tail_captures_tmux(tmp_path, monkeypatch):
    from types import SimpleNamespace

    class _Resp:
        def json(self):
            return {
                "data": [
                    {"type": "environment", "metadata": {}},
                    {"type": "terminal", "metadata": {"tmux_socket": "/s", "tmux_target": "t:0"}},
                ]
            }

    class _Http:
        async def get(self, url):
            return _Resp()

    class _Proc:
        async def communicate(self):
            return ("line1\nline2\n❯ waiting\n".encode(), b"")

    argv = []

    async def fake_exec(*a, **kw):
        argv.extend(a)
        return _Proc()

    monkeypatch.setattr("flowbench.runner.driver.asyncio.create_subprocess_exec", fake_exec)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_x")
    d._http = _Http()
    assert await d._pane_tail(lines=2) == "line2\n❯ waiting"
    assert argv[:4] == ["tmux", "-S", "/s", "capture-pane"]


async def test_pane_tail_gives_up_on_a_wedged_tmux(tmp_path, monkeypatch):
    # the watchdog must never itself hang: a tmux server that never answers -> None
    from types import SimpleNamespace

    class _Resp:
        def json(self):
            return {
                "data": [
                    {"type": "terminal", "metadata": {"tmux_socket": "/s", "tmux_target": "t"}}
                ]
            }

    class _Http:
        async def get(self, url):
            return _Resp()

    async def never(meta):
        raise AssertionError("wait_for must have cancelled this")  # pragma: no cover

    async def instant_wait_for(coro, timeout):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr("flowbench.runner.driver.asyncio.wait_for", instant_wait_for)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_x")
    d._http = _Http()
    d._capture_pane = never
    assert await d._pane_tail() is None
