"""Scenario-side tests only: the CLI entrypoint's wiring + score_todo_app's
offline behavior. The runtime (run_case/run_case_n, SessionModel, factories,
report, watch) is tested in the engine (flowbench tests/)."""

import inspect
import json
import shutil
from pathlib import Path

import pytest

import flowbench.run as engine_run
from scenarios.coding_workflow.cases.todo_app.fixtures import sessions
from scenarios.coding_workflow.cases.todo_app.scoring import make_grader_omni, score_todo_app
from scenarios.coding_workflow.run import SCENARIO, default_runs_root, main

FIX = Path(__file__).parents[3] / "scenarios/coding_workflow/cases/todo_app/fixtures"


def test_default_runs_root_is_sibling_of_repo():
    p = default_runs_root()
    repo_root = Path(__file__).parents[3]
    assert p.parent.name == "flowbench-runs"
    assert p.name == "coding_workflow"
    assert p.parent.parent == repo_root.parent
    assert not p.is_relative_to(repo_root)


def test_main_wires_engine_run_case_n(monkeypatch, capsys, tmp_path):
    calls = []

    async def fake_run_case_n(case, **kw):
        # bind against the real signature so a misspelled/extra kwarg fails here, not live
        inspect.signature(engine_run.run_case_n).bind(case, **kw)
        calls.append((case, kw))
        return {"run_root": str(tmp_path), "trials": [{"x": 1}], "aggregate": {"n": kw["n"]}}

    monkeypatch.setattr("scenarios.coding_workflow.run.run_case_n", fake_run_case_n)
    monkeypatch.setattr("sys.argv", ["run", "--run-id", "r1", "--deadline-s", "60"])
    main()

    case, kw = calls[-1]
    assert type(case).__name__ == "TodoAppCase" and case.name == "todo_app"
    assert case.deadline_s == 60.0  # --deadline-s overrides what the case declares
    assert kw["run_id"] == "r1" and kw["n"] == 1
    # the case git-inits the flow dir in its own setup, and the flow carries its
    # own model, so the flow factory needs nothing bound to it
    assert kw["make_flow_driver"] is engine_run.make_flow_driver_omni
    out = capsys.readouterr().out
    assert json.loads(out.split("\nRun written to:")[0]) == {"x": 1}


def test_main_rescore_calls_rescore_run_and_skips_factories(monkeypatch, capsys, tmp_path):
    (tmp_path / "todo_app" / "r1").mkdir(parents=True)
    calls = []

    async def fake_rescore_run(case, run_root):
        calls.append((case, run_root))
        return {"superpowers": "ok", "plain": "ok"}

    def boom(*args, **kwargs):
        pytest.fail("factories should not be built on --rescore")

    monkeypatch.setattr("scenarios.coding_workflow.run.rescore_run", fake_rescore_run)
    monkeypatch.setattr("scenarios.coding_workflow.run.omni_factories", boom)
    monkeypatch.setattr("scenarios.coding_workflow.run.run_case_n", boom)
    monkeypatch.setattr("sys.argv", ["run", "--rescore", "r1", "--runs-root", str(tmp_path)])
    main()

    case, run_root = calls[-1]
    assert type(case).__name__ == "TodoAppCase" and case.name == "todo_app"
    assert run_root == tmp_path / "todo_app" / "r1"  # <runs_root>/<case>/<run_id>
    out = capsys.readouterr().out
    assert json.loads(out) == {"superpowers": "ok", "plain": "ok"}


def test_main_rescore_missing_run_dir_exits(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["run", "--rescore", "nope", "--runs-root", str(tmp_path)])
    with pytest.raises(SystemExit):
        main()


def test_scenario_constant():
    assert SCENARIO == "coding_workflow"


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


@pytest.mark.parametrize("flag", ["--deadline-s", "--n"])
@pytest.mark.parametrize("bad", ["0", "-5"])
def test_budgets_must_be_positive(flag, bad):
    from scenarios.coding_workflow.run import _parse_args

    with pytest.raises(SystemExit):
        _parse_args([flag, bad])
    args = _parse_args([flag, "2"])
    assert getattr(args, flag.lstrip("-").replace("-", "_")) == 2
