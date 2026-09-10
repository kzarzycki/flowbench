"""`scenarios/smoke/hello` — the smallest case that still exercises the whole
engine: one flow, one deliverable, one simulator relay, and the case's own
`score`. Offline throughout (the three omnigent factories are doubles over
`flowbench.testing`), so this doubles as the end-to-end guard that
`flowbench run` → `compare` → `watch` still work over one run dir.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowbench.case import load_case
from flowbench.cli import app
from flowbench.flowspec import load_flows
from flowbench.loop import DONE_TOKEN
from flowbench.testing import FakeDriver, StubSim
from flowbench.types import TurnResult, TurnStatus

CASE_DIR = Path(__file__).parents[3] / "scenarios" / "smoke" / "hello"
FILES = ("task.md", "simulator.md", "knowledge.md", "flows.yaml", "case.py")
FLOW = {"name": "baseline"}

ASKED = "Which file do you want, and what should the line say?"
WROTE = "Wrote it."
ANSWER = "Call it hello.txt, one line: Hello, world!"

runner = CliRunner()  # typer 0.27 always splits stdout/stderr — no mix_stderr kwarg


class HelloDriver(FakeDriver):
    """A flow that asks for the file name and the line before writing anything,
    so a run only reaches the deliverable if the simulator was primed AND
    relayed to. `FakeDriver`'s own single `plan.md` at `start()` cannot express
    that."""

    def __init__(self, run_dir, *, text="Hello, world!\n"):
        super().__init__("", [], run_dir=run_dir)
        self._text = text

    async def start(self):
        Path(self._run_dir).mkdir(parents=True, exist_ok=True)

    async def send(self, prompt):
        self.sent.append(prompt)
        if len(self.sent) == 1:
            return TurnResult(TurnStatus.IDLE, ASKED)
        (Path(self._run_dir) / "hello.txt").write_text(self._text)
        return TurnResult(TurnStatus.IDLE, WROTE)


class RecordingSim(StubSim):
    """StubSim that keeps every prompt it was handed, so a test can tell the
    prime (persona + knowledge + how to end) from a relay (the delta alone)."""

    def __init__(self, replies):
        super().__init__(replies)
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return await super().generate(prompt)


def _doubles(sims, drivers):
    """The three factories, offline, collecting what they built."""

    def make_flow_driver(flow, flow_dir):
        drivers.append(HelloDriver(flow_dir))
        return drivers[-1]

    def make_simulator(flow, sim_dir):
        sims.append(RecordingSim([ANSWER]))  # then the done token, forever
        return sims[-1]

    async def run_judge(judge_md, entries, judge_dir):
        pytest.fail("the smoke case has no judge.md — nothing may call the judge")

    return make_flow_driver, make_simulator, run_judge


def test_case_files_and_shape():
    for name in FILES:
        assert (CASE_DIR / name).is_file(), name
    assert not (CASE_DIR / "judge.md").exists()  # one flow: score grades it

    case = load_case(CASE_DIR)
    # Discovery loads case.py by path, so the class is never the imported one:
    # assert by name and behaviour, never isinstance.
    assert type(case).__name__ == "HelloCase"
    assert case.name == "hello"
    assert case.deliverable == "hello.txt"
    assert (case.max_turns, case.deadline_s) == (4, 300.0)
    assert case.has_score_override()
    assert case.validate() == ["baseline"]

    (flow,) = load_flows(CASE_DIR / "flows.yaml")
    assert (flow["harness"], flow["model"]) == ("claude-native", "haiku")

    # the task withholds both facts and says to ask; knowledge.md holds them
    task = (CASE_DIR / "task.md").read_text().lower()
    assert "hello" not in task and ".txt" not in task
    assert "ask me" in task
    knowledge = (CASE_DIR / "knowledge.md").read_text()
    assert "hello.txt" in knowledge and "Hello, world!" in knowledge


def test_hello_runs_end_to_end_offline(tmp_path, monkeypatch):
    sims, drivers = [], []
    monkeypatch.setattr("flowbench.run.omni_factories", lambda case: _doubles(sims, drivers))
    monkeypatch.setattr("flowbench.watch.RunWatch._run_sessions", lambda self: [])
    runs_root = tmp_path / "runs"

    result = runner.invoke(
        app, ["run", str(CASE_DIR), "--runs-root", str(runs_root), "--run-id", "smoke-1"]
    )

    assert result.exit_code == 0, result.output
    run_root = runs_root / "hello" / "smoke-1"
    meta = json.loads((run_root / "run.json").read_text())
    assert meta["case"] == "hello"
    assert meta["deliverable"] == "hello.txt"
    assert meta["flows"] == ["baseline"]
    assert "scenario" not in meta

    # the prime carried the persona, the knowledge and the engine's done token;
    # the relay carried only the agent's new line — both reached the simulator.
    (sim,) = sims
    prime, relay = sim.prompts
    assert "role-playing" in prime and DONE_TOKEN in prime
    assert "hello.txt" in prime  # knowledge.md rode in behind the persona
    assert relay == f"[assistant] {WROTE}"

    session = json.loads((run_root / "baseline" / "session.json").read_text())
    assert session["ended_by"] == "done"
    assert session["artifact_exists"] is True
    assert (run_root / "baseline" / "hello.txt").read_text() == "Hello, world!\n"
    card = json.loads((run_root / "baseline" / "scorecard.json").read_text())
    assert card["objective"]["acceptance"] == 1.0

    compared = runner.invoke(
        app, ["compare", "--run-base", str(runs_root / "hello"), "--run-id", "smoke-1"]
    )
    assert compared.exit_code == 0, compared.output
    assert "| metric | baseline |" in compared.stdout
    assert "| acceptance | 1.0 |" in compared.stdout

    watched = runner.invoke(app, ["watch", "smoke-1", "--runs-root", str(runs_root)])
    assert watched.exit_code == 0, watched.output
    assert watched.stdout.startswith("RUN COMPLETE: ")


@pytest.mark.parametrize("text", ["Hello, world!\n", "HELLO, WORLD!", "well, hello you"])
async def test_score_accepts_the_word_in_any_case(text):
    card = await load_case(CASE_DIR).score(
        FLOW, Path("."), {"artifact_exists": True, "artifact_text": text}
    )

    assert card["objective"]["acceptance"] == 1.0
    assert card["deliverable"] == {"name": "hello.txt", "exists": True, "greets": True}


@pytest.mark.parametrize(
    "session",
    [
        {"artifact_exists": False, "artifact_text": None},  # never written
        {"artifact_exists": True, "artifact_text": "Goodbye."},  # wrong content
        {"artifact_exists": True, "artifact_text": None},  # an empty file, or a dir
    ],
)
async def test_score_reports_a_missing_or_wrong_file(session):
    card = await load_case(CASE_DIR).score(FLOW, Path("."), session)

    assert card["objective"]["acceptance"] == 0.0
    assert card["deliverable"]["greets"] is False
    assert card["deliverable"]["exists"] is session["artifact_exists"]
