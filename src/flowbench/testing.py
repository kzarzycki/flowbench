"""Test doubles for the flowbench runtime — offline stand-ins for the three
omnigent factories (`make_flow_driver`, `make_simulator`, `run_judge`) that
`run_case`/`run_case_n` accept, so the whole pipeline is unit-tested without a
live omnigent server."""

from __future__ import annotations

from pathlib import Path

from flowbench.driver import AgentDriver
from flowbench.loop import DONE_TOKEN
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
    plan to `run_dir/plan.md` on disk (like a real driver would) when `run_dir`
    is given, so a case declaring `plan.md` finds one."""

    def __init__(self, plan_text, questions, run_dir=None):
        self._plan = plan_text
        self._questions = list(questions)
        self._run_dir = run_dir
        self.sent = []
        self.closed = False

    async def start(self):
        if self._run_dir is not None:
            Path(self._run_dir).mkdir(parents=True, exist_ok=True)
            (Path(self._run_dir) / "plan.md").write_text(self._plan or "")

    async def send(self, text):
        self.sent.append(text)
        if self._questions:
            return TurnResult(TurnStatus.IDLE, self._questions.pop(0))
        return TurnResult(TurnStatus.IDLE, "The plan is complete and written to plan.md.")

    async def capture_session(self):
        items = [{"type": "message", "role": "user", "content": s} for s in self.sent]
        items.append({"type": "message", "role": "assistant", "content": "plan written"})
        return {"items": items, "events": []}

    async def close(self):
        self.closed = True


class MissingPlanDriver(FakeDriver):
    """Reports the plan complete but never produced an artifact (flow crashed):
    `start()` writes nothing, so the deliverable probe never finds a plan."""

    async def start(self):
        pass

    async def capture_session(self):
        items = [{"type": "message", "role": "user", "content": s} for s in self.sent]
        items.append({"type": "message", "role": "assistant", "content": "no plan"})
        return {"items": items, "events": []}


class StubSim:
    """Simulator fake: pops scripted replies, then keeps emitting the done token."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.closed = False

    async def generate(self, prompt):
        reply = self.replies.pop(0) if self.replies else DONE_TOKEN

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
            return FakeDriver("# SP plan\nunknown flag key returns 404.", [], run_dir=flow_dir)
        return FakeDriver("# plain plan\nno unknown-key note.", [], run_dir=flow_dir)

    def make_simulator(flow, sim_dir):
        return StubSim([DONE_TOKEN])

    async def run_judge(judge_md, entries, judge_dir):
        w = winners.pop(0)
        return f"Some prose about the plans.\nWINNER: {w}\nA: ok\nB: ok"

    return make_flow_driver, make_simulator, run_judge
