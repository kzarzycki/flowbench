"""The in-repo case through real discovery: its shape, its `setup`, and the
grader seam its `score` hangs on. Discovery execs `case.py` as its own module,
so the loaded class is never the imported one: assert by name and behaviour."""

import json
import shutil
import subprocess
from pathlib import Path

from flowbench.case import load_case
from scenarios.coding_workflow import scenario
from scenarios.coding_workflow.cases.todo_app.fixtures import sessions

FIX = Path(__file__).parents[3] / "scenarios/coding_workflow/cases/todo_app/fixtures"


class _CannedGrader:
    def __init__(self, reply):
        self.reply = reply
        self.closed = False

    async def generate(self, prompt):
        class _Out:
            completion = self.reply

        return _Out()

    async def close(self):
        self.closed = True


def test_discovery_finds_the_case_and_its_shape():
    case = load_case(scenario.CASE_DIR("todo_app"))

    assert type(case).__name__ == "TodoAppCase"
    assert case.name == "todo_app"
    assert case.deliverable is None  # the running app is the deliverable, judged black-box
    assert case.deadline_s == 3600.0
    assert case.max_turns == 80
    assert case.has_score_override() is True
    assert case.judge_path.exists() is False  # no comparative judge: each flow scored on its own
    assert case.validate() == ["baseline", "superpowers"]


async def test_todo_app_case_setup_git_inits_the_flow_dir(tmp_path):
    case = load_case(scenario.CASE_DIR("todo_app"))
    flow_dir = tmp_path / "superpowers"
    flow_dir.mkdir()

    await case.setup({"name": "superpowers"}, flow_dir)

    assert (flow_dir / ".git").is_dir()
    log = subprocess.run(
        ["git", "-C", str(flow_dir), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "initial commit" in log.stdout
    await case.setup({"name": "superpowers"}, flow_dir)  # idempotent: a re-run must not fail


async def test_todo_app_case_score_goes_through_the_grader_factory(tmp_path, monkeypatch):
    case = load_case(scenario.CASE_DIR("todo_app"))
    flow_dir = tmp_path / "superpowers"
    shutil.copytree(FIX / "good_app", flow_dir)
    grader = _CannedGrader(
        '{"shape_fit":0.9,"clarifying_quality":0.8,"workflow_adherence":0.9,"rationale":"solid"}'
    )
    monkeypatch.setattr(type(case), "grader_factory", lambda flow_dir, **kw: grader)

    card = await case.score(
        {"name": "superpowers", "harness": "claude-native", "skills": "none", "skill_dirs": []},
        flow_dir,
        sessions.FULL_WORKFLOW,
    )

    assert card["objective"]["acceptance"] == 1.0
    assert card["judge_low_confidence"]["shape_fit"] == 0.9
    assert grader.closed is True
    assert json.loads((flow_dir / "acceptance.json").read_text())["score"] == 1.0
