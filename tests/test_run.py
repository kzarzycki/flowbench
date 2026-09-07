import asyncio
import json
import shutil
from pathlib import Path

import pytest
import yaml

import flowbench.run as run_mod
from flowbench.run import (
    MISSING_PLAN,
    _project,
    _title,
    make_flow_driver_omni,
    run_case,
    run_case_n,
)
from flowbench.testing import FakeDriver, MissingPlanDriver, StubSim, n_run_factories
from tests.report.test_run_report import _aggregate_dir

CASE_DIR = Path(__file__).parent / "fixtures" / "feature_flag_service"


def test_run_case_offline(tmp_path):
    case = CASE_DIR
    sims = []

    def make_flow_driver(flow, flow_dir):
        if flow["name"] == "superpowers":
            return FakeDriver(
                "# SP plan\nunknown flag key returns 404.",
                ["what should evaluation return for an unknown flag key?"],
            )
        return FakeDriver("# plain plan\nno unknown-key note.", [])

    def make_simulator(flow, sim_dir):
        replies = (
            ["a 404 not-found response", "PLAN_COMPLETE"]
            if flow["name"] == "superpowers"
            else ["PLAN_COMPLETE"]
        )
        sim = StubSim(replies)
        sims.append(sim)
        return sim

    async def run_judge(judge_md, entries, judge_dir):
        assert "WINNER:" in judge_md
        by_label = {label: (transcript, plan) for label, transcript, plan in entries}
        assert "SP plan" in by_label["A"][1] and "plain plan" in by_label["B"][1]
        # the judge sees each flow's conversation, not just its plan
        assert "404" in by_label["A"][0]
        assert "# Transcript" in by_label["B"][0]
        return "A is better; it handles the unknown key.\nWINNER: A\nA: thorough\nB: thin"

    result = asyncio.run(
        run_case(
            case,
            run_id="test-run",
            make_flow_driver=make_flow_driver,
            make_simulator=make_simulator,
            run_judge=run_judge,
            runs_root=tmp_path,
            scenario="swe_planning",
            artifact_grace_s=0.0,
        )
    )

    root = Path(result["run_root"])
    assert root == tmp_path / "test-run"
    assert (root / "superpowers" / "plan.md").read_text().startswith("# SP plan")
    assert (root / "plain" / "plan.md").read_text().startswith("# plain plan")
    assert (root / "superpowers" / "session.json").is_file()
    # the superpowers transcript recorded the simulator's injected answer
    assert "404" in (root / "superpowers" / "transcript.md").read_text()
    assert (root / "judge.md").read_text().startswith("A is better")
    assert result["verdict"]["winner"] == "a"

    meta = json.loads((root / "run.json").read_text())
    assert meta["labels"] == {"A": "superpowers", "B": "plain"}
    assert meta["rotation"] == 0
    assert meta["winner"] == "a"
    assert meta["winner_flow"] == "superpowers"
    assert meta["reasoning_effort"] == {"superpowers": "xhigh", "plain": "xhigh"}
    assert meta["plans_missing"] == []
    # every simulator was closed even though run_agent_session closes only drivers
    assert sims and all(s.closed for s in sims)


def test_run_case_flags_missing_plan(tmp_path):
    case = CASE_DIR

    def make_flow_driver(flow, flow_dir):
        if flow["name"] == "superpowers":
            return FakeDriver("# SP plan\nunknown flag key returns 404.", [])
        return MissingPlanDriver("unused", [])

    def make_simulator(flow, sim_dir):
        return StubSim(["PLAN_COMPLETE"])

    async def run_judge(judge_md, entries, judge_dir):
        by_label = {label: plan for label, _transcript, plan in entries}
        assert by_label["B"] == MISSING_PLAN
        return "A is better.\nWINNER: A\nA: thorough\nB: missing"

    result = asyncio.run(
        run_case(
            case,
            run_id="test-run",
            make_flow_driver=make_flow_driver,
            make_simulator=make_simulator,
            run_judge=run_judge,
            runs_root=tmp_path,
            scenario="swe_planning",
            artifact_grace_s=0.0,
        )
    )

    root = Path(result["run_root"])
    assert (root / "plain" / "plan.md").read_text() == ""

    meta = json.loads((root / "run.json").read_text())
    assert meta["plans_missing"] == ["plain"]


def test_run_case_rejects_flow_count(tmp_path):
    case = CASE_DIR
    case_copy = tmp_path / "case"
    case_copy.mkdir()
    for name in ("task.md", "simulator.md", "knowledge.md", "judge.md"):
        shutil.copy(case / name, case_copy / name)
    single_flow = {
        "flows": [
            {
                "name": "plain",
                "harness": "claude-native",
                "model": "opus",
                "reasoning_effort": "xhigh",
                "skills": "none",
                "prepend": "Plan this feature directly.",
                "append": "Write the plan to plan.md.",
            }
        ]
    }
    (case_copy / "flows.yaml").write_text(yaml.safe_dump(single_flow))

    def fail_factory(*args, **kwargs):
        pytest.fail("factory should not be called when flow count is invalid")

    with pytest.raises(ValueError):
        asyncio.run(
            run_case(
                case_copy,
                run_id="test-run",
                make_flow_driver=fail_factory,
                make_simulator=fail_factory,
                run_judge=fail_factory,
                runs_root=tmp_path / "runs",
                scenario="swe_planning",
            )
        )


def test_run_case_forwards_artifact_grace(tmp_path, monkeypatch):
    case = CASE_DIR
    calls = []

    async def rec(*args, **kwargs):
        calls.append(kwargs)
        return {"items": [], "events": [], "artifact_text": "# p"}

    monkeypatch.setattr(run_mod, "run_agent_session", rec)

    def make_flow_driver(flow, flow_dir):
        return FakeDriver("# p", [])

    def make_simulator(flow, sim_dir):
        return StubSim(["PLAN_COMPLETE"])

    async def run_judge(judge_md, entries, judge_dir):
        return "WINNER: A"

    asyncio.run(
        run_case(
            case,
            run_id="t",
            make_flow_driver=make_flow_driver,
            make_simulator=make_simulator,
            run_judge=run_judge,
            runs_root=tmp_path,
            scenario="swe_planning",
            artifact_grace_s=0.0,
        )
    )

    assert calls
    assert all(kwargs["artifact_grace_s"] == 0.0 for kwargs in calls)


def test_make_flow_driver_omni_maps_flow_config(tmp_path):
    flow = {
        "name": "plain",
        "harness": "claude-native",
        "model": "opus",
        "reasoning_effort": "xhigh",
        "skills": "none",
    }
    d = make_flow_driver_omni(flow, tmp_path, scenario="swe_planning")
    assert d.run_dir == tmp_path
    assert d.artifact_name == "plan.md"
    assert d.model == "opus"
    assert d.harness == "claude-native"
    assert d.skills == "none"
    assert d.reasoning_effort == "xhigh"
    assert d.turn_timeout_s == 1800  # planning turns run way past the driver's 240s default
    assert (
        make_flow_driver_omni(
            {"name": "x", "turn_timeout_s": 60}, tmp_path, scenario="swe_planning"
        ).turn_timeout_s
        == 60
    )
    # web-UI grouping: one project folder per run, short role-based titles
    assert d.session_title == "flow: plain"
    assert d.project == f"swe_planning/{tmp_path.parent.name}"


def test_run_case_n_three_trials(tmp_path):
    case = CASE_DIR
    mfd, ms, rj = n_run_factories(["A", "B", "A"])

    result = asyncio.run(
        run_case_n(
            case,
            run_id="agg-run",
            n=3,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
            scenario="swe_planning",
        )
    )

    # uniform return shape
    assert set(result) == {"run_root", "trials", "aggregate"}
    # trial-02 rotates the 2-flow list left by 1 (position-bias cancellation): its
    # positional "B" is superpowers, so scripted winners A,B,A all map to flow
    # superpowers -> the aggregate is name-keyed and invariant to rotation.
    assert result["aggregate"] == {
        "n": 3,
        "counts": {"superpowers": 3, "tie": 0, "unknown": 0},
        "winner": "superpowers",
    }
    assert [t["winner_flow"] for t in result["trials"]] == ["superpowers"] * 3
    assert [t["rotation"] for t in result["trials"]] == [0, 1, 0]

    root = Path(result["run_root"])
    assert root == tmp_path / "agg-run"
    # each trial dir has the full single-run layout
    for k in (1, 2, 3):
        trial = root / f"trial-{k:02d}"
        assert (trial / "superpowers" / "plan.md").is_file()
        assert (trial / "superpowers" / "transcript.md").is_file()
        assert (trial / "superpowers" / "session.json").is_file()
        assert (trial / "plain" / "plan.md").is_file()
        assert (trial / "judge.md").is_file()
        assert (trial / "run.json").is_file()
    # top-level aggregate run.json
    agg = json.loads((root / "run.json").read_text())
    assert agg["n"] == 3
    assert agg["case"] == "feature_flag_service"
    assert agg["flows"] == ["superpowers", "plain"]
    assert agg["trials"] == [
        {"trial": "trial-01", "winner_flow": "superpowers"},
        {"trial": "trial-02", "winner_flow": "superpowers"},
        {"trial": "trial-03", "winner_flow": "superpowers"},
    ]
    assert agg["counts"] == {"superpowers": 3, "tie": 0, "unknown": 0}
    assert agg["winner"] == "superpowers"


def test_run_case_n_single_trial_keeps_flat_layout(tmp_path):
    case = CASE_DIR
    mfd, ms, rj = n_run_factories(["A"])

    result = asyncio.run(
        run_case_n(
            case,
            run_id="single-run",
            n=1,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
            scenario="swe_planning",
        )
    )

    # same uniform shape as n>1, so main()'s print path exists in both modes
    assert set(result) == {"run_root", "trials", "aggregate"}
    assert result["aggregate"] == {
        "n": 1,
        "counts": {"superpowers": 1, "tie": 0, "unknown": 0},
        "winner": "superpowers",
    }
    root = Path(result["run_root"])
    assert root == tmp_path / "single-run"
    # flat single-run layout, no trial dirs, run.json is the single-run meta
    assert not (root / "trial-01").exists()
    assert (root / "superpowers" / "plan.md").is_file()
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner"] == "a"
    assert meta["winner_flow"] == "superpowers"
    assert result["trials"] == [meta]


def test_run_case_n_rejects_bad_n(tmp_path):
    case = CASE_DIR
    mfd, ms, rj = n_run_factories([])
    with pytest.raises(ValueError):
        asyncio.run(
            run_case_n(
                case,
                run_id="x",
                n=0,
                make_flow_driver=mfd,
                make_simulator=ms,
                run_judge=rj,
                runs_root=tmp_path,
                scenario="swe_planning",
            )
        )


def test_run_case_n_failing_trial_propagates(tmp_path):
    case = CASE_DIR
    mfd, ms, rj = n_run_factories(["A"])
    calls = {"n": 0}

    async def failing_judge(judge_md, entries, judge_dir):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("judge crashed")
        return await rj(judge_md, entries, judge_dir)

    with pytest.raises(RuntimeError, match="judge crashed"):
        asyncio.run(
            run_case_n(
                case,
                run_id="fail-run",
                n=3,
                make_flow_driver=mfd,
                make_simulator=ms,
                run_judge=failing_judge,
                runs_root=tmp_path,
                scenario="swe_planning",
            )
        )

    # trial 1 completed and its artifacts remain; trial 3 never started
    assert calls["n"] == 2
    root = tmp_path / "fail-run"
    assert (root / "trial-01" / "judge.md").is_file()
    assert not (root / "trial-03").exists()
    # no aggregate run.json was written for the aborted run
    assert not (root / "run.json").exists()


def test_run_case_writes_report_html_and_flow_stats(tmp_path):
    case = CASE_DIR
    mfd, ms, rj = n_run_factories(["A"])
    result = asyncio.run(
        run_case(
            case,
            run_id="report-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
            scenario="swe_planning",
        )
    )
    root = Path(result["run_root"])
    html_text = (root / "report.html").read_text()
    assert "flowbench run report" in html_text
    assert "superpowers" in html_text and "plain" in html_text
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner_flow"] == "superpowers"
    stats = meta["flow_stats"]["superpowers"]
    assert stats["plan_lines"] == 2  # the fake's two-line plan
    assert "context_tokens" in stats and "exit_status" in stats


def test_run_case_rotation_reverses_judge_order(tmp_path):
    case = CASE_DIR
    seen = {}

    async def run_judge(judge_md, entries, judge_dir):
        seen["plan_a"] = entries[0][2]
        return "WINNER: A\nA: ok\nB: ok"

    mfd, ms, _ = n_run_factories([])
    result = asyncio.run(
        run_case(
            case,
            run_id="swap-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=run_judge,
            runs_root=tmp_path,
            scenario="swe_planning",
            rotation=1,
        )
    )
    assert "plain plan" in seen["plan_a"]  # plain judged as A when rotated
    meta = result["meta"]
    assert meta["labels"] == {"A": "plain", "B": "superpowers"}
    assert meta["rotation"] == 1
    assert meta["winner_flow"] == "plain"  # positional "a" resolved via labels


def test_project_groups_trials_under_the_run(tmp_path):
    assert _project(tmp_path / "todo-010" / "plain", "swe_planning") == "swe_planning/todo-010"
    assert (
        _project(tmp_path / "todo-010" / "trial-01" / "plain", "swe_planning")
        == "swe_planning/todo-010"
    )


def test_title_includes_trial_segment(tmp_path):
    assert _title(tmp_path / "todo-x" / "plain", "sim: plain") == "sim: plain"
    assert (
        _title(tmp_path / "todo-x" / "trial-02" / "plain", "sim: plain") == "trial-02 · sim: plain"
    )


def test_make_flow_driver_threads_skill_dirs(tmp_path):
    flow = {
        "name": "codex",
        "harness": "codex-native",
        "model": "gpt-5.5",
        "skill_dirs": [tmp_path / "skills" / "brainstorming"],
    }
    d = make_flow_driver_omni(flow, tmp_path, scenario="swe_planning")
    assert d.skill_dirs == [tmp_path / "skills" / "brainstorming"]
    assert d.harness == "codex-native"
    assert d.model == "gpt-5.5"


def test_make_flow_driver_defaults_no_skill_dirs(tmp_path):
    d = make_flow_driver_omni({"name": "x"}, tmp_path, scenario="swe_planning")
    assert d.skill_dirs == []


# --- N-way (3-flow) coverage -------------------------------------------------


def _three_flow_case(tmp_path) -> Path:
    """A synthetic 3-flow case dir: reuses feature_flag_service's task/sim/judge
    text, with a hand-written 3-flow flows.yaml."""
    src = CASE_DIR
    case = tmp_path / "three_flow_case"
    case.mkdir()
    for name in ("task.md", "simulator.md", "knowledge.md", "judge.md"):
        shutil.copy(src / name, case / name)
    flows = {
        "flows": [
            {"name": "superpowers", "harness": "claude-native", "model": "opus", "skills": "all"},
            {"name": "plain", "harness": "claude-native", "model": "opus", "skills": "none"},
            {"name": "codex", "harness": "codex-native", "model": "gpt-5.5", "skills": "none"},
        ]
    }
    (case / "flows.yaml").write_text(yaml.safe_dump(flows))
    return case


def _three_flow_factories():
    def make_flow_driver(flow, flow_dir):
        return FakeDriver(f"# {flow['name']} plan\ncontent for {flow['name']}.", [])

    def make_simulator(flow, sim_dir):
        return StubSim(["PLAN_COMPLETE"])

    return make_flow_driver, make_simulator


def test_run_case_three_flows_labels_and_winner_flow(tmp_path):
    case = _three_flow_case(tmp_path)
    mfd, ms = _three_flow_factories()

    async def run_judge(judge_md, entries, judge_dir):
        assert [label for label, _, _ in entries] == ["A", "B", "C"]
        return "C is best.\nWINNER: C\nA: ok\nB: ok\nC: best\n"

    result = asyncio.run(
        run_case(
            case,
            run_id="three-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=run_judge,
            runs_root=tmp_path / "runs",
            scenario="swe_planning",
            artifact_grace_s=0.0,
        )
    )
    meta = result["meta"]
    assert meta["labels"] == {"A": "superpowers", "B": "plain", "C": "codex"}
    assert meta["winner"] == "c"
    assert meta["winner_flow"] == "codex"
    assert meta["flows"] == ["superpowers", "plain", "codex"]


def test_run_case_n_three_flows_rotation_sequence(tmp_path):
    case = _three_flow_case(tmp_path)
    mfd, ms = _three_flow_factories()

    # Each trial's judge always picks positional "A" — with rotation 0,1,2 over
    # 3 flows that resolves to superpowers, plain, codex respectively; the
    # aggregate must still be name-keyed and reflect one win each -> tie.
    async def run_judge(judge_md, entries, judge_dir):
        return "Prose.\nWINNER: A\nA: ok\nB: ok\nC: ok\n"

    result = asyncio.run(
        run_case_n(
            case,
            run_id="three-agg",
            n=3,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=run_judge,
            runs_root=tmp_path / "runs",
            scenario="swe_planning",
        )
    )
    trials = result["trials"]
    assert [t["rotation"] for t in trials] == [0, 1, 2]
    assert [t["winner_flow"] for t in trials] == ["superpowers", "plain", "codex"]
    assert result["aggregate"]["counts"] == {
        "superpowers": 1,
        "plain": 1,
        "codex": 1,
        "tie": 0,
        "unknown": 0,
    }
    assert result["aggregate"]["winner"] == "tie"

    root = Path(result["run_root"])
    agg = json.loads((root / "run.json").read_text())
    assert agg["flows"] == ["superpowers", "plain", "codex"]


def test_run_case_three_flows_report_renders_without_keyerror(tmp_path):
    case = _three_flow_case(tmp_path)
    mfd, ms = _three_flow_factories()

    async def run_judge(judge_md, entries, judge_dir):
        return "C wins.\nWINNER: C\nA: ok\nB: ok\nC: best\n"

    result = asyncio.run(
        run_case(
            case,
            run_id="three-report",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=run_judge,
            runs_root=tmp_path / "runs",
            scenario="swe_planning",
            artifact_grace_s=0.0,
        )
    )
    text = (Path(result["run_root"]) / "report.html").read_text()
    assert "flowbench run report" in text
    assert "superpowers" in text and "plain" in text and "codex" in text


def test_run_case_n_three_flows_aggregate_report_renders(tmp_path):
    case = _three_flow_case(tmp_path)
    mfd, ms = _three_flow_factories()

    async def run_judge(judge_md, entries, judge_dir):
        return "C wins.\nWINNER: C\nA: ok\nB: ok\nC: best\n"

    result = asyncio.run(
        run_case_n(
            case,
            run_id="three-agg-report",
            n=2,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=run_judge,
            runs_root=tmp_path / "runs",
            scenario="swe_planning",
        )
    )
    text = (Path(result["run_root"]) / "report.html").read_text()
    assert "flowbench aggregate report" in text
    assert 'href="trial-01/report.html"' in text
    assert 'href="trial-02/report.html"' in text


def test_render_any_dispatches_on_shape(tmp_path):
    from flowbench.report.run_report import render_any

    # aggregate-shaped dir -> aggregate template
    agg = _aggregate_dir(
        tmp_path,
        winner="tie",
        counts={"superpowers": 1, "plain": 1, "tie": 0, "unknown": 0},
        score_means={},
        flows=["superpowers", "plain"],
        trial_winner_flows=["superpowers", "plain"],
    )
    assert "flowbench aggregate report" in render_any(agg).read_text()

    # single-run-shaped dir (full run_case output) -> single-run template
    mfd, ms, rj = n_run_factories(["A"])
    result = asyncio.run(
        run_case(
            CASE_DIR,
            run_id="single",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
            scenario="swe_planning",
        )
    )
    text = render_any(Path(result["run_root"])).read_text()
    assert "flowbench run report" in text
    assert "flowbench aggregate report" not in text


def test_run_case_n_writes_aggregate_report(tmp_path):
    case = CASE_DIR
    # trial-02 rotates: positional B is superpowers, so A,B -> superpowers 2-0
    mfd, ms, rj = n_run_factories(["A", "B"])
    result = asyncio.run(
        run_case_n(
            case,
            run_id="agg-report-run",
            n=2,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
            scenario="swe_planning",
        )
    )
    text = (Path(result["run_root"]) / "report.html").read_text()
    assert "flowbench aggregate report" in text
    assert "superpowers wins 2–0 (n=2)" in text
    assert 'href="trial-01/report.html"' in text
    assert 'href="trial-02/report.html"' in text
    # scripted judge emits no SCORES lines -> section omitted, no crash
    assert "Score means" not in text
