"""Test doubles for the flowbench runtime — offline stand-ins for the three
omnigent factories (`make_flow_driver`, `make_simulator`, `run_judge`) that
`run_case`/`run_case_n` accept, so the whole pipeline is unit-tested without a
live omnigent server."""

from __future__ import annotations

from flowbench.driver import AgentDriver
from flowbench.types import TurnResult, TurnStatus


class ScriptedDriver:
    """Duck-typed driver stub replaying scripted TurnResults."""

    def __init__(self, results):
        self.results = list(results)
        self.sent = []

    async def start(self):
        pass

    async def send(self, text):
        self.sent.append(text)
        return self.results.pop(0)

    async def close(self):
        pass


class FakeDriver(AgentDriver):
    """Replays scripted questions, then reports the plan complete; 'writes' the
    plan by returning it as capture_session()'s artifact_text."""

    def __init__(self, plan_text, questions):
        self._plan = plan_text
        self._questions = list(questions)
        self.sent = []
        self.closed = False

    async def start(self):
        pass

    async def send(self, text):
        self.sent.append(text)
        if self._questions:
            return TurnResult(TurnStatus.IDLE, self._questions.pop(0), False)
        return TurnResult(TurnStatus.IDLE, "The plan is complete and written to plan.md.", True)

    async def capture_session(self):
        items = [{"type": "message", "role": "user", "content": s} for s in self.sent]
        items.append({"type": "message", "role": "assistant", "content": "plan written"})
        return {"items": items, "events": [], "artifact_text": self._plan}

    def artifact_path(self):
        # Truthful for the grace-poll in run_agent_session: this fake's plan
        # "exists" (returned as artifact_text), so report a path. Fakes that
        # model a missing artifact override this back to None (issue #18).
        return "plan.md"

    async def close(self):
        self.closed = True


class MissingPlanDriver(FakeDriver):
    """Reports the plan complete but never produced an artifact (flow crashed).
    artifact_path stays None, so this fake pays run_agent_session's real
    artifact grace-poll (issue #18) — the one deliberately slow test."""

    async def capture_session(self):
        items = [{"type": "message", "role": "user", "content": s} for s in self.sent]
        items.append({"type": "message", "role": "assistant", "content": "no plan"})
        return {"items": items, "events": [], "artifact_text": None}

    def artifact_path(self):
        return None


class StubSim:
    """Simulator fake: pops scripted replies, then keeps emitting the done token."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.closed = False

    async def generate(self, prompt):
        reply = self.replies.pop(0) if self.replies else "PLAN_COMPLETE"

        class _Out:
            completion = reply

        return _Out()

    async def close(self):
        self.closed = True


def n_run_factories(judge_winners):
    """Factories for run_case_n tests; judge pops one scripted winner per trial."""
    winners = list(judge_winners)

    def make_flow_driver(flow, flow_dir):
        if flow["name"] == "superpowers":
            return FakeDriver("# SP plan\nunknown flag key returns 404.", [])
        return FakeDriver("# plain plan\nno unknown-key note.", [])

    def make_simulator(flow, sim_dir):
        return StubSim(["PLAN_COMPLETE"])

    async def run_judge(judge_md, entries, judge_dir):
        w = winners.pop(0)
        return f"Some prose about the plans.\nWINNER: {w}\nA: ok\nB: ok"

    return make_flow_driver, make_simulator, run_judge
