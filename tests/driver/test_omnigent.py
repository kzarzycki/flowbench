"""Driver contract, offline. We don't drive a live agent here (Task 1 + Task 7
cover that); we assert the interface contract and the pure transcript helpers."""

import asyncio
import io
import json
import logging
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from flowbench.driver import AgentDriver, OmnigentDriver, TurnResult
from flowbench.transcript import dedup_items, is_control_message, last_assistant_text
from flowbench.types import TurnStatus


def test_omnigent_driver_satisfies_interface():
    d = OmnigentDriver(run_dir=Path("/tmp/x"))
    assert isinstance(d, AgentDriver)
    for m in ("start", "send", "capture_session", "close"):
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
    d = OmnigentDriver(run_dir=Path("/tmp/x"))
    await d.close()
    await d.close()  # must not raise
    assert d._closed is True


def test_driver_has_no_artifact_concern(tmp_path):
    # S02.4: which file proves delivery is the orchestrator's knowledge (run.py's
    # probe, consumed by the loop) — the driver and its ABC know nothing of it
    assert not hasattr(AgentDriver, "artifact_path")
    d = OmnigentDriver(run_dir=tmp_path)  # constructs with no artifact argument
    assert not hasattr(d, "artifact_name")
    assert not hasattr(d, "artifact_path")


def test_conversation_url_built_from_captured_events(tmp_path):
    # the conv id is scraped from streamed events; the URL is the omnigent UI route
    # a human opens to browse + resume the (still-alive) SUT session.
    d = OmnigentDriver(run_dir=tmp_path, server_url="http://127.0.0.1:6767")
    assert d.conversation_url() is None  # nothing captured yet
    d._captured = [
        {"__type__": "SessionUsageEvent"},
        {"__type__": "OutputTextDeltaEvent", "conversation_id": "conv_abc123"},
    ]
    assert d.conversation_url() == "http://127.0.0.1:6767/c/conv_abc123"


def test_turn_result_shape():
    r = TurnResult(status=TurnStatus.IDLE, assistant_text="done")
    assert (r.status, r.assistant_text) == (TurnStatus.IDLE, "done")


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

    def __init__(self, batches, labels=None, get_error=None):
        self._batches = list(batches)
        self._labels = {} if labels is None else labels
        self._get_error = get_error

    async def get(self, session_id):
        """The typed `Session` (labels only matter here); raises like the SDK does on
        a >= 400 or non-Session response."""
        if self._get_error is not None:
            raise self._get_error
        return SimpleNamespace(id=session_id, labels=self._labels)

    async def list_items(self, session_id, order, limit, after=None):
        if len(self._batches) > 1:
            return self._batches.pop(0)
        return self._batches[0]


def _settle_driver(tmp_path, chat, batches):
    from types import SimpleNamespace

    d = OmnigentDriver(run_dir=tmp_path)
    d.turn_timeout_s = 1.0
    d.settle_poll_s = 0.01
    d._chat = chat
    d._snapshot = chat.snapshot
    d._client = SimpleNamespace(sessions=_FakeSessions(batches))
    return d


class _Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def _fake_clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr("flowbench.driver.omnigent._now", c.now)
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", c.sleep)
    return c


_USER = {"type": "message", "role": "user", "content": "grade these plans"}
_REPLY = {"type": "message", "role": "assistant", "content": "WINNER: B"}
_USER2 = {"type": "message", "role": "user", "content": "keep going"}
_EMPTY_REPLY = {"type": "message", "role": "assistant", "content": "  "}
_REPLY2 = {"type": "message", "role": "assistant", "content": "WINNER: C"}
_BANNER_TEXT = "You've hit your session limit · resets 6:40pm (Europe/Zurich)"  # s025p2-620b16b
_BANNER = {
    "type": "message",
    "role": "assistant",
    "content": [{"type": "output_text", "text": _BANNER_TEXT}],
}

_real_sleep = asyncio.sleep


async def _fast_sleep(s):
    await _real_sleep(min(s, 0.001))


async def _hang(*a, **k):
    await asyncio.Event().wait()


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
    _fake_clock(monkeypatch)
    # RUNNING once, then stays IDLE (an alternating sequence would let a later
    # _wait_idle expire on RUNNING instead of exercising the settle expiry)
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])
    d = _settle_driver(tmp_path, chat, [[], [_USER]])  # reply never lands
    d.turn_timeout_s = 10.0
    result = await d.send("grade these plans")
    assert result.status == TurnStatus.TIMEOUT


async def _instant_sleep(_secs):
    return None


async def test_read_retry_survives_transient_errors(tmp_path, monkeypatch):
    # a single ReadError during polling killed a live run; reads are idempotent
    import httpx

    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    d = OmnigentDriver(run_dir=tmp_path)
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
    clock = _fake_clock(monkeypatch)
    d = OmnigentDriver(run_dir=tmp_path)
    d.turn_timeout_s = 1000
    outcomes = [
        TurnResult(TurnStatus.FAILED, ""),
        TurnResult(TurnStatus.IDLE, "the plan is complete"),
    ]
    sent = []

    async def fake_send_once(text, deadline):
        sent.append(text)
        return outcomes.pop(0)

    async def resend_allowed():
        return True

    d._send_once = fake_send_once
    d._resend_allowed = resend_allowed
    result = await d.send("go on")
    assert result.status == TurnStatus.IDLE
    assert sent == ["go on", "go on"]  # same text re-sent once
    assert clock.t == 30.0


async def test_send_does_not_retry_delivered_failure(tmp_path, monkeypatch):
    _fake_clock(monkeypatch)
    d = OmnigentDriver(run_dir=tmp_path)
    d.turn_timeout_s = 1000
    sent = []

    async def fake_send_once(text, deadline):
        sent.append(text)
        return TurnResult(TurnStatus.FAILED, "")

    async def resend_not_allowed():
        return False  # a real failure (e.g. model_error), not an undelivered inject

    d._send_once = fake_send_once
    d._resend_allowed = resend_not_allowed
    result = await d.send("go on")
    assert result.status == TurnStatus.FAILED
    assert sent == ["go on"]  # no blind retry


async def test_failed_exhausts_bounded_resends(tmp_path, monkeypatch):
    _fake_clock(monkeypatch)
    d = OmnigentDriver(run_dir=tmp_path)
    d.turn_timeout_s = 1000
    sent = []

    async def fake_send_once(text, deadline):
        sent.append(text)
        return TurnResult(TurnStatus.FAILED, "")

    async def resend_allowed():
        return True

    d._send_once = fake_send_once
    d._resend_allowed = resend_allowed
    result = await d.send("go on")
    assert result.status == TurnStatus.FAILED
    assert len(sent) == 1 + d.send_retry_attempts


@pytest.mark.parametrize(
    "result",
    [
        TurnResult(TurnStatus.TIMEOUT, ""),
        TurnResult(TurnStatus.RUNNING, ""),
        TurnResult(TurnStatus.STALLED, "", stall_reason="prompt"),
        TurnResult(TurnStatus.QUOTA, "You've hit your session limit · resets 6:40pm"),
    ],
)
async def test_non_failed_statuses_are_never_resent(tmp_path, monkeypatch, result):
    # rows 4/5: TIMEOUT, RUNNING and STALLED (idle handles its own row-5 timeout
    # transform inside _send_once) return from send() after exactly one _send_once
    _fake_clock(monkeypatch)
    d = OmnigentDriver(run_dir=tmp_path)
    d.turn_timeout_s = 1000
    sent = []

    async def fake_send_once(text, deadline):
        sent.append(text)
        return result

    async def must_not_be_called():
        raise AssertionError("_resend_allowed must not be consulted for a non-FAILED status")

    d._send_once = fake_send_once
    # send_retry_wait_s (30) fits the 1000 s budget, so only the status gate stands
    # between this result and a re-send; a label read here would mean the gate leaked
    d._resend_allowed = must_not_be_called
    out = await d.send("go on")
    assert out is result
    assert len(sent) == 1


async def test_failed_with_new_text_is_a_flaked_idle(tmp_path, monkeypatch, capsys):
    # row 2: the server said failed AFTER the reply landed — trust the text, IDLE
    _fake_clock(monkeypatch)
    chat = _FakeChat([TurnStatus.FAILED])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[], [_USER, _REPLY]])
    # a retry-eligible budget: if the FAILED were not converted to a flaked idle,
    # send_retry_wait_s (30) would leave more than enough of turn_timeout_s (1000)
    # to attempt a re-send, so this budget actually exercises the "must not resend" claim
    d.turn_timeout_s = 1000

    async def must_not_be_called():
        raise AssertionError("_resend_allowed must not be called for a flaked idle")

    d._resend_allowed = must_not_be_called
    result = await d.send("grade these plans")
    assert (result.status, result.flaked, result.assistant_text) == (
        TurnStatus.IDLE,
        True,
        "WINNER: B",
    )
    assert len(injects) == 1
    assert "turn flaked" in capsys.readouterr().err


async def test_failed_with_a_quota_banner_is_quota_not_flaked(tmp_path, monkeypatch, capsys):
    # #131: the "reply" is the CLI's session-limit banner and the server said failed —
    # not row 2 (a flaked idle): the wall, reported as QUOTA, never re-sent
    _fake_clock(monkeypatch)
    chat = _FakeChat([TurnStatus.FAILED])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[], [_USER, _BANNER]])
    d.turn_timeout_s = 1000  # a retry-eligible budget, as in the flaked-idle test

    async def must_not_be_called():
        raise AssertionError("_resend_allowed must not be called for a quota banner")

    d._resend_allowed = must_not_be_called
    result = await d.send("grade these plans")
    assert (result.status, result.flaked, result.assistant_text) == (
        TurnStatus.QUOTA,
        False,
        _BANNER_TEXT,
    )
    assert len(injects) == 1
    assert "quota:" in capsys.readouterr().err


async def test_idle_with_a_quota_banner_is_quota(tmp_path, monkeypatch):
    # the server may also settle idle on the banner: still the wall, not a reply
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _instant_sleep)
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])
    d = _settle_driver(tmp_path, chat, [[], [_USER, _BANNER]])
    result = await d.send("grade these plans")
    assert (result.status, result.assistant_text) == (TurnStatus.QUOTA, _BANNER_TEXT)


async def test_failed_with_only_an_empty_new_message_is_not_flaked(tmp_path):
    # the only NEW assistant message is empty/whitespace; an older non-empty reply
    # exists but does not count as "new" — this is a re-send candidate, not a flake
    chat = _FakeChat([TurnStatus.FAILED])
    d = _settle_driver(tmp_path, chat, [[_USER, _REPLY], [_USER, _REPLY, _USER2, _EMPTY_REPLY]])
    d.send_retry_attempts = 0
    result = await d.send("go on")
    assert result.status == TurnStatus.FAILED
    assert result.flaked is False


async def test_failed_with_a_repeated_identical_reply_is_flaked(tmp_path):
    # a new reply identical to the previous turn's text IS new text (count-based,
    # not equality-based)
    chat = _FakeChat([TurnStatus.FAILED])
    d = _settle_driver(tmp_path, chat, [[_USER, _REPLY], [_USER, _REPLY, _USER, _REPLY]])
    result = await d.send("go on")
    assert (result.status, result.flaked) == (TurnStatus.IDLE, True)


async def test_idle_with_only_an_empty_new_message_keeps_settling(tmp_path, monkeypatch):
    # row 5's predicate (new_assistant_text) is the same one the settle loop
    # uses: an empty new message must not end the settle early
    clock = _fake_clock(monkeypatch)
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])
    d = _settle_driver(
        tmp_path,
        chat,
        [[_USER, _REPLY], [_USER, _REPLY, _EMPTY_REPLY], [_USER, _REPLY, _EMPTY_REPLY, _REPLY2]],
    )
    d.turn_timeout_s = 100
    result = await d.send("grade these plans")
    assert result.status == TurnStatus.IDLE
    assert result.assistant_text == _REPLY2["content"]
    assert clock.t < 100  # settled on the real reply, not on the budget


async def test_one_budget_per_send(tmp_path, monkeypatch):
    # pre-S02.3, a second _wait_idle got its OWN fresh turn_timeout_s (≈160 here);
    # S02.3 gives the whole send one budget
    clock = _fake_clock(monkeypatch)
    seq = (
        [(TurnStatus.RUNNING, [])] * 40
        + [(TurnStatus.IDLE, [])]
        + [(TurnStatus.RUNNING, [])] * 10_000
    )
    chat = _FakeChat([TurnStatus.RUNNING])
    chat.snapshot, polls = _seq_snapshot(seq)
    d = _settle_driver(tmp_path, chat, [[], [_USER]])  # no new text -> keeps settling
    d.turn_timeout_s = 100
    result = await d.send("build it")
    assert result.status == TurnStatus.RUNNING
    assert clock.t <= 100 + d.settle_poll_s + 1.5
    # the trace's IDLE (at seq index 40) was actually consumed, not skipped over
    assert polls["n"] > 41
    # the budget was actually spent, not returned early on a first-poll RUNNING
    assert clock.t >= d.turn_timeout_s


async def test_no_inject_when_the_budget_is_gone_before_it(tmp_path, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr("flowbench.driver.omnigent._now", clock.now)

    async def overshooting_sleep(s):
        clock.t += s + 1  # the wait itself overshoots what's left of the budget

    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", overshooting_sleep)

    chat = _FakeChat([TurnStatus.FAILED])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 31
    d.send_retry_wait_s = 30

    async def resend_allowed():
        return True

    d._resend_allowed = resend_allowed
    result = await d.send("go on")
    assert result.status == TurnStatus.TIMEOUT
    assert len(injects) == 1  # the re-send never injects: budget gone after the wait


async def test_no_inject_after_a_slow_initial_read(tmp_path, monkeypatch):
    clock = _fake_clock(monkeypatch)
    chat = _FakeChat([TurnStatus.IDLE])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 10.0
    real_list_items = d._list_items
    calls = {"n": 0}

    async def slow_first_read():
        calls["n"] += 1
        if calls["n"] == 1:
            clock.t += d.turn_timeout_s + 1
            return []
        return await real_list_items()

    d._list_items = slow_first_read
    result = await d.send("go on")
    assert result.status == TurnStatus.TIMEOUT
    assert injects == []


@pytest.mark.parametrize("turn_timeout_s,expected_sends", [(50, 2), (10, 1)])
async def test_resend_needs_budget_for_its_wait(
    tmp_path, monkeypatch, turn_timeout_s, expected_sends
):
    _fake_clock(monkeypatch)
    d = OmnigentDriver(run_dir=tmp_path)
    d.turn_timeout_s = turn_timeout_s
    d.send_retry_wait_s = 30
    d.send_retry_attempts = 3
    sent = []

    async def fake_send_once(text, deadline):
        sent.append(text)
        return TurnResult(TurnStatus.FAILED, "")

    async def resend_allowed():
        return True

    d._send_once = fake_send_once
    d._resend_allowed = resend_allowed
    result = await d.send("go on")
    assert len(sent) == expected_sends
    assert result.status == TurnStatus.FAILED


# --- hard ceiling: asyncio.timeout cancels whatever is in flight -------------


async def test_hard_ceiling_cancels_a_hanging_status_read(tmp_path):
    hit = {}
    chat = _FakeChat([TurnStatus.RUNNING])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1

    async def hang_snapshot():
        hit["snapshot"] = True
        await _hang()

    d._snapshot = hang_snapshot
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert "snapshot" in hit
    assert len(injects) == 1


async def test_hard_ceiling_stops_before_the_first_inject_when_the_initial_read_hangs(tmp_path):
    hit = {}
    chat = _FakeChat([TurnStatus.RUNNING])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1

    async def hang_list_items():
        hit["items"] = True
        await _hang()

    d._list_items = hang_list_items
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert "items" in hit
    assert injects == []


async def test_hard_ceiling_cancels_a_hanging_post_wait_item_read(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _fast_sleep)
    hit = {}
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1
    calls = {"n": 0}

    async def list_items():
        calls["n"] += 1
        if calls["n"] == 1:
            return []
        hit["items"] = True
        await _hang()

    d._list_items = list_items
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert "items" in hit
    assert len(injects) == 1


async def test_hard_ceiling_cancels_a_hanging_second_page(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", _fast_sleep)
    from flowbench.driver.omnigent import _PAGE

    hit = {}
    chat = _FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    calls = {"n": 0}

    class _Paged:
        async def list_items(self, session_id, order, limit, after=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return []  # n_before probe
            if calls["n"] == 2:
                return [{"id": f"i{n}", "type": "message", "role": "user"} for n in range(_PAGE)]
            hit["second_page"] = True
            await _hang()

    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = chat
    d._snapshot = chat.snapshot
    d._client = SimpleNamespace(sessions=_Paged())
    d.turn_timeout_s = 0.1
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert "second_page" in hit
    assert calls["n"] == 3  # pagination reached: a full first page, then the second
    assert len(injects) == 1


async def test_hard_ceiling_cuts_read_retry_backoff(tmp_path):
    import httpx

    chat = _FakeChat([TurnStatus.RUNNING])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1
    calls = {"n": 0}

    async def always_fails():
        calls["n"] += 1
        raise httpx.ReadError("down")

    d._snapshot = always_fails
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert calls["n"] >= 1
    assert len(injects) == 1


async def test_hard_ceiling_cancels_a_hanging_label_read(tmp_path):
    hit = {}
    chat = _FakeChat([TurnStatus.FAILED])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.1
    d.send_retry_wait_s = 0.01  # the 0.1 budget makes the re-send eligible

    async def hanging_get(_session_id):
        hit["labels"] = True
        await _hang()

    d._client.sessions.get = hanging_get
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert "labels" in hit
    assert len(injects) == 1


async def test_hard_ceiling_cancels_an_overshooting_retry_sleep(tmp_path, monkeypatch):
    hit = {}

    async def overshoot_sleep(s):
        hit["slept"] = s
        await _real_sleep(s + 1.0)

    monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", overshoot_sleep)
    chat = _FakeChat([TurnStatus.FAILED])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.3
    d.send_retry_wait_s = 0.1

    async def resend_allowed():
        return True

    d._resend_allowed = resend_allowed
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert hit["slept"] == 0.1  # the sleep WAS eligible; the timer still cut it
    assert len(injects) == 1  # never re-injected


async def test_hard_ceiling_cancels_the_resend_wait(tmp_path):
    hit = {}
    chat = _FakeChat([TurnStatus.FAILED])
    calls = {"n": 0}
    base_snapshot = chat.snapshot

    async def snapshot():
        calls["n"] += 1
        if calls["n"] == 1:
            return await base_snapshot()
        hit["hang"] = True
        await _hang()

    chat.snapshot = snapshot
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 0.6
    d.send_retry_wait_s = 0.1

    async def resend_allowed():
        return True

    d._resend_allowed = resend_allowed
    t0 = time.monotonic()
    result = await d.send("go on")
    assert result == TurnResult(TurnStatus.TIMEOUT, "")
    assert time.monotonic() - t0 < 2.0
    assert "hang" in hit
    assert len(injects) == 2  # the re-send DID inject; its second wait hung


async def test_context_tokens_read_is_bounded(tmp_path, monkeypatch):
    """`_context_tokens` has no outer ceiling; the SDK client reads with a 600 s
    budget, so the driver must cap the label read itself (60 s, as before)."""
    import flowbench.driver.omnigent as mod

    monkeypatch.setattr(mod, "_LABEL_READ_S", 0.05)

    async def hanging_get(_session_id):
        await _hang()

    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.IDLE])
    d._client = SimpleNamespace(sessions=SimpleNamespace(get=hanging_get))
    t0 = time.monotonic()
    assert await d._context_tokens() is None
    assert time.monotonic() - t0 < 1.0


async def test_capture_session_includes_context_tokens(tmp_path):
    # cost signal: final context size from session labels lands in the capture
    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.IDLE])
    d._client = _label_client({"omnigent.last_context_tokens": "42072"})
    assert await d._context_tokens() == 42072


async def test_context_tokens_none_when_label_missing(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.IDLE])
    d._client = _label_client({})
    assert await d._context_tokens() is None


def _label_client(labels=None, boom=None):
    """`_client.sessions.get()` double: the typed `Session` carries `labels`
    (omnigent_client 0.2.0); a >= 400 or non-Session response raises instead of
    returning."""

    labels = {} if labels is None else labels  # the SDK always hands a dict

    async def get(session_id):
        if boom is not None:
            raise boom
        return SimpleNamespace(id=session_id, labels=labels)

    return SimpleNamespace(sessions=SimpleNamespace(get=get))


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
    _fake_clock(monkeypatch)
    import itertools

    chat = _FakeChat([TurnStatus.RUNNING], beats=itertools.count())
    base, polls = chat.snapshot, itertools.count()

    async def snapshot():
        n = next(polls)
        return {**(await base()), "terminal_pending": n % 2 == 0}

    chat.snapshot = snapshot
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 10.0
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
    _fake_clock(monkeypatch)
    import itertools

    chat = _FakeChat([TurnStatus.RUNNING], beats=itertools.count())  # every poll a new updated_at
    d = _settle_driver(tmp_path, chat, [[]])
    d.stall_s = 0.05
    d.turn_timeout_s = 10.0
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

    d = OmnigentDriver(run_dir=tmp_path)
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

    d = OmnigentDriver(run_dir=tmp_path)
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
    d = OmnigentDriver(run_dir=tmp_path)
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
    d = OmnigentDriver(run_dir=tmp_path)
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

    d = OmnigentDriver(run_dir=tmp_path)
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

    d = OmnigentDriver(run_dir=tmp_path)
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


async def test_undocumented_server_status_passes_through(tmp_path, monkeypatch):
    # A server status outside the documented vocabulary (idle/running/failed)
    # must reach TurnResult.status unchanged — no exception, no relabelling
    # (decisions #7, AC10). The fake clock advances on sleep, so the cap is
    # reached deterministically without spending real wall-clock time.
    _fake_clock(monkeypatch)
    d = _settle_driver(tmp_path, _FakeChat(["zombie"]), [[]])
    d.turn_timeout_s = 10.0
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
    _fake_clock(monkeypatch)
    IDL = TurnStatus.IDLE
    chat = _FakeChat([IDL])
    chat.snapshot, _ = _seq_snapshot([(IDL, [11]), (IDL, [])])
    d = _settle_driver(tmp_path, chat, [[], [_USER, _REPLY]])
    d.child_wake_s = 999
    d.turn_timeout_s = 10.0
    result = await d.send("build it")
    assert result.status == TurnStatus.TIMEOUT


async def test_queued_own_input_is_not_a_prompt(tmp_path, monkeypatch):
    # pending_inputs = our own message queued behind a running turn (omnigent docs),
    # never a human prompt; the turn just keeps waiting
    _fake_clock(monkeypatch)
    import itertools

    chat = _FakeChat([TurnStatus.RUNNING], beats=itertools.count())
    base = chat.snapshot

    async def snapshot():
        return {**(await base()), "pending_inputs": [{"pending_id": "p1", "content": "Continue."}]}

    chat.snapshot = snapshot
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 10.0
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
                    "configured_harnesses": {"claude-native": True},
                },
                {
                    "host_id": "h2",
                    "status": "online",
                    "configured_harnesses": {"codex-native": True},
                },
                {
                    "host_id": "h3",
                    "status": "online",
                    "configured_harnesses": {"claude-native": True},
                },
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

    ns = _FakeSessionsNs(http)
    launched = {}

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: http)
    monkeypatch.setattr(
        omnigent_client, "OmnigentClient", lambda **kw: SimpleNamespace(sessions=ns)
    )

    class _FakeChatSession:
        """`SessionsChat.session_id` is a property over `self._session.id`
        (the root export of omnigent_client) — the fake reads it off the session
        the driver passes, so a driver that stopped passing one would fail."""

        def __init__(self, *, namespace, files_uploader, files_getter, session):
            self.namespace = namespace
            self._session = session

        @property
        def session_id(self):
            return self._session["id"]

    monkeypatch.setattr(omnigent_client, "SessionsChat", _FakeChatSession)

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
    d = OmnigentDriver(run_dir=tmp_path / "run")
    with pytest.raises(RuntimeError, match="subscription billing"):
        await d.start()


async def test_start_creates_the_session_and_launches_the_runner(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    http = _FakeHttp()
    ns, launched = _patch_start(monkeypatch, http)
    run_dir = tmp_path / "run"
    d = OmnigentDriver(run_dir=run_dir, model="sonnet", reasoning_effort="high")

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
    assert d._chat.session_id == "4242"  # off the session the driver fetched
    assert d._runner_id == "runner-1"


async def test_start_skips_reasoning_effort_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ns, _ = _patch_start(monkeypatch, _FakeHttp())
    await OmnigentDriver(run_dir=tmp_path / "run").start()
    assert ns.effort is None


async def test_start_raises_when_no_host_has_claude_native(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _patch_start(monkeypatch, _FakeHttp(hosts=[]))
    d = OmnigentDriver(run_dir=tmp_path / "run")
    with pytest.raises(RuntimeError, match="no online host with claude-native"):
        await d.start()


# --- fields the harness will not carry (#149) -------------------------------


def _bundle_bits(tmp_path):
    sk = tmp_path / "skills" / "brainstorming"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("# b\n")
    mcp = tmp_path / "fetch.yaml"
    mcp.write_text("transport: http\n")
    return sk, mcp


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("reasoning_effort", "high", ["reasoning_effort"]),
        ("skills", "none", ["skills"]),
        ("skill_dirs", "SKILL_DIR", ["skill_dirs"]),
        ("mcp_files", "MCP_FILE", ["mcp_files"]),
    ],
)
def test_warns_only_about_the_field_that_is_set(tmp_path, field, value, expected):
    """One field at a time: an implementation that names all four whenever any
    one is set passes an all-fields test and fails here."""
    sk, mcp = _bundle_bits(tmp_path)
    value = {"SKILL_DIR": [sk], "MCP_FILE": [mcp]}.get(value, value)
    d = OmnigentDriver(run_dir=tmp_path, harness="antigravity-native", **{field: value})
    assert d._unhonoured_fields() == expected


def test_warns_about_every_field_that_is_set(tmp_path):
    sk, mcp = _bundle_bits(tmp_path)
    d = OmnigentDriver(
        run_dir=tmp_path,
        harness="antigravity-native",
        reasoning_effort="high",
        skills="none",
        skill_dirs=[sk],
        mcp_files=[mcp],
    )
    assert d._unhonoured_fields() == ["mcp_files", "reasoning_effort", "skill_dirs", "skills"]


def test_no_warning_when_the_harness_carries_them(tmp_path):
    """Harness-scoped, not a blanket complaint: claude-native delivers all four."""
    sk, mcp = _bundle_bits(tmp_path)
    d = OmnigentDriver(
        run_dir=tmp_path,
        harness="claude-native",
        reasoning_effort="high",
        skills="none",
        skill_dirs=[sk],
        mcp_files=[mcp],
    )
    assert d._unhonoured_fields() == []


def test_no_warning_when_nothing_is_declared(tmp_path):
    """An agy flow that declares none of them has nothing to be warned about."""
    d = OmnigentDriver(run_dir=tmp_path, harness="antigravity-native")
    assert d._unhonoured_fields() == []


def test_codex_keeps_reasoning_effort_but_not_bundle_skills(tmp_path):
    """The two capability sets are genuinely different — codex honours effort and
    receives no bundle. One set collapses this to both names, or neither."""
    sk, _ = _bundle_bits(tmp_path)
    d = OmnigentDriver(
        run_dir=tmp_path, harness="codex-native", reasoning_effort="high", skill_dirs=[sk]
    )
    assert d._unhonoured_fields() == ["skill_dirs"]


async def test_start_logs_the_warning_once(tmp_path, monkeypatch, caplog):
    """The wiring the pure tests above deliberately do not cover."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _patch_start(monkeypatch, _FakeHttp(hosts=[_host("agy_box", "antigravity-native")]))
    sk, mcp = _bundle_bits(tmp_path)
    d = OmnigentDriver(
        run_dir=tmp_path / "run",
        harness="antigravity-native",
        model="gemini-3.8-flash-low",
        reasoning_effort="high",
        skills="none",
        skill_dirs=[sk],
        mcp_files=[mcp],
    )
    with caplog.at_level(logging.WARNING, logger="flowbench.driver.omnigent"):
        await d.start()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "antigravity-native" in warnings[0].getMessage()


async def test_start_is_quiet_for_a_harness_that_carries_the_fields(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _patch_start(monkeypatch, _FakeHttp())
    sk, _ = _bundle_bits(tmp_path)
    d = OmnigentDriver(run_dir=tmp_path / "run", skills="none", skill_dirs=[sk])
    with caplog.at_level(logging.WARNING, logger="flowbench.driver.omnigent"):
        await d.start()
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


# --- host resolution reads the driver's own harness (#149) ------------------


def _host(host_id, harness, *, status="online", configured=True):
    return {
        "host_id": host_id,
        "status": status,
        "configured_harnesses": {harness: configured},
    }


def _resolver(tmp_path, hosts, **kw):
    d = OmnigentDriver(run_dir=tmp_path, **kw)
    d._http = _FakeHttp(hosts=hosts)
    return d


async def test_resolve_host_matches_the_drivers_harness(tmp_path):
    """The live bug: the reference host advertises BOTH harnesses, so a lookup
    that names claude-native hands an agy flow a host it never checked."""
    d = _resolver(
        tmp_path,
        [_host("claude_box", "claude-native"), _host("agy_box", "antigravity-native")],
        harness="antigravity-native",
    )
    assert await d._resolve_host() == "agy_box"


async def test_resolve_host_skips_a_host_without_the_harness(tmp_path):
    d = _resolver(tmp_path, [_host("claude_box", "claude-native")], harness="antigravity-native")
    with pytest.raises(RuntimeError):
        await d._resolve_host()


async def test_resolve_host_error_names_the_missing_harness(tmp_path):
    d = _resolver(tmp_path, [_host("claude_box", "claude-native")], harness="antigravity-native")
    with pytest.raises(RuntimeError) as excinfo:
        await d._resolve_host()
    assert "antigravity-native" in str(excinfo.value)
    assert "claude-native" not in str(excinfo.value)


async def test_resolve_host_rejects_a_binary_missing_harness(tmp_path):
    """`configured_harnesses` carries `true`, `false` AND the diagnostic string
    `"binary-missing"`, which is truthy. Six harnesses are in that state on the
    reference host; none of them can launch a session."""
    d = _resolver(
        tmp_path,
        [_host("box", "pi-native", configured="binary-missing")],
        harness="pi-native",
    )
    with pytest.raises(RuntimeError):
        await d._resolve_host()


async def test_resolve_host_skips_an_offline_host_running_the_harness(tmp_path):
    d = _resolver(
        tmp_path,
        [_host("down", "antigravity-native", status="offline")],
        harness="antigravity-native",
    )
    with pytest.raises(RuntimeError):
        await d._resolve_host()


async def test_resolve_host_still_finds_claude_native(tmp_path):
    """The rename changed nothing for the default path: _FakeHttp's hosts are
    offline-claude, online-codex, online-claude, and h3 is the only match."""
    d = OmnigentDriver(run_dir=tmp_path)
    d._http = _FakeHttp()
    assert await d._resolve_host() == "h3"


async def test_start_launches_a_non_claude_harness(tmp_path, monkeypatch):
    """Through start(), not the helper: a correct _resolve_host left unwired at
    the call site passes every test above and still cannot run an agy flow."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, launched = _patch_start(
        monkeypatch, _FakeHttp(hosts=[_host("agy_box", "antigravity-native")])
    )
    d = OmnigentDriver(
        run_dir=tmp_path / "run", harness="antigravity-native", model="gemini-3.8-flash-low"
    )
    await d.start()
    assert launched["args"][0] == "agy_box"


# --- the paths the file's move pulled into diff-cover's scope ----------------


async def test_resend_allowed_reads_the_error_labels(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._client = _label_client({})  # row 3: no label at all — sim/judge sessions (#39)
    assert await d._resend_allowed() is True

    d._client = _label_client(
        {
            "omnigent.last_task_error_code": "runner_error",
            "omnigent.last_task_error_message": "The message was not delivered",
        }
    )
    assert await d._resend_allowed() is True  # row 1

    # a failure that is not the undelivered one: retrying could double-deliver
    d._client = _label_client({"omnigent.last_task_error_code": "model_error"})
    assert await d._resend_allowed() is False


async def test_resend_allowed_is_false_when_the_read_fails(tmp_path):
    """Unknown means "do not retry" — a blind resend can double-deliver."""
    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._client = _label_client(boom=httpx.ConnectError("transport gone"))
    assert await d._resend_allowed() is False


async def test_resend_allowed_is_false_when_the_status_read_errors(tmp_path):
    """An HTTP error response (503 etc.) is not "no label": `sessions.get` raises
    `OmnigentError` at >= 400, so this takes the except path, not row 3."""
    from omnigent_client import OmnigentError

    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._client = _label_client(boom=OmnigentError("503 service unavailable"))
    assert await d._resend_allowed() is False


def _real_sdk_client(handler):
    """The installed `SessionsNamespace` over an httpx MockTransport: pins what the
    SDK itself does with a response, not what a fake says it does."""
    import httpx
    from omnigent_client import SessionsNamespace

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SimpleNamespace(sessions=SessionsNamespace(http, "http://omni"))


async def test_resend_allowed_is_false_on_a_redirect_through_the_real_sdk(tmp_path):
    """`raise_for_status` in omnigent_client 0.2.0 lets 3xx through; the read is
    still "unknown" because a redirect body is not a Session (`require_json_object`
    / `Session.from_dict` raise) — the only 3xx that would slip past is one that
    carries a complete Session JSON, which no redirect does."""
    import httpx

    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._client = _real_sdk_client(
        lambda req: httpx.Response(302, headers={"location": "http://elsewhere/"}, text="")
    )
    assert await d._resend_allowed() is False
    d._client = _real_sdk_client(  # the web UI answers unknown paths with HTML 200
        lambda req: httpx.Response(200, headers={"content-type": "text/html"}, text="<html>")
    )
    assert await d._resend_allowed() is False
    d._client = _real_sdk_client(lambda req: httpx.Response(503, json={}))
    assert await d._resend_allowed() is False


async def test_failed_status_read_error_never_authorizes_a_resend(tmp_path, monkeypatch):
    _fake_clock(monkeypatch)
    chat = _FakeChat([TurnStatus.FAILED])
    injects = []
    base_send = chat.send

    def counting_send(text):
        injects.append(text)
        return base_send(text)

    chat.send = counting_send
    d = _settle_driver(tmp_path, chat, [[]])
    d.turn_timeout_s = 1000
    from omnigent_client import OmnigentError

    d._client.sessions._get_error = OmnigentError("503 service unavailable")
    result = await d.send("go on")
    assert result.status == TurnStatus.FAILED
    assert len(injects) == 1


async def test_context_tokens_none_before_a_session_exists(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path)
    assert await d._context_tokens() is None


async def test_context_tokens_none_when_the_read_fails(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.IDLE])
    d._client = _label_client(boom=httpx.ConnectError("transport gone"))
    assert await d._context_tokens() is None


# --- #106: the label reads catch a known tuple, log it, and let our bugs through ----

ABSENT = object()  # sentinel: leave the `labels` key out of the Session body entirely


def _session_body(labels):
    """A complete Session body as `Session.from_dict` needs it (omnigent_client
    0.2.0); `labels=ABSENT` omits the key."""
    body = {
        "id": "c",
        "agent_id": "a",
        "status": "idle",
        "created_at": 0,
        "updated_at": 0,
        "title": None,
        "items": [],
        "pending_inputs": [],
    }
    if labels is not ABSENT:
        body["labels"] = labels
    return body


def _driver_debug(caplog):
    return [
        r
        for r in caplog.records
        if r.name == "flowbench.driver.omnigent" and r.levelno == logging.DEBUG
    ]


def _failed_driver(tmp_path, client):
    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = _FakeChat([TurnStatus.FAILED])
    d._client = client
    return d


def _read_error(kind):
    """What `sessions.get()` raises: >= 400 / non-Session body, the driver's own
    read cap, a JSON object missing a Session field."""
    if kind == "omnigent":
        from omnigent_client import OmnigentError

        return OmnigentError("503")
    if kind == "timeout":
        return TimeoutError()
    return KeyError("agent_id")


async def test_resend_allowed_reraises_a_foreign_exception(tmp_path):
    """A driver bug is not an unreadable label: it must surface, not read as False."""
    d = _failed_driver(tmp_path, _label_client(boom=RuntimeError("driver bug")))
    with pytest.raises(RuntimeError, match="driver bug"):
        await d._resend_allowed()


async def test_context_tokens_reraises_a_foreign_exception(tmp_path):
    d = _failed_driver(tmp_path, _label_client(boom=RuntimeError("driver bug")))
    with pytest.raises(RuntimeError, match="driver bug"):
        await d._context_tokens()


@pytest.mark.parametrize("kind", ["omnigent", "timeout", "keyerror"])
async def test_resend_allowed_false_on_each_read_error(tmp_path, caplog, kind):
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")
    boom = _read_error(kind)
    d = _failed_driver(tmp_path, _label_client(boom=boom))
    assert await d._resend_allowed() is False
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert repr(boom) in records[0].getMessage()


@pytest.mark.parametrize("kind", ["omnigent", "timeout", "keyerror"])
async def test_context_tokens_none_on_each_read_error(tmp_path, caplog, kind):
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")
    boom = _read_error(kind)
    d = _failed_driver(tmp_path, _label_client(boom=boom))
    assert await d._context_tokens() is None
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert repr(boom) in records[0].getMessage()


@pytest.mark.parametrize("message", [None, 7, ["not delivered"], {"not delivered": True}])
async def test_resend_allowed_false_on_a_non_string_message(tmp_path, caplog, message):
    """Row 1 needs a *string* saying "not delivered"; any other message shape is
    not the undelivered signal. The guard decides — nothing is swallowed, so
    nothing is logged (a list/dict containing the phrase used to pass the `in`
    test and authorize a re-send)."""
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")
    d = _failed_driver(
        tmp_path,
        _label_client(
            {
                "omnigent.last_task_error_code": "runner_error",
                "omnigent.last_task_error_message": message,
            }
        ),
    )
    assert await d._resend_allowed() is False
    assert _driver_debug(caplog) == []


@pytest.mark.parametrize("value", ["lots", float("inf"), [1]])
async def test_context_tokens_none_on_a_garbage_label(tmp_path, caplog, value):
    """A token label of the wrong shape (ValueError / OverflowError / TypeError from
    `int()`) is "no cost signal", logged, not a crash of the capture."""
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")
    d = _failed_driver(tmp_path, _label_client({"omnigent.last_context_tokens": value}))
    assert await d._context_tokens() is None
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert "Error" in records[0].getMessage()


async def test_label_reads_fall_back_on_an_overflowing_session_field(tmp_path):
    """`Session.from_dict`'s `int(raw["created_at"])` raises OverflowError on
    `1e400` (parsed as inf) — a schema-drift shape, still an unreadable label."""
    # raw bytes: `httpx.Response(json=...)` would refuse to encode inf itself, and the
    # test would pass for the wrong reason (a ValueError before the SDK ever parses)
    body = (
        b'{"id":"c","agent_id":"a","status":"idle","created_at":1e400,"updated_at":0,'
        b'"title":null,"items":[],"pending_inputs":[],"labels":{}}'
    )
    d = _failed_driver(
        tmp_path,
        _real_sdk_client(
            lambda req: httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        ),
    )
    assert await d._resend_allowed() is False
    assert await d._context_tokens() is None


async def test_label_reads_do_not_paper_over_a_non_dict_labels(tmp_path):
    """The SDK always hands a dict (`Session.from_dict` coerces); `labels=None`
    is not an SDK shape, so the `AttributeError` from `.get` is our bug and
    propagates — no `or {}` in either read hides it."""

    async def get(session_id):
        return SimpleNamespace(id=session_id, labels=None)

    d = _failed_driver(tmp_path, SimpleNamespace(sessions=SimpleNamespace(get=get)))
    with pytest.raises(AttributeError):
        await d._resend_allowed()
    with pytest.raises(AttributeError):
        await d._context_tokens()


@pytest.mark.parametrize(
    "handler",
    [
        lambda req: httpx.Response(503, json={}),
        lambda req: httpx.Response(200, headers={"content-type": "text/html"}, text="<html>"),
        lambda req: httpx.Response(200, json={"labels": {}}),  # no Session fields
    ],
    ids=["503", "html-200", "no-session-fields"],
)
async def test_label_reads_fall_back_through_the_real_sdk(tmp_path, handler):
    d = _failed_driver(tmp_path, _real_sdk_client(handler))
    assert await d._resend_allowed() is False
    assert await d._context_tokens() is None


async def test_context_tokens_none_on_a_503_carrying_the_label(tmp_path):
    """An error response is not a reading, even when its body carries the label."""
    body = _session_body({"omnigent.last_context_tokens": "123"})
    d = _failed_driver(tmp_path, _real_sdk_client(lambda req: httpx.Response(503, json=body)))
    assert await d._context_tokens() is None


@pytest.mark.parametrize("labels", [[], ["x"], "", 0, None, ABSENT], ids=repr)
async def test_resend_allowed_true_when_the_sdk_coerces_labels(tmp_path, labels):
    """A non-dict / absent `labels` is `{}` before the driver sees it — the
    coercion is `Session.from_dict`'s, not ours — so row 3 applies: no error
    label, the sim/judge re-send is allowed."""
    body = _session_body(labels)
    d = _failed_driver(tmp_path, _real_sdk_client(lambda req: httpx.Response(200, json=body)))
    assert await d._resend_allowed() is True


async def test_resend_allowed_logs_the_swallowed_error(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")
    d = _failed_driver(tmp_path, _label_client(boom=httpx.ConnectError("transport gone")))
    assert await d._resend_allowed() is False
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert "transport gone" in records[0].getMessage()


async def test_context_tokens_logs_the_swallowed_error(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")
    d = _failed_driver(tmp_path, _label_client(boom=httpx.ConnectError("transport gone")))
    assert await d._context_tokens() is None
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert "transport gone" in records[0].getMessage()


async def test_pane_tail_logs_the_swallowed_error(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")

    class _Http:
        async def get(self, url):
            raise OSError("runner offline")

    d = OmnigentDriver(run_dir=tmp_path)
    d._chat = SimpleNamespace(session_id="conv_x")
    d._http = _Http()
    assert await d._pane_tail() is None
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert "runner offline" in records[0].getMessage()


async def test_close_logs_the_swallowed_error(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="flowbench.driver.omnigent")

    class _Boom:
        async def aclose(self):
            raise RuntimeError("already gone")

    d = OmnigentDriver(run_dir=tmp_path)
    d._http, d._client = _Boom(), None
    await d.close()
    records = _driver_debug(caplog)
    assert len(records) == 1
    assert "already gone" in records[0].getMessage()


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
    from flowbench.driver.omnigent import _now

    await d._send_once("hi", _now() + 0.01)
    assert d._captured == [{"__type__": "_Delta", "conversation_id": "conv_xyz"}]
    assert d.conversation_url() == f"{d.server_url}/c/conv_xyz"


async def test_capture_session_returns_the_run_fields(tmp_path):
    (tmp_path / "plan.md").write_text("# the plan\n")
    chat = _FakeChat([TurnStatus.IDLE])
    d = _settle_driver(tmp_path, chat, [[_USER, _USER, _REPLY]])
    d._client.sessions._labels = {"omnigent.last_context_tokens": "1234"}

    out = await d.capture_session()

    assert out["items"] == [_USER, _REPLY]  # deduped
    assert out["context_tokens"] == 1234
    assert not {"artifact_exists", "artifact_path", "artifact_text"} & out.keys()
    assert (out["model"], out["driver"]) == (d.model, "omnigent")
    assert out["session_id"] == "conv_test"
    assert isinstance(out["duration_s"], float)


async def test_close_swallows_a_failing_client(tmp_path):
    """Teardown must never mask the real error that got us here."""

    class _Boom:
        async def aclose(self):
            raise RuntimeError("already gone")

    d = OmnigentDriver(run_dir=tmp_path)
    d._http, d._client = _Boom(), None
    await d.close()
    assert d._closed is True
