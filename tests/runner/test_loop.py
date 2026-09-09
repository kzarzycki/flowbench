"""DONE-token loop, offline: a fake driver replays turns, a stub model simulates
the user. Asserts the loop answers, stops on the DONE token, respects max_turns,
and bails on a failed status."""

from flowbench.runner.driver import AgentDriver, TurnResult
from flowbench.runner.loop import _is_done, render_tail, run_agent_session

# Inline fixture data: an engine test must not depend on a scenario (decision 14,
# flowbench issue #2 / S01.3) — these used to be scenarios.coding_workflow.cases.
# todo_app.task's FIRST_PROMPT/DONE_TOKEN/simulator_system(), which the loop
# never inspects beyond the DONE token and a "primed vs. relayed" text diff.
FIRST_PROMPT = "I want a command-line todo app in Python."
DONE_TOKEN = "<<DONE>>"
SIM_SYSTEM = (
    "You are role-playing a USER who wants a todo app built.\n\n"
    "ENVISIONED SHAPE: a Python CLI todo app.\n\n"
    f"Reply with EXACTLY `{DONE_TOKEN}` when the app is delivered and nothing else."
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

    def artifact_path(self):
        return None

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
        TurnResult("idle", "what storage should I use?", False),
        TurnResult("idle", "and what file name?", False),
        TurnResult("idle", "done, tests pass", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a JSON file", "tasks.json", DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
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


async def test_relay_advances_even_when_simulator_says_continue():
    # todo-app-004: the sim's literal "Continue." matched the old nudge sentinel,
    # so sim_seen froze and every later relay resent the whole backlog (quadratic)
    turns = [
        TurnResult("idle", "Task 1 implementer running", False),
        TurnResult("idle", "Task 1 done, on to Task 2", False),
        TurnResult("idle", "all done", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["Continue.", "Continue.", DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
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
        TurnResult("idle", "What should I store tasks in?", False),
        TurnResult("idle", "Design approved? I built it and tests pass.", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["Use a JSON file at ./tasks.json", DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
        max_turns=10,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert driver.started and driver.closed
    assert driver.sent[0] == FIRST_PROMPT
    assert "tasks.json" in driver.sent[1]
    assert len(user.seen) == 2  # answered once, then said DONE
    assert session["items"] == []


async def test_loop_stops_at_max_turns():
    turns = [TurnResult("idle", "another question?", False)]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["keep going"])  # never says DONE
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
        max_turns=3,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert len(driver.sent) == 1 + 3  # first prompt + 3 simulated turns
    assert driver.closed


async def test_loop_bails_on_failed_status():
    turns = [TurnResult("failed", "", False)]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["unused"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert user.seen == []  # never simulated
    assert driver.closed
    # the non-idle exit is recorded, not silent (live-001 shipped a timeout invisibly)
    assert session["exit_status"] == "failed"
    assert session["turns"] == 0


async def test_done_waits_for_pending_artifact(monkeypatch):
    # the agent may claim DONE while its Write is still flushing — the loop
    # grace-polls artifact_path() before capturing (plan.md landed post-capture live)
    class _LateArtifactDriver(_FakeDriver):
        def __init__(self, *a):
            super().__init__(*a)
            self.polls = 0

        def artifact_path(self):
            self.polls += 1
            return "plan.md" if self.polls >= 3 else None

    async def _nosleep(_s):
        return None

    monkeypatch.setattr("flowbench.runner.loop.asyncio.sleep", _nosleep)
    driver = _LateArtifactDriver([TurnResult("idle", "the plan is complete", False)], {"items": []})
    user = _StubModel([DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=10,
    )
    assert driver.polls >= 3  # kept polling until the artifact appeared
    assert driver.closed


async def test_loop_records_stall_reason_and_pane(monkeypatch):
    # #54: a stalled first turn stops the loop and lands what the agent waits on
    turns = [TurnResult("stalled", "", False, stall_reason="prompt", pane_tail="❯ y/n?")]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["unused"])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=FIRST_PROMPT,
        simulator_system=SIM_SYSTEM,
        done_token=DONE_TOKEN,
        max_turns=5,
        deadline_s=999,
        artifact_grace_s=0,
    )
    assert user.seen == []
    assert session["exit_status"] == "stalled"
    assert session["stall_reason"] == "prompt"
    assert session["pane_tail"] == "❯ y/n?"
