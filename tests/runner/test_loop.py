"""DONE-token loop, offline: a fake driver replays turns, a stub model simulates
the user. Asserts the loop answers, stops on the DONE token, respects max_turns,
and bails on a failed status. The @solver wrapper is exercised live (Task 7)."""

from flowbench.runner.driver import AgentDriver, TurnResult
from flowbench.runner.loop import _is_done, next_user_message, render_tail, run_agent_session
from scenarios.coding_workflow.cases.todo_app import task


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


async def test_loop_feeds_growing_context_to_simulator():
    # the simulator's prompt on turn 2 must contain BOTH the first prompt and the
    # agent's first answer — proving accumulated context, not just the latest line.
    turns = [
        TurnResult("idle", "what storage should I use?", False),
        TurnResult("idle", "done, tests pass", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a JSON file", task.DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=10,
        deadline_s=999,
    )
    # second simulator call sees the full conversation tail
    second = user.seen[1]
    assert task.FIRST_PROMPT in second
    assert "what storage should I use?" in second
    assert "a JSON file" in second  # its own prior reply, in context


async def test_next_user_message_passes_system_and_transcript():
    stub = _StubModel(["What storage should I use?"])
    msg = await next_user_message("agent asked: storage?", task.simulator_system(), stub)
    assert msg == "What storage should I use?"
    assert "ENVISIONED SHAPE" in stub.seen[0]  # simulator system embedded
    assert "agent asked: storage?" in stub.seen[0]  # transcript tail passed


def test_is_done_tolerates_wrapped_token():
    # M1: claude -p may wrap the token; bare equality is too strict.
    assert _is_done("<<DONE>>", task.DONE_TOKEN)
    assert _is_done("Looks good. `<<DONE>>`", task.DONE_TOKEN)
    assert _is_done("  <<DONE>>  ", task.DONE_TOKEN)
    assert not _is_done("not done yet, keep going", task.DONE_TOKEN)
    # a long message that merely mentions the token in prose is not a stop signal
    assert not _is_done("x" * 200 + " <<DONE>> " + "y" * 200, task.DONE_TOKEN)


async def test_loop_answers_then_stops_on_done_token():
    turns = [
        TurnResult("idle", "What should I store tasks in?", False),
        TurnResult("idle", "Design approved? I built it and tests pass.", True),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["Use a JSON file at ./tasks.json", task.DONE_TOKEN])
    session = await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=10,
        deadline_s=999,
    )
    assert driver.started and driver.closed
    assert driver.sent[0] == task.FIRST_PROMPT
    assert "tasks.json" in driver.sent[1]
    assert len(user.seen) == 2  # answered once, then said DONE
    assert session["items"] == []


async def test_loop_canned_nudges_self_wait_without_simulator():
    # Agent parks on its own background sub-agent: idle, child_busy, no question.
    # The loop must nudge with a free "Continue." and NOT call the simulator. Once
    # the child settles (child_busy False) the simulator runs and can say DONE.
    turns = [
        TurnResult("idle", "Task 1 implementer running in the background", False, child_busy=True),
        TurnResult("idle", "still running, I'll proceed when it reports", False, child_busy=True),
        TurnResult("idle", "Task 1 done. App complete, tests pass.", True, child_busy=False),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel([task.DONE_TOKEN])  # only consulted once, at the end
    await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=10,
        deadline_s=999,
    )
    assert driver.sent == [task.FIRST_PROMPT, "Continue.", "Continue."]
    assert len(user.seen) == 1  # simulator NOT burned on the 2 self-waits
    assert driver.closed


async def test_loop_forces_simulator_when_child_looks_stuck_busy():
    # Safeguard: if a child never reports busy=False (capture race), the loop must
    # not canned-nudge forever — after _MAX_CONSEC_NUDGES it forces a simulator turn
    # so DONE is still reachable.
    from flowbench.runner.loop import _MAX_CONSEC_NUDGES

    stuck = TurnResult("idle", "still working in the background", False, child_busy=True)
    driver = _FakeDriver([stuck], {"items": []})  # every turn looks busy, no question
    user = _StubModel([task.DONE_TOKEN])  # forced call ends the run
    await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=50,
        deadline_s=999,
    )
    # first_prompt + exactly _MAX_CONSEC_NUDGES canned nudges, then simulator -> DONE
    assert driver.sent == [task.FIRST_PROMPT] + ["Continue."] * _MAX_CONSEC_NUDGES
    assert len(user.seen) == 1
    assert driver.closed


async def test_loop_simulates_when_agent_asks_even_if_child_busy():
    # A real question must reach the simulator even while a sub-agent is busy —
    # the canned path only swallows non-question self-waits.
    turns = [
        TurnResult("idle", "Which storage format — json or sqlite?", False, child_busy=True),
        TurnResult("idle", "built it.", True, child_busy=False),
    ]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["a JSON file", task.DONE_TOKEN])
    await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=10,
        deadline_s=999,
    )
    assert "json" in driver.sent[1].lower()  # the simulator's answer, not a canned nudge
    assert len(user.seen) == 2


async def test_loop_stops_at_max_turns():
    turns = [TurnResult("idle", "another question?", False)]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["keep going"])  # never says DONE
    await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=3,
        deadline_s=999,
    )
    assert len(driver.sent) == 1 + 3  # first prompt + 3 simulated turns
    assert driver.closed


async def test_loop_bails_on_failed_status():
    turns = [TurnResult("failed", "", False)]
    driver = _FakeDriver(turns, {"items": []})
    user = _StubModel(["unused"])
    await run_agent_session(
        driver,
        user,
        first_prompt=task.FIRST_PROMPT,
        simulator_system=task.simulator_system(),
        done_token=task.DONE_TOKEN,
        max_turns=5,
        deadline_s=999,
    )
    assert user.seen == []  # never simulated
    assert driver.closed
