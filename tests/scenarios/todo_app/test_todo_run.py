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
from scenarios.coding_workflow.run import DONE_TOKEN, SCENARIO, default_runs_root, main

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

    async def fake_run_case_n(case_dir, **kw):
        # bind against the real signature so a misspelled/extra kwarg fails here, not live
        inspect.signature(engine_run.run_case_n).bind(case_dir, **kw)
        calls.append((case_dir, kw))
        return {"run_root": str(tmp_path), "trials": [{"x": 1}], "aggregate": {"n": kw["n"]}}

    monkeypatch.setattr("scenarios.coding_workflow.run.run_case_n", fake_run_case_n)
    monkeypatch.setattr("sys.argv", ["run", "--run-id", "r1"])
    main()

    case_dir, kw = calls[-1]
    assert kw["run_id"] == "r1" and kw["n"] == 1
    assert kw["scenario"] == "coding_workflow"
    assert kw["done_token"] == "<<DONE>>"
    assert kw["score_flow"].func is score_todo_app
    assert kw["score_flow"].keywords["make_grader"].func is make_grader_omni
    assert kw["make_flow_driver"].func is engine_run.make_flow_driver_omni
    assert kw["make_flow_driver"].keywords == {
        "scenario": "coding_workflow",
        "artifact_name": "__none__",
        "git_init": True,
    }
    assert kw["artifact_name"] is None
    out = capsys.readouterr().out
    assert json.loads(out.split("\nRun written to:")[0]) == {"x": 1}


def test_main_rescore_calls_rescore_run_and_skips_factories(monkeypatch, capsys, tmp_path):
    (tmp_path / "r1").mkdir()
    calls = []

    async def fake_rescore_run(case_dir, run_root, *, score_flow):
        calls.append((case_dir, run_root, score_flow))
        return {"superpowers": "ok", "plain": "ok"}

    def boom(*args, **kwargs):
        pytest.fail("factories should not be built on --rescore")

    monkeypatch.setattr("scenarios.coding_workflow.run.rescore_run", fake_rescore_run)
    monkeypatch.setattr("scenarios.coding_workflow.run.omni_factories", boom)
    monkeypatch.setattr("scenarios.coding_workflow.run.run_case_n", boom)
    monkeypatch.setattr("sys.argv", ["run", "--rescore", "r1", "--runs-root", str(tmp_path)])
    main()

    case_dir, run_root, score_flow = calls[-1]
    assert Path(case_dir).name == "todo_app"
    assert run_root == tmp_path / "r1"
    assert score_flow.func is score_todo_app
    out = capsys.readouterr().out
    assert json.loads(out) == {"superpowers": "ok", "plain": "ok"}


def test_main_rescore_missing_run_dir_exits(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["run", "--rescore", "nope", "--runs-root", str(tmp_path)])
    with pytest.raises(SystemExit):
        main()


def test_scenario_and_done_token_constants():
    assert SCENARIO == "coding_workflow"
    assert DONE_TOKEN == "<<DONE>>"


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


def test_make_grader_omni_wires_judge_dir_and_model(tmp_path):
    flow_dir = tmp_path / "run-1" / "superpowers"
    flow_dir.mkdir(parents=True)
    model = make_grader_omni(flow_dir, scenario="coding_workflow")
    d = model._driver
    assert d.run_dir == flow_dir.parent / "_judge_superpowers"
    assert d.run_dir.is_dir()
    assert d.model == engine_run.JUDGE_MODEL
    assert d.skills == "none"
    assert d.turn_timeout_s == 600
    assert d.artifact_name == "__none__"
    # web-UI grouping: the grader lands in its run's folder, titled by flow
    assert d.project == "coding_workflow/run-1"
    assert d.session_title == "judge: superpowers"


@pytest.mark.parametrize("flag", ["--deadline-s", "--n"])
@pytest.mark.parametrize("bad", ["0", "-5"])
def test_budgets_must_be_positive(flag, bad):
    from scenarios.coding_workflow.run import _parse_args

    with pytest.raises(SystemExit):
        _parse_args([flag, bad])
    args = _parse_args([flag, "2"])
    assert getattr(args, flag.lstrip("-").replace("-", "_")) == 2
