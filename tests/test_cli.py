"""The engine CLI: `flowbench run <case_dir>`, `flowbench watch <run_id>`, `compare`.

The three omnigent factories are patched to `flowbench.testing`'s offline doubles,
so every test here drives the real command path — discovery, settings, the
orchestrator, the run dir — without a live server.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowbench.cli import app
from flowbench.testing import n_run_factories

FIXTURE = Path(__file__).parent / "fixtures" / "feature_flag_service"
TEXT_FILES = ("task.md", "simulator.md", "knowledge.md", "flows.yaml", "judge.md")
ENV_VARS = ("FLOWBENCH_RUNS_ROOT", "FLOWBENCH_SIM_MODEL", "FLOWBENCH_JUDGE_MODEL")

ONE_FLOW = (
    "flows:\n  - name: plain\n    harness: claude-native\n    model: opus\n    skills: none\n"
)

SCORING_CASE_PY = """\
from flowbench.case import Case


class ScoringCase(Case):
    deliverable = "plan.md"

    async def score(self, flow, flow_dir, session):
        return {"judge_model": self.settings.judge_model, "v": %s}
"""
# The two versions differ in LENGTH, not only in value: CPython invalidates its
# cached bytecode on the source's (mtime-to-the-second, size) pair, and a
# same-size edit inside one second would be re-run from the stale .pyc.
V1, V2 = SCORING_CASE_PY % '"one"', SCORING_CASE_PY % '"another"'

runner = CliRunner()  # typer 0.27 always splits stdout/stderr — no mix_stderr kwarg


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """No FLOWBENCH_* from the developer's shell, and no repo `.env`/`pyproject.toml`
    under the cwd: every test states the settings it depends on."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)


def _case(dst: Path, *, case_py: str | None = None, files=TEXT_FILES) -> Path:
    """A case folder under a `scenarios` root (so discovery stops there), over the
    fixture's text files, with an optional `case.py`."""
    dst.mkdir(parents=True, exist_ok=True)
    for name in files:
        shutil.copy(FIXTURE / name, dst / name)
    if case_py is not None:
        (dst / "case.py").write_text(case_py)
    return dst


def _doubles(case):
    return n_run_factories(["A"])


def _fail_factory(case):
    pytest.fail("no factory may be built on this path")


def _offline(monkeypatch, factories=_doubles):
    monkeypatch.setattr("flowbench.run.omni_factories", factories)


# --- flowbench run ----------------------------------------------------------


def test_run_a_judged_two_flow_case(tmp_path, monkeypatch):
    _offline(monkeypatch)
    runs_root = tmp_path / "runs"

    result = runner.invoke(
        app,
        ["run", str(FIXTURE), "--runs-root", str(runs_root), "--run-id", "cli-1"],
    )

    assert result.exit_code == 0, result.output
    run_root = runs_root / "feature_flag_service" / "cli-1"
    meta = json.loads((run_root / "run.json").read_text())
    assert meta["case"] == "feature_flag_service"
    assert meta["deliverable"] == "plan.md"
    assert meta["winner_flow"] == "superpowers"  # judge letter A = the first flow
    assert (run_root / "superpowers" / "plan.md").is_file()
    assert (run_root / "judge.md").is_file()
    # stdout: the trial's own meta, then where it landed
    printed, tail = result.stdout.split("\nRun written to: ")
    assert json.loads(printed)["run_id"] == "cli-1"
    assert tail.strip() == str(run_root)


def test_run_n_trials_prints_the_aggregate(tmp_path, monkeypatch):
    _offline(monkeypatch, lambda case: n_run_factories(["A", "B"]))
    runs_root = tmp_path / "runs"

    result = runner.invoke(
        app,
        ["run", str(FIXTURE), "--runs-root", str(runs_root), "--run-id", "cli-n", "--n", "2"],
    )

    assert result.exit_code == 0, result.output
    run_root = runs_root / "feature_flag_service" / "cli-n"
    assert (run_root / "trial-01" / "run.json").is_file()
    assert (run_root / "trial-02" / "run.json").is_file()
    printed = json.loads(result.stdout.split("\nRun written to: ")[0])
    assert printed["n"] == 2
    assert printed["counts"]["superpowers"] == 2  # A, then B after the rotation
    assert printed["winner"] == "superpowers"


def test_run_id_defaults_to_a_timestamp(tmp_path, monkeypatch):
    _offline(monkeypatch)
    runs_root = tmp_path / "runs"

    result = runner.invoke(app, ["run", str(FIXTURE), "--runs-root", str(runs_root)])

    assert result.exit_code == 0, result.output
    (run_root,) = list((runs_root / "feature_flag_service").iterdir())
    assert re.fullmatch(r"\d{8}-\d{6}", run_root.name), run_root.name


@pytest.mark.parametrize(
    ("judge", "expected"),
    [
        (True, "judge.md needs 2+ flows to compare, flows.yaml has 1"),
        (False, "nothing grades this case — one flow and no score() override"),
    ],
)
def test_run_reports_a_load_error_and_exits_1(tmp_path, monkeypatch, judge, expected):
    _offline(monkeypatch, _fail_factory)  # a load error never spends a session
    files = ("task.md", "simulator.md", "knowledge.md") + (("judge.md",) if judge else ())
    case_dir = _case(tmp_path / "scenarios" / "lonely", files=files)
    (case_dir / "flows.yaml").write_text(ONE_FLOW)

    result = runner.invoke(app, ["run", str(case_dir), "--runs-root", str(tmp_path / "runs")])

    assert result.exit_code == 1, result.output
    assert expected in result.stderr
    assert result.stdout == ""


def test_run_reports_a_missing_flows_file_and_exits_1(tmp_path, monkeypatch):
    _offline(monkeypatch, _fail_factory)
    case_dir = _case(
        tmp_path / "scenarios" / "flowless", files=("task.md", "simulator.md", "knowledge.md")
    )

    result = runner.invoke(app, ["run", str(case_dir), "--runs-root", str(tmp_path / "runs")])

    assert result.exit_code == 1, result.output
    assert "flows.yaml" in result.stderr


def test_rescore_rewrites_scorecards_without_a_session_or_a_factory(tmp_path, monkeypatch):
    case_dir = _case(tmp_path / "scenarios" / "scored", case_py=V1)
    runs_root = tmp_path / "runs"
    _offline(monkeypatch)
    first = runner.invoke(
        app, ["run", str(case_dir), "--runs-root", str(runs_root), "--run-id", "r1"]
    )
    assert first.exit_code == 0, first.output
    card = runs_root / "scored" / "r1" / "plain" / "scorecard.json"
    assert json.loads(card.read_text())["v"] == "one"

    (case_dir / "case.py").write_text(V2)
    _offline(monkeypatch, _fail_factory)
    result = runner.invoke(
        app,
        ["run", str(case_dir), "--runs-root", str(runs_root), "--rescore", "r1"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert json.loads(card.read_text())["v"] == "another"
    assert json.loads(result.stdout) == {"superpowers": "ok", "plain": "ok"}


def test_rescore_missing_run_dir_exits_1(tmp_path, monkeypatch):
    case_dir = _case(tmp_path / "scenarios" / "scored", case_py=V1)
    _offline(monkeypatch, _fail_factory)

    result = runner.invoke(
        app,
        ["run", str(case_dir), "--runs-root", str(tmp_path / "runs"), "--rescore", "nope"],
    )

    assert result.exit_code == 1, result.output
    assert str(tmp_path / "runs" / "scored" / "nope") in result.stderr


def test_flags_beat_the_environment_for_every_setting(tmp_path, monkeypatch):
    seen = []

    def _factories(case):
        seen.append(case.settings)
        return n_run_factories(["A"])

    _offline(monkeypatch, _factories)
    monkeypatch.setenv("FLOWBENCH_RUNS_ROOT", str(tmp_path / "env-runs"))
    monkeypatch.setenv("FLOWBENCH_SIM_MODEL", "env-sim")
    monkeypatch.setenv("FLOWBENCH_JUDGE_MODEL", "env-judge")

    # no flag: the environment stands, for the run dir too
    from_env = runner.invoke(app, ["run", str(FIXTURE), "--run-id", "e"])
    assert from_env.exit_code == 0, from_env.output
    assert seen[-1].runs_root == tmp_path / "env-runs"
    assert (seen[-1].sim_model, seen[-1].judge_model) == ("env-sim", "env-judge")
    assert (tmp_path / "env-runs" / "feature_flag_service" / "e" / "run.json").is_file()

    from_flags = runner.invoke(
        app,
        [
            "run",
            str(FIXTURE),
            "--run-id",
            "f",
            "--runs-root",
            str(tmp_path / "flag-runs"),
            "--sim-model",
            "flag-sim",
            "--judge-model",
            "flag-judge",
        ],
    )
    assert from_flags.exit_code == 0, from_flags.output
    assert seen[-1].runs_root == tmp_path / "flag-runs"
    assert (seen[-1].sim_model, seen[-1].judge_model) == ("flag-sim", "flag-judge")
    assert (tmp_path / "flag-runs" / "feature_flag_service" / "f" / "run.json").is_file()


def test_judge_model_flag_reaches_the_case_grader(tmp_path, monkeypatch):
    case_dir = _case(tmp_path / "scenarios" / "scored", case_py=V1)
    _offline(monkeypatch)

    result = runner.invoke(
        app,
        [
            "run",
            str(case_dir),
            "--runs-root",
            str(tmp_path / "runs"),
            "--run-id",
            "r1",
            "--judge-model",
            "sonnet",
        ],
    )

    assert result.exit_code == 0, result.output
    for flow in ("superpowers", "plain"):
        card = json.loads(
            (tmp_path / "runs" / "scored" / "r1" / flow / "scorecard.json").read_text()
        )
        assert card["judge_model"] == "sonnet"


# --- flowbench watch --------------------------------------------------------


@pytest.fixture
def _offline_sessions(monkeypatch):
    """The watcher's only network read, stubbed: no live omnigent in the suite."""
    monkeypatch.setattr("flowbench.watch.RunWatch._run_sessions", lambda self: [])


def _completed_run(runs_root: Path, case: str, run_id: str) -> Path:
    run_root = runs_root / case / run_id
    run_root.mkdir(parents=True)
    (run_root / "run.json").write_text('{"winner_flow": "plain"}')
    return run_root


def test_watch_exits_on_run_json(tmp_path, _offline_sessions):
    runs_root = tmp_path / "runs"
    _completed_run(runs_root, "feature_flag_service", "r1")

    result = runner.invoke(app, ["watch", "r1", "--runs-root", str(runs_root)])

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("RUN COMPLETE: ")
    assert '"winner_flow": "plain"' in result.stdout


def test_watch_takes_the_runs_root_from_the_environment(tmp_path, monkeypatch, _offline_sessions):
    runs_root = tmp_path / "env-runs"
    _completed_run(runs_root, "feature_flag_service", "r1")
    monkeypatch.setenv("FLOWBENCH_RUNS_ROOT", str(runs_root))

    result = runner.invoke(app, ["watch", "r1"])

    assert result.exit_code == 0, result.output
    assert "RUN COMPLETE" in result.stdout


def test_watch_flag_beats_the_environment(tmp_path, monkeypatch, _offline_sessions):
    (tmp_path / "env-runs").mkdir()  # the env root does not hold the run
    _completed_run(tmp_path / "flag-runs", "feature_flag_service", "r1")
    monkeypatch.setenv("FLOWBENCH_RUNS_ROOT", str(tmp_path / "env-runs"))

    result = runner.invoke(app, ["watch", "r1", "--runs-root", str(tmp_path / "flag-runs")])

    assert result.exit_code == 0, result.output
    assert "RUN COMPLETE" in result.stdout


def test_watch_ambiguous_and_missing_run_id(tmp_path, _offline_sessions):
    runs_root = tmp_path / "runs"
    _completed_run(runs_root, "case_a", "r1")
    _completed_run(runs_root, "case_b", "r1")

    ambiguous = runner.invoke(app, ["watch", "r1", "--runs-root", str(runs_root)])
    assert ambiguous.exit_code == 1, ambiguous.output
    assert str(runs_root / "case_a" / "r1") in ambiguous.stderr
    assert str(runs_root / "case_b" / "r1") in ambiguous.stderr

    missing = runner.invoke(app, ["watch", "nope", "--runs-root", str(runs_root)])
    assert missing.exit_code == 1, missing.output
    assert str(runs_root / "*" / "nope") in missing.stderr


# --- flowbench compare ------------------------------------------------------


def test_compare_still_runs(tmp_path):
    for flow, acceptance in (("baseline", 0.7), ("superpowers", 0.9)):
        flow_dir = tmp_path / "r1" / flow
        flow_dir.mkdir(parents=True)
        (flow_dir / "scorecard.json").write_text(
            json.dumps({"objective": {"acceptance": acceptance}})
        )

    result = runner.invoke(app, ["compare", "--run-base", str(tmp_path), "--run-id", "r1"])

    assert result.exit_code == 0, result.output
    assert "| metric | baseline | superpowers |" in result.stdout
    assert "| acceptance | 0.7 | 0.9 |" in result.stdout

    to_file = runner.invoke(
        app,
        ["compare", "--run-base", str(tmp_path), "--run-id", "r1", "--out", str(tmp_path / "c.md")],
    )
    assert to_file.exit_code == 0, to_file.output
    assert "| acceptance | 0.7 | 0.9 |" in (tmp_path / "c.md").read_text()
