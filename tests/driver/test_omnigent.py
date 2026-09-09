"""Driver contract, offline. We don't drive a live agent here (Task 1 + Task 7
cover that); we assert the interface contract and the pure transcript helpers."""

import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from flowbench.driver import AgentDriver, OmnigentDriver, TurnResult
from flowbench.transcript import dedup_items, is_control_message, last_assistant_text
from flowbench.types import TurnStatus


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
    r = TurnResult(status=TurnStatus.IDLE, assistant_text="done", artifact_exists=True)
    assert (r.status, r.assistant_text, r.artifact_exists) == (TurnStatus.IDLE, "done", True)


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


def _role(it):
    return it.get("role", "")


def _text(it):
    c = it.get("content")
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") for p in c if isinstance(p, dict))


# --- send() settle: idle observed before the reply item lands ---------------


class _FakeChat:
    """Status sequence pops once per snapshot(), then stays on the last value.
    Stands in for the driver's raw `GET /v1/sessions/{id}` poll."""

    session_id = "conv_test"

    def __init__(self, statuses, *, pending=(), beats=(1,)):
        self._statuses = list(statuses)
        self._beats = iter(beats)  # exhausted -> last value repeats
        self._last_beat = None
        self.pending = list(pending)
        self.busy_children = []  # updated_at of each busy sub-agent (see _snapshot)
        self.status = None

    async def snapshot(self):
        if len(self._statuses) > 1:
            self.status = self._statuses.pop(0)
        else:
            self.status = self._statuses[0]
        self._last_beat = next(self._beats, self._last_beat)
        return {
            "status": self.status,
            "updated_at": self._last_beat,
            "pending_elicitations": self.pending,
            "busy_children": list(self.busy_children),
        }

    def send(self, text):
        async def _gen():
            return
            yield  # pragma: no cover

        return _gen()


class _FakeSessions:
    """Item batches pop once per list_items(), then stay on the last batch."""

    def __init__(self, batches):
        self._batches = list(batches)

    async def list_items(self, session_id, order, limit, after=None):
        if len(self._batches) > 1:
            return self._batches.pop(0)
        return self._batches[0]


def _settle_driver(tmp_path, chat, batches):
    from types import SimpleNamespace

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d.settle_timeout_s = 1.0
    d.settle_poll_s = 0.01
    d._chat = chat
    d._snapshot = chat.snapshot
    d._client = SimpleNamespace(sessions=_FakeSessions(batches))
    return d


_USER = {"type": "message", "role": "user", "content": "grade these plans"}
_REPLY = {"type": "message", "role": "assistant", "content": "WINNER: B"}


async def test_send_settles_until_new_assistant_message(tmp_path, monkeypatch):
    # live-001: judge status read idle before the runner picked the turn up ->
    # empty verdict. send() must keep polling until a NEW assistant message lands.
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    # server statuses fed to _snapshot, not driver outputs
    chat = _FakeChat(
        [TurnStatus.RUNNING, TurnStatus.IDLE] * 10
    )  # every _wait_idle sees running->idle (fast path)
    # batches consumed in call order: n_before probe, post-wait fetch, settle polls
    d = _settle_driver(tmp_path, chat, [[], [_USER], [_USER], [_USER, _REPLY]])
    result = await d.send("grade these plans")
    assert result.status == TurnStatus.IDLE
    assert result.assistant_text == "WINNER: B"


async def test_send_settle_expiry_is_a_timeout_not_a_stale_idle(tmp_path, monkeypatch):
    # todo-003: settle expired while the agent was still mid-turn behind a lying
    # idle; the old code returned idle+stale text, the loop injected into a busy
    # terminal and the run died. Expiry must read as an unfinished turn.
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    # server statuses fed to _snapshot, not driver outputs
    chat = _FakeChat(
        [TurnStatus.RUNNING, TurnStatus.IDLE] * 10
    )  # every _wait_idle sees running->idle (fast path)
    d = _settle_driver(tmp_path, chat, [[], [_USER]])  # reply never lands
    d.settle_timeout_s = 0.05
    result = await d.send("grade these plans")
    assert result.status == TurnStatus.TIMEOUT


async def _instant_sleep(_secs):
    return None


async def test_read_retry_survives_transient_errors(tmp_path, monkeypatch):
    # a single ReadError during polling killed a live run; reads are idempotent
    import httpx

    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
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
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    outcomes = [
        TurnResult(TurnStatus.FAILED, "", False),
        TurnResult(TurnStatus.IDLE, "the plan is complete", False),
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
    assert result.status == TurnStatus.IDLE
    assert sent == ["go on", "go on"]  # same text re-sent once


async def test_send_does_not_retry_delivered_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    sent = []

    async def fake_send_once(text):
        sent.append(text)
        return TurnResult(TurnStatus.FAILED, "", False)

    async def delivered():
        return False  # a real failure, not an undelivered inject

    d._send_once = fake_send_once
    d._injection_undelivered = delivered
    result = await d.send("go on")
    assert result.status == TurnStatus.FAILED
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
    d._chat = _FakeChat([TurnStatus.IDLE])
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
    d._chat = _FakeChat([TurnStatus.IDLE])
    d._http = _FakeHttp()
    assert await d._context_tokens() is None


async def test_pending_elicitation_stalls_the_turn_at_once(tmp_path, monkeypatch):
    # todo-app-001: a permission prompt nobody could answer sat until the turn cap
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    chat = _FakeChat([TurnStatus.RUNNING], pending=[{"id": "elicit_1"}])
    d = _settle_driver(tmp_path, chat, [[]])
    d._pane_tail = _pane("❯ Allow Bash(rm -rf build)? (y/n)")
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == (TurnStatus.STALLED, "prompt")
    assert "Allow Bash" in result.pane_tail


@pytest.mark.parametrize("key", ["terminal_pending"])
async def test_other_prompt_signals_stall_too(tmp_path, monkeypatch, key):
    # #61: a trust dialog / login shows up as terminal_pending, not as an
    # elicitation — same instant stall
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    chat = _FakeChat([TurnStatus.RUNNING])
    base = chat.snapshot

    async def snapshot():
        return {**(await base()), key: True}

    chat.snapshot = snapshot
    d = _settle_driver(tmp_path, chat, [[]])
    d._pane_tail = _pane(None)
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == (TurnStatus.STALLED, "prompt")


async def test_one_poll_prompt_flicker_is_not_a_stall(tmp_path, monkeypatch):
    # a one-poll flicker of a prompt signal must not stall — a real dialog persists
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    import itertools

    chat = _FakeChat([TurnStatus.RUNNING], beats=itertools.count())
    base, polls = chat.snapshot, itertools.count()

    async def snapshot():
        n = next(polls)
        return {**(await base()), "terminal_pending": n % 2 == 0}

    chat.snapshot = snapshot
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == (TurnStatus.RUNNING, None)


async def test_frozen_heartbeat_stalls_after_stall_s(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    d = _settle_driver(tmp_path, _FakeChat([TurnStatus.RUNNING], beats=[7]), [[]])
    d.stall_s = 0.05
    d._pane_tail = _pane(None)
    result = await d.send("build it")
    assert (result.status, result.stall_reason, result.pane_tail) == (
        TurnStatus.STALLED,
        "no_progress",
        None,
    )


async def test_moving_heartbeat_is_not_a_stall(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    import itertools

    chat = _FakeChat([TurnStatus.RUNNING], beats=itertools.count())  # every poll a new updated_at
    d = _settle_driver(tmp_path, chat, [[]])
    d.stall_s = 0.05
    d.turn_timeout_s = 0.2
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == (TurnStatus.RUNNING, None)


async def test_snapshot_reads_the_raw_session(tmp_path):
    # the stall signals live only in the raw JSON (the client dataclass drops them)
    from types import SimpleNamespace

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "status": TurnStatus.RUNNING,
                "updated_at": 5,
                "pending_elicitations": [{"id": "e"}],
            }

    class _Http:
        async def get(self, url):
            assert url == "/v1/sessions/conv_x"
            return _Resp()

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_x")
    d._http = _Http()
    snap = await d._snapshot()
    assert (snap["status"], snap["updated_at"], len(snap["pending_elicitations"])) == (
        TurnStatus.RUNNING,
        5,
        1,
    )


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

    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.create_subprocess_exec", fake_exec)
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

    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.wait_for", instant_wait_for)
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_x")
    d._http = _Http()
    d._capture_pane = never
    assert await d._pane_tail() is None


# --- #67: pagination + waiting out the agent's own sub-agents -----------------


async def test_list_items_pages_past_the_server_cap(tmp_path):
    # todo-app-004: one 200-item page froze the settle check for the rest of the run
    from types import SimpleNamespace

    from flowbench.driver.omnigent import _PAGE

    all_items = [{"id": f"it_{i}", "type": "message", "role": "user"} for i in range(_PAGE * 2 + 7)]
    calls = []

    class _Paged:
        async def list_items(self, session_id, order, limit, after=None):
            calls.append(after)
            start = (
                0
                if after is None
                else next(i for i, it in enumerate(all_items) if it["id"] == after) + 1
            )
            return all_items[start : start + limit]

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_test")
    d._client = SimpleNamespace(sessions=_Paged())
    assert await d._list_items() == all_items
    assert calls == [None, f"it_{_PAGE - 1}", f"it_{2 * _PAGE - 1}"]


async def test_idle_with_busy_child_is_still_this_turn(tmp_path, monkeypatch):
    # the main agent parks at the prompt while its sub-agent runs; the turn ends
    # only once no child is busy (no "Continue." nudges, no simulator call)
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])
    chat.busy_children = [11]
    polls = {"n": 0}
    base = chat.snapshot

    async def snapshot():
        polls["n"] += 1
        if polls["n"] >= 5:
            chat.busy_children = []  # child finished
        return await base()

    chat.snapshot = snapshot
    d = _settle_driver(tmp_path, chat, [[], [_USER, _REPLY]])
    d.child_wake_s = 0
    result = await d.send("build it")
    assert result.status == TurnStatus.IDLE
    assert polls["n"] >= 5  # waited through the busy child


async def test_frozen_child_stalls_after_stall_s(tmp_path, monkeypatch):
    # a child that never settles must not hold the turn to the cap: its updated_at
    # is part of the heartbeat, so a frozen child is a no_progress stall
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE], beats=[7])
    chat.busy_children = [11]
    d = _settle_driver(tmp_path, chat, [[]])
    d.stall_s = 0.05
    d._pane_tail = _pane(None)
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == (TurnStatus.STALLED, "no_progress")


async def test_snapshot_attaches_busy_children_when_idle(tmp_path):
    from types import SimpleNamespace

    class _Resp:
        def __init__(self, data):
            self._d = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    class _Http:
        urls = []

        async def get(self, url):
            self.urls.append(url)
            if "/child_sessions" in url:
                if "after=" not in url:  # page 1: newest, idle; an older busy child is on page 2
                    page = {"data": [{"id": "c9", "busy": False, "updated_at": 9}]}
                    return _Resp({**page, "has_more": True, "last_id": "c9"})
                return _Resp(
                    {"data": [{"id": "c1", "busy": True, "updated_at": 5}], "has_more": False}
                )
            return _Resp({"status": TurnStatus.IDLE, "updated_at": 1})

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = SimpleNamespace(session_id="conv_test")
    d._http = _Http()
    assert (await d._snapshot())["busy_children"] == [5]
    assert any("after=c9" in u for u in _Http.urls)


async def test_failed_session_status_ends_the_turn(tmp_path):
    # The server reporting `failed` ends the turn at once — no settle loop, no
    # waiting out the turn cap. `send` then decides whether to re-send (only when
    # the labels confirm the injection never landed).
    d = _settle_driver(tmp_path, _FakeChat([TurnStatus.FAILED]), [[]])
    d.send_retry_attempts = 0
    result = await d.send("build it")
    assert result.status == TurnStatus.FAILED


async def test_undocumented_server_status_passes_through(tmp_path):
    # A server status outside the documented vocabulary (idle/running/failed)
    # must reach TurnResult.status unchanged — no exception, no relabelling
    # (decisions #7, AC10). NOT monkeypatching asyncio.sleep here: the
    # passthrough is reached only by exhausting turn_timeout_s in real
    # monotonic time, which _instant_sleep does not fast-forward.
    d = _settle_driver(tmp_path, _FakeChat(["zombie"]), [[]])
    d.turn_timeout_s = 0.1
    result = await d.send("build it")
    assert result.status == "zombie"


# --- wake-up after children clear (todo-app-005) -------------------------------


def _seq_snapshot(seq):
    polls = {"n": 0}

    async def snapshot():
        st, kids = seq[min(polls["n"], len(seq) - 1)]
        polls["n"] += 1
        return {
            "status": st,
            "updated_at": polls["n"],
            "pending_elicitations": [],
            "busy_children": kids,
        }

    return snapshot, polls


async def test_children_cleared_waits_for_the_wakeup_turn(tmp_path, monkeypatch):
    # children cleared, we reported idle, omnigent's task-notification started a turn
    # 1 s later and our inject queued behind it. After children clear the turn ends
    # only once that wake-up turn has run (or child_wake_s passes).
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    RUN, IDL = TurnStatus.RUNNING, TurnStatus.IDLE
    seq = [(RUN, [11]), (IDL, [11]), (IDL, []), (IDL, []), (IDL, []), (RUN, []), (IDL, [])]
    chat = _FakeChat([IDL])
    chat.snapshot, polls = _seq_snapshot(seq)
    d = _settle_driver(tmp_path, chat, [[], [_USER, _REPLY]])
    d.child_wake_s = 999  # grace never elapses: only the wake-up turn releases
    result = await d.send("build it")
    assert result.status == TurnStatus.IDLE
    assert polls["n"] >= len(seq)  # did not return during the idle gap


async def test_wakeup_already_ran_returns_idle_at_once(tmp_path, monkeypatch):
    # idle+busy -> running (the wake-up turn) -> idle: the wake-up is over, no grace
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    RUN, IDL = TurnStatus.RUNNING, TurnStatus.IDLE
    seq = [(IDL, [11]), (RUN, []), (IDL, [])]
    chat = _FakeChat([IDL])
    chat.snapshot, polls = _seq_snapshot(seq)
    d = _settle_driver(tmp_path, chat, [[], [_USER, _REPLY]])
    d.child_wake_s = 999
    result = await d.send("build it")
    assert result.status == TurnStatus.IDLE
    assert polls["n"] == len(seq)


async def test_cap_during_wake_wait_is_a_timeout_not_idle(tmp_path, monkeypatch):
    # children clear right before the turn cap, no wake-up seen: the withheld idle
    # must not leak out of the timeout fallthrough
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    IDL = TurnStatus.IDLE
    chat = _FakeChat([IDL])
    chat.snapshot, _ = _seq_snapshot([(IDL, [11]), (IDL, [])])
    d = _settle_driver(tmp_path, chat, [[], [_USER, _REPLY]])
    d.child_wake_s = 999
    d.turn_timeout_s = 0.05
    result = await d.send("build it")
    assert result.status == TurnStatus.TIMEOUT


async def test_queued_own_input_is_not_a_prompt(tmp_path, monkeypatch):
    # pending_inputs = our own message queued behind a running turn (omnigent docs),
    # never a human prompt; the turn just keeps waiting
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    import itertools

    chat = _FakeChat([TurnStatus.RUNNING], beats=itertools.count())
    base = chat.snapshot

    async def snapshot():
        return {**(await base()), "pending_inputs": [{"pending_id": "p1", "content": "Continue."}]}

    chat.snapshot = snapshot
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1
    result = await d.send("build it")
    assert (result.status, result.stall_reason) == (TurnStatus.RUNNING, None)


# --- start(): the session-creation path -------------------------------------
# Untested until S02.2 pulled the whole file into diff-cover's scope. It is also
# the code S02.5 has to migrate off omnigent's privates (`sessions._http`,
# `sessions._base`, hand-built `SessionsChat`), so pinning the calls it makes is
# the safety net that refactor needs.


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.raised = False

    def raise_for_status(self):
        self.raised = True

    def json(self):
        return self._payload


class _FakeHttp:
    """Stands in for `httpx.AsyncClient` and for `sessions._http`."""

    def __init__(self, hosts=None):
        self.hosts = (
            hosts
            if hosts is not None
            else [
                {
                    "host_id": "h1",
                    "status": "offline",
                    "configured_harnesses": {"claude-native": 1},
                },
                {"host_id": "h2", "status": "online", "configured_harnesses": {"codex-native": 1}},
                {"host_id": "h3", "status": "online", "configured_harnesses": {"claude-native": 1}},
            ]
        )
        self.posts = []
        self.init_kwargs = None

    async def get(self, url):
        return _FakeResponse({"hosts": self.hosts})

    async def post(self, url, data=None, files=None):
        self.posts.append((url, data, files))
        return _FakeResponse({"session_id": 4242})


class _FakeSessionsNs:
    def __init__(self, http):
        self._http = http
        self._base = "http://omni"
        self.model_override = None
        self.effort = None

    async def get(self, session_id):
        return {"id": session_id}

    async def set_model_override(self, session_id, *, model_override, silent):
        self.model_override = (session_id, model_override, silent)

    async def set_reasoning_effort(self, session_id, *, reasoning_effort):
        self.effort = (session_id, reasoning_effort)


def _patch_start(monkeypatch, http):
    """Wire start()'s five function-local imports to fakes."""
    import httpx
    import omnigent.host.daemon_launch as dl
    import omnigent_client
    import omnigent_client._sessions_chat as sc

    ns = _FakeSessionsNs(http)
    launched = {}

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: http)
    monkeypatch.setattr(
        omnigent_client, "OmnigentClient", lambda **kw: SimpleNamespace(sessions=ns)
    )
    monkeypatch.setattr(
        sc, "SessionsChat", lambda **kw: SimpleNamespace(session_id="conv_new", **kw)
    )

    async def _launch(http_, *, host_id, session_id, workspace):
        launched["args"] = (host_id, session_id, workspace)
        return "runner-1"

    async def _wait(http_, runner_id, timeout_s):
        launched["waited"] = (runner_id, timeout_s)

    monkeypatch.setattr(dl, "launch_or_reuse_daemon_runner", _launch)
    monkeypatch.setattr(dl, "wait_for_runner_online", _wait)
    return ns, launched


async def test_start_refuses_when_the_api_key_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-nope")  # pragma: allowlist secret
    d = OmnigentDriver(run_dir=tmp_path / "run", artifact_name="plan.md")
    with pytest.raises(RuntimeError, match="subscription billing"):
        await d.start()


async def test_start_creates_the_session_and_launches_the_runner(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    http = _FakeHttp()
    ns, launched = _patch_start(monkeypatch, http)
    run_dir = tmp_path / "run"
    d = OmnigentDriver(
        run_dir=run_dir, artifact_name="plan.md", model="sonnet", reasoning_effort="high"
    )

    await d.start()

    assert run_dir.is_dir()  # created for the agent to write into
    url, data, files = http.posts[0]
    assert url == "http://omni/v1/sessions"
    assert json.loads(data["metadata"]) == d._create_metadata()
    name, blob, mime = files["bundle"]
    assert (name, mime) == ("agent.tar.gz", "application/gzip")
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        assert tar.getnames()[:2] == [".", "./config.yaml"]
    # the online claude-native host, not the offline one or the codex one
    assert launched["args"] == ("h3", "4242", str(run_dir))
    assert launched["waited"] == ("runner-1", 90)
    assert ns.model_override == ("4242", "sonnet", True)
    assert ns.effort == ("4242", "high")
    assert d._chat.session_id == "conv_new"
    assert d._runner_id == "runner-1"


async def test_start_skips_reasoning_effort_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ns, _ = _patch_start(monkeypatch, _FakeHttp())
    await OmnigentDriver(run_dir=tmp_path / "run", artifact_name="plan.md").start()
    assert ns.effort is None


async def test_start_git_inits_the_run_dir_once(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _patch_start(monkeypatch, _FakeHttp())
    run_dir = tmp_path / "run"
    d = OmnigentDriver(run_dir=run_dir, artifact_name="plan.md", git_init=True)

    await d.start()
    assert (run_dir / ".git").is_dir()

    # already a repo: git_init_repo must not run again (it would re-commit)
    def _boom(path):  # pragma: no cover - must not be called
        raise AssertionError("git_init_repo called on an existing repo")

    monkeypatch.setattr("flowbench.driver.omnigent.git_init_repo", _boom)
    await d.start()


async def test_start_raises_when_no_host_has_claude_native(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _patch_start(monkeypatch, _FakeHttp(hosts=[]))
    d = OmnigentDriver(run_dir=tmp_path / "run", artifact_name="plan.md")
    with pytest.raises(RuntimeError, match="no online host with claude-native"):
        await d.start()


# --- the paths the file's move pulled into diff-cover's scope ----------------


class _LabelHttp:
    def __init__(self, labels=None, boom=False):
        self._labels = labels
        self._boom = boom

    async def get(self, _url):
        if self._boom:
            raise RuntimeError("transport gone")
        return _FakeResponse({"labels": self._labels})


async def test_injection_undelivered_reads_the_error_labels(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._http = _LabelHttp(
        {
            "omnigent.last_task_error_code": "runner_error",
            "omnigent.last_task_error_message": "The message was not delivered",
        }
    )
    assert await d._injection_undelivered() is True

    # a failure that is not the undelivered one: retrying could double-deliver
    d._http = _LabelHttp({"omnigent.last_task_error_code": "model_error"})
    assert await d._injection_undelivered() is False


async def test_injection_undelivered_is_false_when_the_read_fails(tmp_path):
    """Unknown means "do not retry" — a blind resend can double-deliver."""
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._http = _LabelHttp(boom=True)
    assert await d._injection_undelivered() is False


async def test_context_tokens_none_before_a_session_exists(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    assert await d._context_tokens() is None


async def test_context_tokens_none_when_the_read_fails(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._chat = _FakeChat([TurnStatus.IDLE])
    d._http = _LabelHttp(boom=True)
    assert await d._context_tokens() is None


async def test_send_once_captures_the_streamed_events(tmp_path, monkeypatch):
    """`events` is what conversation_url is later recovered from."""
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)

    @dataclass
    class _Delta:
        conversation_id: str

    chat = _FakeChat([TurnStatus.IDLE])

    def _send(_text):
        async def _gen():
            yield _Delta("conv_xyz")

        return _gen()

    chat.send = _send
    d = _settle_driver(tmp_path, chat, [[_USER, _REPLY]])
    d.turn_timeout_s = 0.01  # the turn boundary is not what this test is about
    await d._send_once("hi")
    assert d._captured == [{"__type__": "_Delta", "conversation_id": "conv_xyz"}]
    assert d.conversation_url() == f"{d.server_url}/c/conv_xyz"


async def test_capture_session_returns_the_run_fields(tmp_path):
    (tmp_path / "plan.md").write_text("# the plan\n")
    chat = _FakeChat([TurnStatus.IDLE])
    d = _settle_driver(tmp_path, chat, [[_USER, _USER, _REPLY]])
    d._http = _LabelHttp({"omnigent.last_context_tokens": "1234"})

    out = await d.capture_session()

    assert out["items"] == [_USER, _REPLY]  # deduped
    assert out["context_tokens"] == 1234
    assert out["artifact_exists"] is True
    assert out["artifact_path"] == str(tmp_path / "plan.md")
    assert out["artifact_text"] == "# the plan\n"
    assert (out["model"], out["driver"]) == (d.model, "omnigent")
    assert out["session_id"] == "conv_test"
    assert isinstance(out["duration_s"], float)


async def test_close_swallows_a_failing_client(tmp_path):
    """Teardown must never mask the real error that got us here."""

    class _Boom:
        async def aclose(self):
            raise RuntimeError("already gone")

    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    d._http, d._client = _Boom(), None
    await d.close()
    assert d._closed is True
