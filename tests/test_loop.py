"""DONE-token loop, offline: a fake driver replays turns, a stub model simulates
the user. Asserts the loop answers, stops on the DONE token, respects max_turns,
and bails on a failed status."""

import asyncio
import dataclasses
import time
from pathlib import Path

import pytest

from flowbench.driver import AgentDriver, TurnResult
from flowbench.loop import (
    DONE_TOKEN,
    END_INSTRUCTION,
    _is_done,
    prime_prompt,
    relay_prompt,
    render_tail,
    run_agent_session,
)
from flowbench.types import TurnStatus

REPO_ROOT = Path(__file__).resolve().parents[1]

# Inline fixture data: an engine test must not depend on a scenario (decision 14,
# flowbench issue #2 / S01.3) — these used to be scenarios.coding_workflow.cases.
# todo_app.task's FIRST_PROMPT/simulator_system(), which the loop never inspects
# beyond the DONE token and a "primed vs. relayed" text diff. The persona names
# no token: the engine owns it and appends the end instruction at prime time.
FIRST_PROMPT = "I want a command-line todo app in Python."
SIM_SYSTEM = (
    "You are role-playing a USER who wants a todo app built.\n\n"
    "ENVISIONED SHAPE: a Python CLI todo app.\n\n"
    "Answer only what the agent asks, in one short sentence."
)


class _StubModel:
    """Returns scripted replies in order; records prompts seen."""

    def __init__(self, replies):
        self.replies, self.seen, self._i = list(replies), [], 0

    async def generate(self, prompt):
        self.seen.append(prompt)
        r = self.replies[min(self._i, len(self.replies) - 1)]
        self._i += 1

        class _Out:
            completion = r

        return _Out()


class _FakeDriver(AgentDriver):
    def __init__(self, turns, session):
        self._turns, self._session = turns, session
        self.sent, self.started, self.closed, self._i = [], False, False, 0

    async def start(self):
        self.started = True

    async def send(self, text):
        self.sent.append(text)
        r = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return r

    async def capture_session(self):
        return dict(self._session)

    async def close(self):
        self.closed = True


def test_render_tail_gives_simulator_multi_turn_context():
    # bug 2: the simulator was fed only the agent's latest line, lost the thread,
    # and re-introduced the task / emitted filler. render_tail gives it the last
    # N labelled exchanges so it can reply in context.
    convo = [
        ("user", "build a todo app"),
        ("assistant", "what storage?"),
        ("user", "JSON file"),
        ("assistant", "building now"),
    ]
    tail = render_tail(convo, n=8)
    assert tail == (
        "[user] build a todo app\n[assistant] what storage?\n"
        "[user] JSON file\n[assistant] building now"
    )


def test_render_tail_caps_to_last_n():
    convo = [("user", str(i)) for i in range(20)]
    tail = render_tail(convo, n=3)
    assert tail == "[user] 17\n[user] 18\n[user] 19"


async def test_loop_primes_simulator_once_then_relays_deltas():
    # The simulator is a stateful session: its FIRST prompt carries the persona +
    # conversation so far; every later prompt is ONLY the delta since its last
    # reply. Re-sending system+tail each turn cost quadratic tokens (seen live).
    turns = [
        TurnResult(TurnStatus.IDLE, "what storage should I use?"),
        TurnResult(TurnStatus.IDLE, "and what file name?"),
        TurnResult(TurnStatus.IDLE, "done, tests pass", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a JSON file", "tasks.json", DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    first, second, third = user.seen
    # prime: persona + context
    assert "ENVISIONED SHAPE" in first
    assert FIRST_PROMPT in first
    assert "what storage should I use?" in first
    # relays: delta only — no persona, no re-sent history
    for later in (second, third):
        assert "ENVISIONED SHAPE" not in later
        assert FIRST_PROMPT not in later
    assert "and what file name?" in second
    assert "a JSON file" not in second  # its own prior reply is not re-relayed
    assert "done, tests pass" in third
    assert "and what file name?" not in third  # relayed once, never again


@pytest.mark.parametrize("flaked_index", [0, 1])
async def test_loop_continues_past_a_flaked_idle_turn_and_counts_it(flaked_index):
    # a flaked turn (driver already resolved FAILED-after-reply-landed to IDLE,
    # flaked=True) is a normal idle turn to the loop — it just counts it. The
    # flaked_index=0 case is the uninitialized-counter trap: `flaked` must exist
    # before the FIRST send, not only inside the in-loop send.
    turns = [
        TurnResult(TurnStatus.IDLE, "q?"),
        TurnResult(TurnStatus.IDLE, "done", True),
    ]
    turns[flaked_index] = dataclasses.replace(turns[flaked_index], flaked=True)
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["some reply", DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert session["exit_status"] == TurnStatus.IDLE
    assert session["flaked_turns"] == 1
    assert session["turns"] == 1


async def test_relay_advances_even_when_simulator_says_continue():
    # todo-app-004: the sim's literal "Continue." matched the old nudge sentinel,
    # so sim_seen froze and every later relay resent the whole backlog (quadratic)
    turns = [
        TurnResult(TurnStatus.IDLE, "Task 1 implementer running"),
        TurnResult(TurnStatus.IDLE, "Task 1 done, on to Task 2"),
        TurnResult(TurnStatus.IDLE, "all done", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["Continue.", "Continue.", DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    _, second, third = user.seen
    assert "Task 1 done" in second
    assert "Task 1 implementer running" not in second
    assert "Task 1 done" not in third and "Task 1 implementer running" not in third


def test_is_done_tolerates_wrapped_token():
    # M1: claude -p may wrap the token; bare equality is too strict.
    assert _is_done("<<DONE>>", DONE_TOKEN)
    assert _is_done("Looks good. `<<DONE>>`", DONE_TOKEN)
    assert _is_done("  <<DONE>>  ", DONE_TOKEN)
    assert not _is_done("not done yet, keep going", DONE_TOKEN)
    # a long message that merely mentions the token in prose is not a stop signal
    assert not _is_done("x" * 200 + " <<DONE>> " + "y" * 200, DONE_TOKEN)


async def test_loop_answers_then_stops_on_done_token():
    turns = [
        TurnResult(TurnStatus.IDLE, "What should I store tasks in?"),
        TurnResult(TurnStatus.IDLE, "Design approved? I built it and tests pass.", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["Use a JSON file at ./tasks.json", DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert driver.started and driver.closed
    assert driver.sent[0] == FIRST_PROMPT
    assert "tasks.json" in driver.sent[1]
    assert len(user.seen) == 2  # answered once, then said DONE
    assert session["items"] == []
    assert session["flaked_turns"] == 0


async def test_loop_stops_at_max_turns():
    turns = [TurnResult(TurnStatus.IDLE, "another question?")]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["keep going"])  # never says DONE
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=3,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert len(driver.sent) == 1 + 3  # first prompt + 3 simulated turns
    assert driver.closed


async def test_loop_bails_on_failed_status():
    turns = [TurnResult(TurnStatus.FAILED, "")]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["unused"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert user.seen == []  # never simulated
    assert driver.closed
    # the non-idle exit is recorded, not silent (live-001 shipped a timeout invisibly)
    assert session["exit_status"] == TurnStatus.FAILED
    assert session["turns"] == 0


async def test_loop_stops_on_quota():
    # #131: the second turn hits the subscription wall — the loop ends the session
    # with exit_status "quota" and never asks the simulator again
    banner = "You've hit your session limit · resets 6:40pm (Europe/Zurich)"
    turns = [TurnResult(TurnStatus.IDLE, "what shape?"), TurnResult(TurnStatus.QUOTA, banner)]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a CLI", "never relayed"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert len(user.seen) == 1
    assert driver.sent == [FIRST_PROMPT, "a CLI"]
    assert session["exit_status"] == TurnStatus.QUOTA
    assert session["turns"] == 1
    assert driver.closed


async def test_done_waits_for_pending_artifact(monkeypatch, tmp_path):
    # the agent may claim DONE while its Write is still flushing — the loop
    # grace-polls artifact_probe() before capturing (plan.md landed post-capture live)
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("plan")
    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        return plan_path if calls["n"] >= 3 else None

    async def _nosleep(_s):
        return None

    monkeypatch.setattr("flowbench.loop.asyncio.sleep", _nosleep)
    driver = _FakeDriver([TurnResult(TurnStatus.IDLE, "the plan is complete")], {"items": []})
    user = _StubModel([DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=10,
        artifact_probe=probe,
    )
    assert calls["n"] >= 3  # kept polling until the artifact appeared
    assert driver.closed
    assert session["artifact_exists"] is True
    assert session["artifact_path"] == str(plan_path)
    assert session["artifact_text"] == "plan"


async def test_done_grace_poll_is_bounded_by_wall_clock():
    # a hung filesystem must not hang the run: the grace-poll is bounded by
    # artifact_grace_s wall-clock, not by a call count.
    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(1.0)
        return None

    driver = _FakeDriver([TurnResult(TurnStatus.IDLE, "the plan is complete")], {"items": []})
    user = _StubModel([DONE_TOKEN])
    start = time.monotonic()
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0.1,
        artifact_probe=probe,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 1.0
    assert session["artifact_exists"] is False


async def test_no_probe_skips_poll_and_reports_no_artifact(monkeypatch):
    sleeps = []

    async def _record_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr("flowbench.loop.asyncio.sleep", _record_sleep)
    driver = _FakeDriver([TurnResult(TurnStatus.IDLE, "the plan is complete")], {"items": []})
    user = _StubModel([DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=10,
    )
    assert sleeps == []
    assert session["artifact_exists"] is False
    assert session["artifact_path"] is None
    assert session["artifact_text"] is None


async def test_loop_records_stall_reason_and_pane(monkeypatch):
    # #54: a stalled first turn stops the loop and lands what the agent waits on
    turns = [TurnResult(TurnStatus.STALLED, "", stall_reason="prompt", pane_tail="❯ y/n?")]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["unused"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert user.seen == []
    assert session["exit_status"] == TurnStatus.STALLED
    assert session["stall_reason"] == "prompt"
    assert session["pane_tail"] == "❯ y/n?"


# --- S03.2: engine-owned done token, `ended_by`, directory deliverables -------


def test_prime_prompt_carries_the_end_instruction():
    # The engine owns the token, so the persona never names it: the end
    # instruction is appended once, at prime time, AFTER the persona (the
    # simulator reads its role first, then how to stop). Relays are pure delta —
    # repeating the instruction every turn is what the prime/relay split avoids.
    convo = [("user", FIRST_PROMPT), ("assistant", "what storage?")]
    primed = prime_prompt(SIM_SYSTEM, convo)

    assert END_INSTRUCTION in primed
    assert primed.count(END_INSTRUCTION) == 1
    assert primed.count(DONE_TOKEN) == 1  # named by the instruction, nowhere else
    assert primed.index("ENVISIONED SHAPE") < primed.index(END_INSTRUCTION)
    assert primed.index(END_INSTRUCTION) < primed.index(FIRST_PROMPT)

    relayed = relay_prompt(convo, 1)
    assert END_INSTRUCTION not in relayed
    assert DONE_TOKEN not in relayed


async def test_ended_by_done():
    turns = [
        TurnResult(TurnStatus.IDLE, "what storage?"),
        TurnResult(TurnStatus.IDLE, "built it, tests pass"),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a JSON file", DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert session["ended_by"] == "done"
    assert session["exit_status"] == TurnStatus.IDLE
    assert session["turns"] == 1


async def test_ended_by_max_turns():
    # 50 of 69 recorded flow sessions ended `idle` and the record could not say
    # whether the simulator ended them or the cap did. It can now.
    driver = _FakeDriver([TurnResult(TurnStatus.IDLE, "another question?")], {"items": []})
    user = _StubModel(["keep going"])  # never says DONE
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=2,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert session["ended_by"] == "max_turns"
    assert session["exit_status"] == TurnStatus.IDLE  # a healthy agent, just capped
    assert session["turns"] == 2


async def test_ended_by_deadline():
    # the wall-clock backstop, mid-conversation: the cap is nowhere near and the
    # agent is idle and healthy, so only the elapsed budget explains the exit.
    class _SlowDriver(_FakeDriver):
        async def send(self, text):
            result = await super().send(text)
            if len(self.sent) > 1:
                await asyncio.sleep(0.08)
            return result

    driver = _SlowDriver([TurnResult(TurnStatus.IDLE, "still a question?")], {"items": []})
    user = _StubModel(["keep going"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=50,
        deadline_s=0.05,
        artifact_grace_s=0,
    )
    assert session["ended_by"] == "deadline"
    assert session["exit_status"] == TurnStatus.IDLE
    assert session["turns"] == 1  # not the cap, and the simulator never said DONE


@pytest.mark.parametrize(
    "status,expected",
    [
        (TurnStatus.FAILED, "failed"),
        (TurnStatus.QUOTA, "quota"),
        # an undocumented server status passes through verbatim (types.py: the
        # status is `TurnStatus | str`, so this arrives as a bare string)
        ("wedged", "wedged"),
    ],
)
async def test_ended_by_terminal_status(status, expected):
    driver = _FakeDriver([TurnResult(status, "")], {"items": []})
    user = _StubModel(["unused"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert user.seen == []
    assert session["ended_by"] == expected
    # a StrEnum member must land as its plain string, not "TurnStatus.FAILED"
    assert type(session["ended_by"]) is str


async def test_ended_by_terminal_status_beats_done():
    # the simulator said DONE on turn 1, then the agent's next turn crashed: a
    # crashed session is not a completed one, so the status wins.
    turns = [TurnResult(TurnStatus.IDLE, "what storage?"), TurnResult(TurnStatus.FAILED, "")]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a JSON file", DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert session["ended_by"] == "failed"


async def test_directory_deliverable_is_present_with_no_text(tmp_path):
    # a case whose deliverable is a folder (dwh_migration's ported project):
    # presence is the probe's answer, and `.read_text()` on a directory used to
    # raise IsADirectoryError right after DONE. Presence is `artifact_exists`
    # everywhere — never the truthiness of `artifact_text`.
    deliverable = tmp_path / "ported"
    deliverable.mkdir()
    (deliverable / "dim_customer.sql").write_text("select 1")

    driver = _FakeDriver([TurnResult(TurnStatus.IDLE, "ported it")], {"items": []})
    user = _StubModel([DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
        artifact_probe=lambda: deliverable,
    )
    assert session["ended_by"] == "done"
    assert session["artifact_exists"] is True
    assert session["artifact_path"] == str(deliverable)
    assert session["artifact_text"] is None


def test_no_simulator_names_a_done_token():
    # the token is the engine's, appended at prime time; a persona that also
    # names one can only contradict it. Each simulator.md says what "delivered"
    # means for its case, in its own words.
    simulators = [
        p
        for p in REPO_ROOT.rglob("simulator.md")
        if not any(part in {".git", ".venv", "runs"} for part in p.parts)
    ]
    assert simulators, "no simulator.md found — the glob is wrong, not the repo clean"
    for path in simulators:
        text = path.read_text()
        assert DONE_TOKEN not in text, path
