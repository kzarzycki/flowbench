import asyncio
import inspect
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

import flowbench.run as run_mod
from flowbench.case import Case, load_case
from flowbench.loop import DONE_TOKEN
from flowbench.run import (
    MISSING_DELIVERABLE,
    NO_DELIVERABLE,
    _judge_view,
    _project,
    _run_parts,
    _title,
    make_flow_driver_omni,
    run_case,
    run_case_n,
)
from flowbench.settings import Settings
from flowbench.testing import FakeDriver, MissingPlanDriver, StubSim, n_run_factories
from tests.report.test_run_report import _aggregate_dir

CASE_DIR = Path(__file__).parent / "fixtures" / "feature_flag_service"

ONE_FLOW = [{"name": "plain", "harness": "claude-native", "model": "opus", "skills": "none"}]
TWO_FLOWS = [
    {"name": "superpowers", "harness": "claude-native", "model": "opus", "skills": "all"},
    {"name": "plain", "harness": "claude-native", "model": "opus", "skills": "none"},
]
THREE_FLOWS = [
    *TWO_FLOWS,
    {"name": "codex", "harness": "codex-native", "model": "gpt-5.5", "skills": "none"},
]


class PlanCase(Case):
    """Plan-shaped, like the fixture case: the flows are compared on plan.md."""

    deliverable = "plan.md"


def _case_files(dst: Path, *, flows: list[dict], judge: bool = True) -> Path:
    """A case folder over the fixture's text, with a hand-written flows.yaml and
    judge.md only when this case compares its flows."""
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("task.md", "simulator.md", "knowledge.md"):
        shutil.copy(CASE_DIR / name, dst / name)
    if judge:
        shutil.copy(CASE_DIR / "judge.md", dst / "judge.md")
    (dst / "flows.yaml").write_text(yaml.safe_dump({"flows": flows}))
    return dst


def _scored(case_dir, score_fn, *, base=PlanCase, **attrs) -> Case:
    """A case that grades its own flows: `score_fn(flow, flow_dir, session)` is
    what the retired `score_flow` keyword used to carry."""

    async def score(self, flow, flow_dir, session):
        return await score_fn(flow, flow_dir, session)

    return type("ScoredCase", (base,), {"score": score, **attrs})(case_dir)


async def _card(flow, flow_dir, session) -> dict:
    """The simplest scorecard a case's `score` can return."""
    return {"flow": flow["name"]}


def _fail_factory(*args, **kwargs):
    pytest.fail("no factory may be built when the case cannot be graded")


def _sim(flow, sim_dir):
    return StubSim([DONE_TOKEN])


class TreeDriver(FakeDriver):
    """A flow that lays down an arbitrary tree in its run dir: the deliverable
    shapes a real agent produces (nested file, directory, none) that FakeDriver's
    single plan.md cannot express. `{"a/b.txt": "text", "port/": ""}` — a trailing
    slash is a directory."""

    def __init__(self, tree, run_dir, on_start=None):
        super().__init__("", [], run_dir=run_dir)
        self._tree = tree
        self._on_start = on_start

    async def start(self):
        if self._on_start is not None:
            self._on_start()
        root = Path(self._run_dir)
        root.mkdir(parents=True, exist_ok=True)
        for rel, text in self._tree.items():
            path = root / rel
            if rel.endswith("/"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)


# --- layout, budgets, settings ----------------------------------------------


async def test_run_case_layout_is_case_then_run_id(tmp_path):
    case = load_case(CASE_DIR)
    mfd, ms, rj = n_run_factories(["A"])

    result = await run_case(
        case,
        run_id="test-run",
        make_flow_driver=mfd,
        make_simulator=ms,
        run_judge=rj,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    assert root == tmp_path / "feature_flag_service" / "test-run"
    meta = json.loads((root / "run.json").read_text())
    assert meta["case"] == "feature_flag_service"
    assert meta["deliverable"] == "plan.md"
    assert "scenario" not in meta


async def test_runs_root_defaults_to_settings(tmp_path):
    case = load_case(CASE_DIR, Settings(runs_root=tmp_path / "from-settings"))
    mfd, ms, rj = n_run_factories(["A"])

    result = await run_case(case, run_id="r", make_flow_driver=mfd, make_simulator=ms, run_judge=rj)

    assert Path(result["run_root"]) == tmp_path / "from-settings" / "feature_flag_service" / "r"


async def test_case_budgets_reach_the_loop_and_done_token_does_not(tmp_path, monkeypatch):
    retired = {"done_token", "artifact_name", "score_flow", "max_turns", "deadline_s", "scenario"}
    assert retired.isdisjoint(inspect.signature(run_case).parameters)
    assert retired.isdisjoint(inspect.signature(run_case_n).parameters)

    calls = []

    async def rec(*args, **kwargs):
        calls.append(kwargs)
        return {"items": [], "events": []}

    monkeypatch.setattr(run_mod, "run_agent_session", rec)
    case = type("Budgeted", (PlanCase,), {"max_turns": 7, "deadline_s": 12.0})(CASE_DIR)
    mfd, ms, rj = n_run_factories(["A"])

    await run_case(
        case,
        run_id="budgets",
        make_flow_driver=mfd,
        make_simulator=ms,
        run_judge=rj,
        runs_root=tmp_path,
    )

    assert calls
    assert all(kwargs["max_turns"] == 7 for kwargs in calls)
    assert all(kwargs["deadline_s"] == 12.0 for kwargs in calls)
    assert all("done_token" not in kwargs for kwargs in calls)


# --- the two load-time errors ------------------------------------------------


async def test_judge_with_one_flow_is_a_load_error(tmp_path):
    case_dir = _case_files(tmp_path / "one_flow_judged", flows=ONE_FLOW)
    expected = re.escape(f"{case_dir}/judge.md needs 2+ flows to compare, flows.yaml has 1")

    with pytest.raises(ValueError, match=expected):
        load_case(case_dir)
    case = PlanCase(case_dir)
    with pytest.raises(ValueError, match=expected):
        await run_case(
            case,
            run_id="x",
            make_flow_driver=_fail_factory,
            make_simulator=_fail_factory,
            run_judge=_fail_factory,
            runs_root=tmp_path / "runs",
        )
    with pytest.raises(ValueError, match=expected):
        await run_case_n(
            case,
            run_id="x",
            n=1,
            make_flow_driver=_fail_factory,
            make_simulator=_fail_factory,
            run_judge=_fail_factory,
            runs_root=tmp_path / "runs",
        )
    assert not (tmp_path / "runs").exists()


async def test_one_flow_without_score_is_a_load_error(tmp_path):
    case_dir = _case_files(tmp_path / "one_flow", flows=ONE_FLOW, judge=False)
    expected = re.escape(
        f"{case_dir}: nothing grades this case — one flow and no score() override "
        "(add a second flow to compare, or override Case.score)"
    )

    with pytest.raises(ValueError, match=expected):
        load_case(case_dir)
    case = PlanCase(case_dir)
    with pytest.raises(ValueError, match=expected):
        await run_case(
            case,
            run_id="x",
            make_flow_driver=_fail_factory,
            make_simulator=_fail_factory,
            run_judge=_fail_factory,
            runs_root=tmp_path / "runs",
        )
    with pytest.raises(ValueError, match=expected):
        await run_case_n(
            case,
            run_id="x",
            n=2,
            make_flow_driver=_fail_factory,
            make_simulator=_fail_factory,
            run_judge=_fail_factory,
            runs_root=tmp_path / "runs",
        )
    assert not (tmp_path / "runs").exists()


async def test_load_errors_fire_before_any_factory(tmp_path):
    """Ordering, not just the message: a factory that raises is never reached, so
    the ValueError is what surfaces and no run dir is created."""
    case = PlanCase(_case_files(tmp_path / "one_flow", flows=ONE_FLOW, judge=False))

    def exploding(*args, **kwargs):
        raise RuntimeError("a factory was built")

    with pytest.raises(ValueError, match="nothing grades this case"):
        await run_case(
            case,
            run_id="x",
            make_flow_driver=exploding,
            make_simulator=exploding,
            run_judge=exploding,
            runs_root=tmp_path / "runs",
        )
    assert not (tmp_path / "runs").exists()


async def test_two_flows_without_score_or_judge_load(tmp_path):
    """The errors do not over-reject: two flows are comparable even with no
    judge.md and no score override (the run dir is the record)."""
    case_dir = _case_files(tmp_path / "unjudged", flows=TWO_FLOWS, judge=False)
    mfd, ms, _ = n_run_factories([])

    assert type(load_case(case_dir)).__name__ == "Case"
    result = await run_case(
        PlanCase(case_dir),
        run_id="r",
        make_flow_driver=mfd,
        make_simulator=ms,
        run_judge=None,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    for name in ("superpowers", "plain"):
        assert (root / name / "session.json").is_file()
        assert not (root / name / "scorecard.json").exists()
    assert not (root / "judge.md").exists()


# --- the per-flow lifecycle --------------------------------------------------


async def test_lifecycle_order_setup_session_capture_score_teardown(tmp_path):
    log = []

    class Lifecycle(PlanCase):
        async def setup(self, flow, flow_dir):
            log.append("setup")

        async def score(self, flow, flow_dir, session):
            # Only the capture stage puts the nested plan.md at the flow-dir root.
            captured = (Path(flow_dir) / "plan.md").is_file()
            log.append("capture" if captured else "no-capture")
            log.append("score")
            return {"flow": flow["name"]}

        async def teardown(self, flow, flow_dir):
            log.append("teardown")

    def make_flow_driver(flow, flow_dir):
        return TreeDriver(
            {"work/plan.md": "# nested plan\n"}, flow_dir, on_start=lambda: log.append("session")
        )

    await run_case(
        Lifecycle(_case_files(tmp_path / "case", flows=ONE_FLOW, judge=False)),
        run_id="r",
        make_flow_driver=make_flow_driver,
        make_simulator=_sim,
        run_judge=None,
        runs_root=tmp_path,
    )

    assert log == ["setup", "session", "capture", "score", "teardown"]


@pytest.mark.parametrize("stage", ["setup", "session", "score"])
async def test_teardown_runs_when_a_stage_fails(tmp_path, stage):
    torn_down = []

    class Failing(PlanCase):
        async def setup(self, flow, flow_dir):
            if stage == "setup":
                raise RuntimeError("setup boom")

        async def score(self, flow, flow_dir, session):
            if stage == "score":
                raise RuntimeError("score boom")
            return None

        async def teardown(self, flow, flow_dir):
            torn_down.append(flow["name"])

    class BoomDriver(FakeDriver):
        async def start(self):
            raise RuntimeError("session boom")

    def make_flow_driver(flow, flow_dir):
        if stage == "session":
            return BoomDriver("", [], run_dir=flow_dir)
        return FakeDriver("# plan\n", [], run_dir=flow_dir)

    case = Failing(_case_files(tmp_path / "case", flows=TWO_FLOWS, judge=False))
    kwargs = {
        "run_id": "r",
        "make_flow_driver": make_flow_driver,
        "make_simulator": _sim,
        "run_judge": None,
        "runs_root": tmp_path,
    }

    if stage == "score":  # a scorer failure is isolated: both flows run and tear down
        await run_case(case, **kwargs)
        assert torn_down == ["superpowers", "plain"]
    else:
        with pytest.raises(RuntimeError, match=f"{stage} boom"):
            await run_case(case, **kwargs)
        assert torn_down == ["superpowers"]  # the run aborted, its flow still tore down


async def test_score_returning_none_writes_no_scorecard(tmp_path):
    async def score(flow, flow_dir, session):
        return {"flow": flow["name"]} if flow["name"] == "superpowers" else None

    case = _scored(_case_files(tmp_path / "case", flows=TWO_FLOWS, judge=False), score)
    mfd, ms, _ = n_run_factories([])

    result = await run_case(
        case,
        run_id="r",
        make_flow_driver=mfd,
        make_simulator=ms,
        run_judge=None,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    assert json.loads((root / "superpowers" / "scorecard.json").read_text()) == {
        "flow": "superpowers"
    }
    assert not (root / "plain" / "scorecard.json").exists()


async def test_one_flow_case_runs_and_scores(tmp_path):
    async def score(flow, flow_dir, session):
        return {"flow": flow["name"], "objective": {"acceptance": 1.0}}

    case = _scored(_case_files(tmp_path / "solo", flows=ONE_FLOW, judge=False), score)

    result = await run_case(
        case,
        run_id="solo-run",
        make_flow_driver=lambda flow, flow_dir: FakeDriver(
            "# plan\nplanned.", [], run_dir=flow_dir
        ),
        make_simulator=_sim,
        run_judge=None,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    assert json.loads((root / "plain" / "scorecard.json").read_text()) == {
        "flow": "plain",
        "objective": {"acceptance": 1.0},
    }
    meta = json.loads((root / "run.json").read_text())
    assert meta["flows"] == ["plain"]
    assert meta["labels"] == {"A": "plain"}
    assert meta["winner"] is None and meta["winner_flow"] is None
    assert not (root / "judge.md").exists() and not (root / "report.html").exists()


# --- a judged run end to end -------------------------------------------------


def test_run_a_judged_two_flow_case(tmp_path):
    case = load_case(CASE_DIR)
    sims = []

    def make_flow_driver(flow, flow_dir):
        if flow["name"] == "superpowers":
            return FakeDriver(
                "# SP plan\nunknown flag key returns 404.",
                ["what should evaluation return for an unknown flag key?"],
                run_dir=flow_dir,
            )
        return FakeDriver("# plain plan\nno unknown-key note.", [], run_dir=flow_dir)

    def make_simulator(flow, sim_dir):
        replies = (
            ["a 404 not-found response", DONE_TOKEN]
            if flow["name"] == "superpowers"
            else [DONE_TOKEN]
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
            artifact_grace_s=0.0,
        )
    )

    root = Path(result["run_root"])
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
    assert meta["artifact_missing"] == []
    assert "plans_missing" not in meta and "plan_lines" not in json.dumps(meta)
    # every simulator was closed even though run_agent_session closes only drivers
    assert sims and all(s.closed for s in sims)


def test_run_case_forwards_artifact_grace(tmp_path, monkeypatch):
    calls = []

    async def rec(*args, **kwargs):
        calls.append(kwargs)
        return {"items": [], "events": [], "artifact_text": "# p"}

    monkeypatch.setattr(run_mod, "run_agent_session", rec)

    async def run_judge(judge_md, entries, judge_dir):
        return "WINNER: A"

    asyncio.run(
        run_case(
            load_case(CASE_DIR),
            run_id="t",
            make_flow_driver=lambda flow, flow_dir: FakeDriver("# p", []),
            make_simulator=_sim,
            run_judge=run_judge,
            runs_root=tmp_path,
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
    flow_dir = tmp_path / "todo_app" / "run-1" / "plain"
    d = make_flow_driver_omni(flow, flow_dir)
    assert d.run_dir == flow_dir
    assert d.model == "opus"
    assert d.harness == "claude-native"
    assert d.skills == "none"
    assert d.reasoning_effort == "xhigh"
    assert d.turn_timeout_s == 1800  # planning turns run way past the driver's 240s default
    assert d.stall_s == 300  # watchdog (#54) is per-flow tunable like the turn cap
    assert make_flow_driver_omni({"name": "x", "turn_timeout_s": 60}, flow_dir).turn_timeout_s == 60
    # web-UI grouping: one project folder per run, case-and-role titles
    assert d.session_title == "todo_app · flow: plain"
    assert d.project == "todo_app/run-1"


def test_run_n_writes_one_trial_dir_per_trial(tmp_path):
    case = load_case(CASE_DIR)
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
    assert root == tmp_path / "feature_flag_service" / "agg-run"
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


def test_aggregate_run_json_carries_the_deliverable(tmp_path):
    mfd, ms, rj = n_run_factories(["A", "B"])
    result = asyncio.run(
        run_case_n(
            load_case(CASE_DIR),
            run_id="agg-deliverable",
            n=2,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )

    agg = json.loads((Path(result["run_root"]) / "run.json").read_text())
    assert agg["case"] == "feature_flag_service"
    assert agg["deliverable"] == "plan.md"
    assert "scenario" not in agg


def test_run_case_n_single_trial_keeps_flat_layout(tmp_path):
    case = load_case(CASE_DIR)
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
    assert root == tmp_path / "feature_flag_service" / "single-run"
    # flat single-run layout, no trial dirs, run.json is the single-run meta
    assert not (root / "trial-01").exists()
    assert (root / "superpowers" / "plan.md").is_file()
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner"] == "a"
    assert meta["winner_flow"] == "superpowers"
    assert result["trials"] == [meta]


def test_run_case_n_rejects_bad_n(tmp_path):
    mfd, ms, rj = n_run_factories([])
    with pytest.raises(ValueError):
        asyncio.run(
            run_case_n(
                load_case(CASE_DIR),
                run_id="x",
                n=0,
                make_flow_driver=mfd,
                make_simulator=ms,
                run_judge=rj,
                runs_root=tmp_path,
            )
        )


def test_run_case_n_failing_trial_propagates(tmp_path):
    case = load_case(CASE_DIR)
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
            )
        )

    # trial 1 completed and its artifacts remain; trial 3 never started
    assert calls["n"] == 2
    root = tmp_path / "feature_flag_service" / "fail-run"
    assert (root / "trial-01" / "judge.md").is_file()
    assert not (root / "trial-03").exists()
    # no aggregate run.json was written for the aborted run
    assert not (root / "run.json").exists()


def test_run_case_writes_report_html_and_flow_stats(tmp_path):
    mfd, ms, rj = n_run_factories(["A"])
    result = asyncio.run(
        run_case(
            load_case(CASE_DIR),
            run_id="report-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )
    root = Path(result["run_root"])
    html_text = (root / "report.html").read_text()
    assert "flowbench run report" in html_text
    assert "superpowers" in html_text and "plain" in html_text
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner_flow"] == "superpowers"
    stats = meta["flow_stats"]["superpowers"]
    assert stats["artifact_lines"] == 2  # the fake's two-line plan
    assert "context_tokens" in stats and "exit_status" in stats


def test_run_case_rotation_reverses_judge_order(tmp_path):
    seen = {}

    async def run_judge(judge_md, entries, judge_dir):
        seen["plan_a"] = entries[0][2]
        return "WINNER: A\nA: ok\nB: ok"

    mfd, ms, _ = n_run_factories([])
    result = asyncio.run(
        run_case(
            load_case(CASE_DIR),
            run_id="swap-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=run_judge,
            runs_root=tmp_path,
            rotation=1,
        )
    )
    assert "plain plan" in seen["plan_a"]  # plain judged as A when rotated
    meta = result["meta"]
    assert meta["labels"] == {"A": "plain", "B": "superpowers"}
    assert meta["rotation"] == 1
    assert meta["winner_flow"] == "plain"  # positional "a" resolved via labels


def test_run_parts_and_title_and_project(tmp_path):
    flat = tmp_path / "todo_app" / "run-7" / "plain"
    assert _run_parts(flat) == ("todo_app", "run-7", None)
    assert _title(flat, "flow: plain") == "todo_app · flow: plain"
    assert _project(flat) == "todo_app/run-7"

    trial = tmp_path / "todo_app" / "run-7" / "trial-01" / "plain"
    assert _run_parts(trial) == ("todo_app", "run-7", "trial-01")
    assert _title(trial, "flow: plain") == "todo_app · trial-01 · flow: plain"
    assert _project(trial) == "todo_app/run-7"


def test_project_groups_trials_under_the_run(tmp_path):
    assert _project(tmp_path / "todo_app" / "todo-010" / "plain") == "todo_app/todo-010"
    assert (
        _project(tmp_path / "todo_app" / "todo-010" / "trial-01" / "plain") == "todo_app/todo-010"
    )


def test_title_includes_trial_segment(tmp_path):
    assert _title(tmp_path / "todo_app" / "todo-x" / "plain", "sim: plain") == (
        "todo_app · sim: plain"
    )
    assert _title(tmp_path / "todo_app" / "todo-x" / "trial-02" / "plain", "sim: plain") == (
        "todo_app · trial-02 · sim: plain"
    )


def test_make_flow_driver_threads_skill_dirs(tmp_path):
    flow = {
        "name": "codex",
        "harness": "codex-native",
        "model": "gpt-5.5",
        "skill_dirs": [tmp_path / "skills" / "brainstorming"],
    }
    d = make_flow_driver_omni(flow, tmp_path)
    assert d.skill_dirs == [tmp_path / "skills" / "brainstorming"]
    assert d.harness == "codex-native"
    assert d.model == "gpt-5.5"


def test_make_flow_driver_defaults_no_skill_dirs(tmp_path):
    d = make_flow_driver_omni({"name": "x"}, tmp_path)
    assert d.skill_dirs == []


# --- N-way (3-flow) coverage -------------------------------------------------


def _three_flow_case(tmp_path) -> Case:
    """A synthetic 3-flow case: the fixture's task/sim/judge text, three flows."""
    return PlanCase(_case_files(tmp_path / "three_flow_case", flows=THREE_FLOWS))


def _three_flow_factories():
    def make_flow_driver(flow, flow_dir):
        return FakeDriver(
            f"# {flow['name']} plan\ncontent for {flow['name']}.", [], run_dir=flow_dir
        )

    return make_flow_driver, _sim


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
            load_case(CASE_DIR),
            run_id="single",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path / "runs",
        )
    )
    text = render_any(Path(result["run_root"])).read_text()
    assert "flowbench run report" in text
    assert "flowbench aggregate report" not in text


def test_run_case_n_writes_aggregate_report(tmp_path):
    # trial-02 rotates: positional B is superpowers, so A,B -> superpowers 2-0
    mfd, ms, rj = n_run_factories(["A", "B"])
    result = asyncio.run(
        run_case_n(
            load_case(CASE_DIR),
            run_id="agg-report-run",
            n=2,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )
    text = (Path(result["run_root"]) / "report.html").read_text()
    assert "flowbench aggregate report" in text
    assert "superpowers wins 2–0 (n=2)" in text
    assert 'href="trial-01/report.html"' in text
    assert 'href="trial-02/report.html"' in text
    # scripted judge emits no SCORES lines -> section omitted, no crash
    assert "Score means" not in text


def test_make_simulator_omni_is_bare_claude_on_a_session_model(tmp_path):
    sim_dir = tmp_path / "todo_app" / "run-1" / "_sim_plain"
    sim = run_mod.make_simulator_omni({"name": "plain"}, sim_dir, model="haiku")
    d = sim._driver
    assert d.skills == "none" and d.model == "haiku"
    # web-UI grouping: the sim shares its run's folder, like the flow and judge
    assert d.session_title == "todo_app · sim: plain"
    assert d.project == "todo_app/run-1"


def test_run_judge_omni_generates_once_and_closes(tmp_path, monkeypatch):
    seen = {}

    class _Model:
        def __init__(self, driver):
            seen["driver"] = driver
            self.closed = False

        async def generate(self, prompt):
            seen["prompt"] = prompt

            class _Out:
                completion = "WINNER: A"

            return _Out()

        async def close(self):
            seen["closed"] = True

    monkeypatch.setattr(run_mod, "SessionModel", _Model)
    judge_dir = tmp_path / "todo_app" / "todo-1" / "_judge"
    out = asyncio.run(
        run_mod.run_judge_omni("rubric", [("A", "t", "plan a")], judge_dir, model="sonnet")
    )
    assert out == "WINNER: A" and seen["closed"] is True
    assert seen["prompt"].startswith("rubric")
    d = seen["driver"]
    assert d.model == "sonnet" and d.turn_timeout_s == 600
    assert d.project == "todo_app/todo-1" and d.session_title == "todo_app · judge"


@pytest.mark.parametrize("trial", [None, "trial-01"])
def test_every_role_driver_carries_the_case_and_trial(tmp_path, monkeypatch, trial):
    """Flow, sim and judge label themselves off the run layout alone: the case,
    the trial when there is one, and the run they all belong to."""
    run_root = tmp_path / "todo_app" / "run-7"
    if trial is not None:
        run_root = run_root / trial
    prefix = f"todo_app · {trial}" if trial is not None else "todo_app"
    drivers = []

    class _Model:
        def __init__(self, driver):
            drivers.append(driver)

        async def generate(self, prompt):
            class _Out:
                completion = "WINNER: A"

            return _Out()

        async def close(self):
            pass

    monkeypatch.setattr(run_mod, "SessionModel", _Model)
    flow_driver = make_flow_driver_omni({"name": "plain"}, run_root / "plain")
    run_mod.make_simulator_omni({"name": "plain"}, run_root / "_sim_plain", model="haiku")
    asyncio.run(
        run_mod.run_judge_omni("rubric", [("A", "t", "p")], run_root / "_judge", model="sonnet")
    )

    sim_driver, judge_driver = drivers
    assert flow_driver.session_title == f"{prefix} · flow: plain"
    assert sim_driver.session_title == f"{prefix} · sim: plain"
    assert judge_driver.session_title == f"{prefix} · judge"
    # one benchmark run is one web-UI folder, trials included
    assert {d.project for d in (flow_driver, sim_driver, judge_driver)} == {"todo_app/run-7"}


def test_omni_factories_read_models_from_case_settings(tmp_path):
    case = PlanCase(
        tmp_path / "case_dir", settings=Settings(sim_model="haiku", judge_model="sonnet")
    )
    mk_flow, mk_sim, judge = run_mod.omni_factories(case)
    assert mk_flow is run_mod.make_flow_driver_omni  # nothing to bind: the flow carries its model
    assert mk_sim.func is run_mod.make_simulator_omni
    assert judge.func is run_mod.run_judge_omni
    assert mk_sim.keywords == {"model": "haiku"}
    assert judge.keywords == {"model": "sonnet"}


# --- the case's own grading, with no judge ----------------------------------


def _unjudged_case(tmp_path, score_fn=None) -> Case:
    """The fixture's two flows, minus judge.md — a build-shaped case."""
    case_dir = _case_files(tmp_path / "unjudged_case", flows=TWO_FLOWS, judge=False)
    return PlanCase(case_dir) if score_fn is None else _scored(case_dir, score_fn)


def test_case_score_writes_a_scorecard_per_flow_with_no_judge(tmp_path):
    async def score(flow, flow_dir, session):
        return {"flow": flow["name"], "objective": {"acceptance": 1.0}}

    mfd, ms, _ = n_run_factories([])
    result = asyncio.run(
        run_case(
            _unjudged_case(tmp_path, score),
            run_id="unjudged-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=None,
            runs_root=tmp_path,
            artifact_grace_s=0.0,
        )
    )
    root = Path(result["run_root"])
    for name in ("superpowers", "plain"):
        card = json.loads((root / name / "scorecard.json").read_text())
        assert card == {"flow": name, "objective": {"acceptance": 1.0}}
    assert not (root / "_judge").exists()
    assert not (root / "judge.md").exists()
    assert not (root / "report.html").exists()
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner"] is None
    assert meta["labels"] == {"A": "superpowers", "B": "plain"}


@pytest.mark.parametrize("n", [1, 2])  # n=1 is the CLI default and takes its own branch
def test_run_case_n_unjudged_aggregate_empty(tmp_path, n):
    async def score(flow, flow_dir, session):
        return {"flow": flow["name"]}

    mfd, ms, _ = n_run_factories([])
    result = asyncio.run(
        run_case_n(
            _unjudged_case(tmp_path, score),
            run_id="unjudged-agg",
            n=n,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=None,
            runs_root=tmp_path,
        )
    )
    assert result["aggregate"] == {"n": n, "counts": {}, "winner": None}
    root = Path(result["run_root"])
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner"] is None
    if n > 1:  # n=1 writes run_case's own meta; the aggregate keys/report exist only for n>1
        assert meta["counts"] == {} and meta["score_means"] == {}
        assert (root / "report.html").is_file()


def test_case_score_error_is_isolated(tmp_path):
    calls = {"n": 0}

    async def score(flow, flow_dir, session):
        calls["n"] += 1
        if flow["name"] == "superpowers":
            raise RuntimeError("boom")
        return {"flow": flow["name"], "objective": {"acceptance": 1.0}}

    mfd, ms, _ = n_run_factories([])
    result = asyncio.run(
        run_case(
            _unjudged_case(tmp_path, score),
            run_id="err-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=None,
            runs_root=tmp_path,
            artifact_grace_s=0.0,
        )
    )
    root = Path(result["run_root"])
    sp_card = json.loads((root / "superpowers" / "scorecard.json").read_text())
    assert sp_card == {"error": "RuntimeError: boom"}
    plain_card = json.loads((root / "plain" / "scorecard.json").read_text())
    assert plain_card == {"flow": "plain", "objective": {"acceptance": 1.0}}
    meta = json.loads((root / "run.json").read_text())
    assert meta["flow_stats"]["superpowers"]["score_error"] == "RuntimeError: boom"
    assert calls["n"] == 2

    from flowbench.report.compare import compare_table, load_scorecards

    cards = load_scorecards(root.parent, root.name)
    table = compare_table(cards)
    assert "FAILED (RuntimeError: boom)" in table
    lines = table.splitlines()
    status_line = next(line for line in lines if line.startswith("| _status_"))
    assert "ok" in status_line


def test_no_score_override_writes_no_scorecard_and_still_judges(tmp_path):
    mfd, ms, rj = n_run_factories(["A"])
    result = asyncio.run(
        run_case(
            load_case(CASE_DIR),
            run_id="judged-run",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )
    root = Path(result["run_root"])
    assert not (root / "superpowers" / "scorecard.json").exists()
    assert (root / "report.html").is_file()
    assert (root / "judge.md").is_file()


# --- deliverable shapes ------------------------------------------------------


async def test_file_deliverable_still_carries_its_text(tmp_path):
    mfd, ms, rj = n_run_factories(["A"])
    result = await run_case(
        load_case(CASE_DIR),
        run_id="file-run",
        make_flow_driver=mfd,
        make_simulator=ms,
        run_judge=rj,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    assert (root / "superpowers" / "plan.md").read_text().startswith("# SP plan")
    stats = json.loads((root / "run.json").read_text())["flow_stats"]["superpowers"]
    assert stats["artifact_lines"] == 2
    assert stats["deliverable_path"] == "plan.md"


async def test_nested_file_deliverable_is_copied_to_the_flow_dir(tmp_path):
    """A declared `out/result.txt` the agent wrote under a subagent's cwd: the
    canonical copy lands at the flow-dir root, its parent dir created for it."""
    case = _scored(
        _case_files(tmp_path / "case", flows=ONE_FLOW, judge=False),
        _card,
        deliverable="out/result.txt",
    )

    result = await run_case(
        case,
        run_id="nested",
        make_flow_driver=lambda flow, flow_dir: TreeDriver(
            {"work/out/result.txt": "ported\n"}, flow_dir
        ),
        make_simulator=_sim,
        run_judge=None,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    assert (root / "plain" / "out" / "result.txt").read_text() == "ported\n"
    stats = json.loads((root / "run.json").read_text())["flow_stats"]["plain"]
    assert stats["deliverable_path"] == "work/out/result.txt"
    assert stats["artifact_lines"] == 1


async def test_directory_deliverable_is_present_with_no_text(tmp_path):
    """A directory is left where it is — `deliverable_path` is how a reader
    reaches a nested one."""
    case = _scored(
        _case_files(tmp_path / "case", flows=ONE_FLOW, judge=False), _card, deliverable="port"
    )

    result = await run_case(
        case,
        run_id="dir-run",
        make_flow_driver=lambda flow, flow_dir: TreeDriver(
            {"work/port/a.sql": "select 1\n", "work/port/b/c.sql": "select 2\n"}, flow_dir
        ),
        make_simulator=_sim,
        run_judge=None,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    flow_dir = root / "plain"
    session = json.loads((flow_dir / "session.json").read_text())
    assert session["artifact_exists"] is True
    assert session["artifact_text"] is None
    assert not (flow_dir / "port").exists()  # never copied
    meta = json.loads((root / "run.json").read_text())
    stats = meta["flow_stats"]["plain"]
    assert stats["deliverable_path"] == "work/port"
    assert stats["artifact_lines"] == 0
    assert meta["artifact_missing"] == []
    assert _judge_view(case, session) == "(port/ — 2 files)\na.sql\nb/c.sql"


async def test_empty_directory_deliverable_is_present_not_missing(tmp_path):
    case = _scored(
        _case_files(tmp_path / "case", flows=ONE_FLOW, judge=False), _card, deliverable="port"
    )

    result = await run_case(
        case,
        run_id="empty-dir",
        make_flow_driver=lambda flow, flow_dir: TreeDriver({"port/": ""}, flow_dir),
        make_simulator=_sim,
        run_judge=None,
        runs_root=tmp_path,
        artifact_grace_s=0.0,
    )

    root = Path(result["run_root"])
    session = json.loads((root / "plain" / "session.json").read_text())
    assert session["artifact_exists"] is True and session["artifact_text"] is None
    meta = json.loads((root / "run.json").read_text())
    assert meta["artifact_missing"] == []  # present, though it holds nothing
    assert meta["flow_stats"]["plain"]["deliverable_path"] == "port"
    assert _judge_view(case, session) == "(port/ — 0 files)"


async def test_missing_deliverable_marks_the_flow_and_the_judge_entry(tmp_path):
    seen = {}

    def make_flow_driver(flow, flow_dir):
        if flow["name"] == "superpowers":
            return FakeDriver("# SP plan\nunknown flag key returns 404.", [], run_dir=flow_dir)
        return MissingPlanDriver("unused", [], run_dir=flow_dir)

    async def run_judge(judge_md, entries, judge_dir):
        seen.update({label: plan for label, _transcript, plan in entries})
        return "A is better.\nWINNER: A\nA: thorough\nB: missing"

    result = await run_case(
        load_case(CASE_DIR),
        run_id="missing-run",
        make_flow_driver=make_flow_driver,
        make_simulator=_sim,
        run_judge=run_judge,
        runs_root=tmp_path,
        artifact_grace_s=0.0,
    )

    root = Path(result["run_root"])
    assert not (root / "plain" / "plan.md").exists()  # nothing to capture, nothing written
    assert seen["B"] == MISSING_DELIVERABLE("plan.md")
    meta = json.loads((root / "run.json").read_text())
    assert meta["artifact_missing"] == ["plain"]
    assert meta["flow_stats"]["plain"]["deliverable_path"] is None
    assert meta["flow_stats"]["plain"]["artifact_lines"] == 0


async def test_no_deliverable_omits_the_artifact_keys(tmp_path):
    case = _scored(
        _case_files(tmp_path / "case", flows=TWO_FLOWS, judge=False), _card, deliverable=None
    )
    result = await run_case(
        case,
        run_id="no-deliverable",
        make_flow_driver=lambda flow, flow_dir: FakeDriver("# p", [], run_dir=flow_dir),
        make_simulator=_sim,
        run_judge=None,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    run_json_text = (root / "run.json").read_text()
    for key in ("artifact_missing", "artifact_lines", "deliverable_path", "plans_missing"):
        assert key not in run_json_text
    for name in ("superpowers", "plain"):
        assert (root / name / "session.json").is_file()
        assert (root / name / "transcript.md").is_file()
        assert json.loads((root / name / "scorecard.json").read_text()) == {"flow": name}


async def test_no_deliverable_with_judge_reports_null_and_no_missing_key(tmp_path):
    """A judged case may declare no deliverable: the flows are then compared on
    their conversations alone."""
    seen = {}

    async def run_judge(judge_md, entries, judge_dir):
        seen.update({label: plan for label, _transcript, plan in entries})
        return "A is better.\nWINNER: A\nA: ok\nB: ok"

    case = Case(_case_files(tmp_path / "case", flows=TWO_FLOWS, judge=True))
    result = await run_case(
        case,
        run_id="judged-no-deliverable",
        make_flow_driver=lambda flow, flow_dir: FakeDriver("# p", [], run_dir=flow_dir),
        make_simulator=_sim,
        run_judge=run_judge,
        runs_root=tmp_path,
    )

    root = Path(result["run_root"])
    assert seen == {"A": NO_DELIVERABLE, "B": NO_DELIVERABLE}
    assert (root / "judge.md").is_file() and (root / "report.html").is_file()
    meta = json.loads((root / "run.json").read_text())
    assert meta["deliverable"] is None
    assert "artifact_missing" not in meta
    assert "artifact_lines" not in json.dumps(meta)


def test_what_the_judge_is_shown_for_each_deliverable_shape(tmp_path):
    plan_case = PlanCase(CASE_DIR)
    port = tmp_path / "port"
    (port / "b").mkdir(parents=True)
    (port / "a.sql").write_text("select 1\n")
    (port / "b" / "c.sql").write_text("select 2\n")
    dir_case = type("DirCase", (Case,), {"deliverable": "port"})(CASE_DIR)

    # a file: its text; an empty file: its (empty) text — presence, not truthiness
    assert _judge_view(plan_case, {"artifact_exists": True, "artifact_text": "# plan\n"}) == (
        "# plan\n"
    )
    assert _judge_view(plan_case, {"artifact_exists": True, "artifact_text": ""}) == ""
    # absent: the missing marker
    assert _judge_view(plan_case, {"artifact_exists": False, "artifact_text": None}) == (
        MISSING_DELIVERABLE("plan.md")
    )
    # a directory: no text, so a sorted listing
    session = {"artifact_exists": True, "artifact_text": None, "artifact_path": str(port)}
    assert _judge_view(dir_case, session) == "(port/ — 2 files)\na.sql\nb/c.sql"
    # none declared: the conversations are the whole evidence
    assert _judge_view(Case(CASE_DIR), session) == NO_DELIVERABLE


async def test_the_probe_is_the_cases_find_deliverable(tmp_path, monkeypatch):
    calls = []

    async def rec(*args, **kwargs):
        calls.append(kwargs)
        return {"items": [], "events": []}

    monkeypatch.setattr(run_mod, "run_agent_session", rec)
    mfd, ms, _ = n_run_factories([])
    common = {
        "make_flow_driver": mfd,
        "make_simulator": ms,
        "run_judge": None,
        "runs_root": tmp_path,
        "artifact_grace_s": 30.0,
    }
    case_dir = _case_files(tmp_path / "case", flows=TWO_FLOWS, judge=False)

    await run_case(_scored(case_dir, _card, deliverable=None), run_id="t-none", **common)
    assert calls
    assert all(kwargs["artifact_probe"] is None for kwargs in calls)
    assert all(kwargs["artifact_grace_s"] == 30.0 for kwargs in calls)

    calls.clear()
    case = _scored(case_dir, _card)  # PlanCase: declares plan.md
    result = await run_case(case, run_id="t-plan", **common)
    root = Path(result["run_root"])
    assert calls
    for name, kwargs in zip([f["name"] for f in TWO_FLOWS], calls, strict=True):
        probe = kwargs["artifact_probe"]
        assert probe.func == case.find_deliverable
        assert probe.args == (root / name,)
