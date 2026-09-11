"""The in-repo case through real discovery: its layout, its shape, its `setup`,
and the grading body its `score` delegates to. Discovery execs `case.py` as its
own module, so the loaded class is never the imported one: assert by name and
behaviour."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from flowbench.case import load_case
from flowbench.settings import Settings
from scenarios.swe_e2e.cases.todo_app.case import make_grader_omni, score_todo_app
from scenarios.swe_e2e.cases.todo_app.fixtures import sessions

REPO_ROOT = Path(__file__).parents[3]
SCENARIO_DIR = REPO_ROOT / "scenarios" / "swe_e2e"
CASE_DIR = SCENARIO_DIR / "cases" / "todo_app"
FIX = CASE_DIR / "fixtures"


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


def test_the_case_dir_holds_only_content_and_case_py():
    for name in ("task.md", "simulator.md", "knowledge.md", "flows.yaml", "case.py"):
        assert (CASE_DIR / name).is_file(), name
    # the grading body folded into case.py: no scoring.py beside it
    assert not (CASE_DIR / "scoring.py").exists()
    assert score_todo_app.__module__.endswith("todo_app.case")
    assert make_grader_omni.__module__ == score_todo_app.__module__
    # the scenario is content plus that one case.py: no entrypoint, no scenario
    # module, and nothing left under the old name
    assert sorted(p.name for p in SCENARIO_DIR.glob("*.py")) == ["__init__.py"]
    assert not (REPO_ROOT / "scenarios" / "coding_workflow").exists()


def test_discovery_finds_the_case_and_its_shape():
    case = load_case(CASE_DIR)

    assert type(case).__name__ == "TodoAppCase"
    assert case.name == "todo_app"
    assert case.deliverable is None  # the running app is the deliverable, judged black-box
    assert case.deadline_s == 3600.0
    assert case.max_turns == 80
    assert case.has_score_override() is True
    assert case.judge_path.exists() is False  # no comparative judge: each flow scored on its own
    assert case.validate() == ["baseline", "superpowers"]


async def test_todo_app_case_setup_git_inits_the_flow_dir(tmp_path):
    case = load_case(CASE_DIR)
    flow_dir = tmp_path / "superpowers"
    flow_dir.mkdir()

    await case.setup({"name": "superpowers"}, flow_dir)

    assert (flow_dir / ".git").is_dir()
    log = subprocess.run(
        ["git", "-C", str(flow_dir), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
        # Scrub GIT_* the way git_init_repo does (#49): run from a git hook — the
        # pre-push suite — and an inherited GIT_DIR points this log at the outer
        # repo, which passes `check=True` and asserts against the wrong history.
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )
    assert "initial commit" in log.stdout
    await case.setup({"name": "superpowers"}, flow_dir)  # idempotent: a re-run must not fail


async def test_todo_app_case_score_uses_the_settings_judge_model(tmp_path, monkeypatch):
    case = load_case(CASE_DIR, settings=Settings(judge_model="haiku"))
    flow_dir = tmp_path / "superpowers"
    shutil.copytree(FIX / "good_app", flow_dir)
    grader = _CannedGrader('{"shape_fit":0.5,"rationale":"ok"}')
    seen = {}

    def _factory(flow_dir, **kw):
        seen.update(kw)
        return grader

    # At the class attribute, not the instance: `score` reads it through type(self)
    monkeypatch.setattr(type(case), "grader_factory", _factory)

    await case.score(
        {"name": "superpowers", "harness": "claude-native", "skills": "none", "skill_dirs": []},
        flow_dir,
        sessions.FULL_WORKFLOW,
    )

    assert seen == {"model": "haiku"}


async def test_todo_app_case_score_goes_through_the_grader_factory(tmp_path, monkeypatch):
    case = load_case(CASE_DIR)
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


async def test_score_todo_app_over_good_app_full_workflow(tmp_path):
    ws = tmp_path / "flow_dir"
    shutil.copytree(FIX / "good_app", ws)
    flow = {"name": "superpowers", "harness": "claude-native", "skills": "none", "skill_dirs": []}
    grader = _CannedGrader(
        '{"shape_fit":0.9,"clarifying_quality":0.8,"workflow_adherence":0.9,"rationale":"solid"}'
    )

    card = await score_todo_app(
        flow, ws, sessions.FULL_WORKFLOW, make_grader=lambda flow_dir: grader
    )

    assert card["objective"]["acceptance"] == 1.0
    assert card["objective"]["superpowers_used"] is True
    assert card["objective"]["brainstorming_used"] is True
    assert card["judge_low_confidence"]["shape_fit"] == 0.9
    assert grader.closed is True
    acc_on_disk = json.loads((ws / "acceptance.json").read_text())
    assert acc_on_disk["score"] == 1.0

    # AC5: frozen key set
    assert set(card) == {"flow", "objective", "heuristic", "judge_low_confidence", "session"}
    assert set(card["objective"]) == {
        "app_runs",
        "acceptance",
        "clarifying_coverage",
        "clarifying_asked",
        "superpowers_used",
        "brainstorming_used",
        "skills_invoked",
    }


async def test_score_todo_app_empty_grader_completion(tmp_path):
    ws = tmp_path / "flow_dir"
    shutil.copytree(FIX / "good_app", ws)
    flow = {"name": "baseline", "harness": "claude-native", "skills": "none"}
    grader = _CannedGrader("")

    card = await score_todo_app(
        flow, ws, sessions.SKIPPED_PHASES, make_grader=lambda flow_dir: grader
    )
    assert card["judge_low_confidence"] == {"error": "empty_grader_completion"}
    assert grader.closed is True


@pytest.mark.parametrize("trial", [None, "trial-01"])
def test_make_grader_omni_takes_the_model_and_the_new_labels(tmp_path, trial):
    run_root = tmp_path / "todo_app" / "run-1"
    if trial is not None:
        run_root = run_root / trial
    flow_dir = run_root / "superpowers"
    flow_dir.mkdir(parents=True)
    model = make_grader_omni(flow_dir, model="sonnet")
    d = model._driver
    assert d.run_dir == run_root / "_judge_superpowers"
    assert d.run_dir.is_dir()
    assert d.model == "sonnet"
    assert d.skills == "none"
    assert d.turn_timeout_s == 600
    # web-UI grouping: the grader lands in its run's folder, titled by case and flow
    assert d.project == "todo_app/run-1"
    prefix = f"todo_app · {trial}" if trial is not None else "todo_app"
    assert d.session_title == f"{prefix} · judge: superpowers"
