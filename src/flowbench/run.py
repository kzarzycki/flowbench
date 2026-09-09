"""Orchestrator: the simulator, each flow, and the judge all run as omnigent
sessions via flowbench's OmnigentDriver — never `claude -p`.

Outputs land in <runs_root>/<run_id>/ (per-flow subfolders), never inside the
repo. Offline tests inject fakes for the three factories."""

from __future__ import annotations

import functools
import json
import string
from pathlib import Path

from flowbench.driver import OmnigentDriver
from flowbench.flowspec import compose_kickoff, load_flows
from flowbench.loop import run_agent_session
from flowbench.model import SessionModel
from flowbench.report.run_report import render_aggregate_report, render_report
from flowbench.runner.judge import (
    aggregate_scores,
    aggregate_verdicts,
    build_judge_prompt,
    parse_verdict,
)
from flowbench.transcript import render_transcript

DONE_TOKEN = "PLAN_COMPLETE"
MISSING_PLAN = "(this flow produced no plan.md — treat it as a failed run)"
SIM_MODEL = "opus"
JUDGE_MODEL = "opus"


async def run_case(
    case_dir,
    *,
    run_id: str,
    make_flow_driver,
    make_simulator,
    run_judge,
    runs_root,
    scenario: str,
    max_turns: int = 80,
    deadline_s: float = 1800.0,
    artifact_grace_s: float = 60.0,
    rotation: int = 0,
    done_token: str = DONE_TOKEN,
    score_flow=None,
    artifact_name: str | None = "plan.md",
) -> dict:
    """Spawn simulator + each flow, run the mediated loop, collect artifacts,
    then judge. Omnigent-specific spawning is injected via the three factories
    so the whole pipeline runs offline with fakes. `rotation` rotates the flow
    list left by rotation % N so multi-trial runs cancel judge position bias.

    `artifact_name=None` means the case declares no artifact (a build-shaped
    case like todo_app, judged black-box): no `<flow>/plan.md` is written, no
    `artifact_missing`/`artifact_lines` keys appear in `run.json`, and the
    artifact grace-poll is skipped.

    `score_flow(flow, flow_dir, session) -> dict`, when given, is called after
    each flow's session and its result written to `<flow_dir>/scorecard.json`;
    a raised exception is caught and recorded as `{"error": ...}` instead of
    aborting the run. The comparative judge stage runs only when the case
    carries a `judge.md` (a build-shaped case like todo_app has none — each
    flow is scored on its own instead)."""
    case_dir = Path(case_dir)
    task_text = (case_dir / "task.md").read_text()
    sim_system = (
        (case_dir / "simulator.md").read_text()
        + "\n\n--- WHAT YOU KNOW ---\n\n"
        + (case_dir / "knowledge.md").read_text()
    )
    judge_path = case_dir / "judge.md"
    has_judge = judge_path.exists()
    judge_md = judge_path.read_text() if has_judge else None
    has_artifact = artifact_name is not None
    if artifact_name is None and has_judge:
        raise ValueError(
            f"{case_dir}: artifact_name=None is incompatible with judge.md "
            "— the HTML report needs <flow>/plan.md"
        )
    flows = load_flows(case_dir / "flows.yaml")
    if len(flows) < 2:
        raise ValueError(f"run_case judges 2+ flows, got {len(flows)}")
    r = rotation % len(flows)
    flows = flows[r:] + flows[:r]

    run_root = Path(runs_root) / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    plans: dict[str, str | None] = {}
    transcripts: dict[str, str] = {}
    flow_stats: dict[str, dict] = {}
    for flow in flows:
        name = flow["name"]
        flow_dir = run_root / name
        flow_dir.mkdir(parents=True, exist_ok=True)
        sim_dir = run_root / f"_sim_{name}"
        sim_dir.mkdir(parents=True, exist_ok=True)
        driver = make_flow_driver(flow, flow_dir)
        simulator = make_simulator(flow, sim_dir)
        try:
            # run_agent_session closes the flow driver itself (its own finally);
            # the simulator is ours to close.
            session = await run_agent_session(
                driver,
                simulator,
                first_prompt=compose_kickoff(flow, task_text),
                simulator_system=sim_system,
                done_token=done_token,
                max_turns=max_turns,
                deadline_s=deadline_s,
                artifact_grace_s=(artifact_grace_s if has_artifact else 0.0),
            )
        finally:
            close = getattr(simulator, "close", None)
            if close is not None:
                await close()

        plan_text = session.get("artifact_text")
        transcript_text = render_transcript(session.get("items") or [])
        if has_artifact:
            (flow_dir / "plan.md").write_text(plan_text or "")
        (flow_dir / "transcript.md").write_text(transcript_text)
        (flow_dir / "session.json").write_text(json.dumps(session, indent=2, default=str))
        plans[name] = plan_text
        transcripts[name] = transcript_text
        flow_stats[name] = {
            "exit_status": session.get("exit_status"),
            "turns": session.get("turns"),
            "duration_s": session.get("duration_s"),
            **({"artifact_lines": len((plan_text or "").splitlines())} if has_artifact else {}),
            "context_tokens": session.get("context_tokens"),
        }
        if score_flow is not None:
            try:
                card = await score_flow(flow, flow_dir, session)
            except Exception as e:  # noqa: BLE001 - isolate one flow's scorer, never abort the run
                error = f"{type(e).__name__}: {e}"
                card = {"error": error}
                flow_stats[name]["score_error"] = error
            (flow_dir / "scorecard.json").write_text(json.dumps(card, indent=2, default=str))

    # Rotated flow order defines this trial's judge-facing labels A, B, C…
    names = [f["name"] for f in flows]
    letters = string.ascii_uppercase[: len(flows)]
    labels = dict(zip(letters, names, strict=True))  # {"A": name, "B": name, ...}
    if has_judge:
        entries = [
            (letter, transcripts[name], plans[name] if plans[name] else MISSING_PLAN)
            for letter, name in zip(letters, names, strict=True)
        ]
        judge_dir = run_root / "_judge"
        judge_dir.mkdir(parents=True, exist_ok=True)
        verdict_text = await run_judge(judge_md, entries, judge_dir)
        (run_root / "judge.md").write_text(verdict_text)
        verdict = parse_verdict(verdict_text)
        winner_flow = labels.get(verdict["winner"].upper(), verdict["winner"])
    else:
        verdict = {"winner": None, "scores": {}}
        winner_flow = None

    meta = {
        "run_id": run_id,
        "scenario": scenario,
        "case": case_dir.name,
        "flows": names,
        "labels": labels,  # {"A": flow_name, ...} — judge-facing, this trial only
        "rotation": rotation,
        "winner": verdict["winner"],  # judge letter, or tie/unknown
        "winner_flow": winner_flow,  # flow NAME (order-independent), or tie/unknown
        "scores": verdict.get("scores"),
        **({"artifact_missing": [n for n, p in plans.items() if not p]} if has_artifact else {}),
        "flow_stats": flow_stats,
        "models": {f["name"]: f.get("model") for f in flows},
        "reasoning_effort": {f["name"]: f.get("reasoning_effort") for f in flows},
    }
    (run_root / "run.json").write_text(json.dumps(meta, indent=2, default=str))
    if has_judge:
        render_report(run_root)  # pure reader over the files just written
    return {"run_root": str(run_root), "verdict": verdict, "meta": meta}


async def run_case_n(
    case_dir,
    *,
    run_id: str,
    n: int,
    make_flow_driver,
    make_simulator,
    run_judge,
    runs_root,
    scenario: str,
    max_turns: int = 80,
    deadline_s: float = 1800.0,
    done_token: str = DONE_TOKEN,
    score_flow=None,
    artifact_name: str | None = "plan.md",
) -> dict:
    """Run run_case n times (sequentially; a failing trial propagates) and
    aggregate the categorical verdicts. Uniform return shape for every n:
    {"run_root", "trials", "aggregate"}. n=1 delegates and keeps today's
    flat layout; n>1 writes trial-XX/ subdirs plus an aggregate run.json.
    A case without judge.md never produces a winner_flow — the aggregate is
    then {"counts": {}, "winner": None} rather than tallying None as a flow."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    kwargs = {
        "make_flow_driver": make_flow_driver,
        "make_simulator": make_simulator,
        "run_judge": run_judge,
        "runs_root": runs_root,
        "scenario": scenario,
        "max_turns": max_turns,
        "deadline_s": deadline_s,
        "done_token": done_token,
        "score_flow": score_flow,
        "artifact_name": artifact_name,
    }

    names = [f["name"] for f in load_flows(Path(case_dir) / "flows.yaml")]

    if n == 1:
        result = await run_case(case_dir, run_id=run_id, **kwargs)
        winner_flow = result["meta"]["winner_flow"]
        agg = (
            aggregate_verdicts([winner_flow])
            if winner_flow is not None
            else {
                "counts": {},
                "winner": None,
            }
        )
        return {
            "run_root": result["run_root"],
            "trials": [result["meta"]],
            "aggregate": {"n": 1, **agg},
        }

    trials = []
    for k in range(1, n + 1):
        # Trial k rotates the flow list so multi-trial runs cancel judge
        # position bias; everything cross-trial keys by flow NAME, not label.
        result = await run_case(
            case_dir, run_id=f"{run_id}/trial-{k:02d}", rotation=(k - 1) % len(names), **kwargs
        )
        trials.append(result["meta"])

    def _name_keyed_scores(t: dict) -> dict:
        labels = t.get("labels") or {}
        scores = t.get("scores") or {}
        return {labels.get(letter.upper(), letter): v for letter, v in scores.items()}

    judged = [t["winner_flow"] for t in trials if t.get("winner_flow") is not None]
    if judged:
        agg = aggregate_verdicts(judged)
        counts, winner = agg["counts"], agg["winner"]
        score_means = aggregate_scores([_name_keyed_scores(t) for t in trials])
    else:
        counts, winner, score_means = {}, None, {}
    run_root = Path(runs_root) / run_id
    aggregate_meta = {
        "run_id": run_id,
        "scenario": scenario,
        "case": Path(case_dir).name,
        "n": n,
        "flows": names,  # flows.yaml order, name-keyed everything below
        "trials": [
            {"trial": f"trial-{k:02d}", "winner_flow": t.get("winner_flow")}
            for k, t in enumerate(trials, 1)
        ],
        "counts": counts,
        "winner": winner,
        "score_means": score_means,  # per flow name, mean per criterion
    }
    (run_root / "run.json").write_text(json.dumps(aggregate_meta, indent=2, default=str))
    render_aggregate_report(run_root)  # pure reader over the files just written
    return {
        "run_root": str(run_root),
        "trials": trials,
        "aggregate": {"n": n, "counts": counts, "winner": winner},
    }


async def rescore_run(case_dir, run_root, *, score_flow) -> dict[str, str]:
    """Re-run `score_flow` over an existing run dir, without starting a
    session: rewrites `<flow>/scorecard.json` and `flow_stats[flow].score_error`
    from what is already on disk (`<flow>/session.json` + the case's current
    flows.yaml). Never touches transcripts or session.json.

    Covers both layouts: the flat `n=1` run dir itself, and each `trial-XX/`
    of an `n>1` run (its own aggregate `run.json` has no `flow_stats` and is
    left untouched). A flow with no `session.json` (never ran, or was never
    part of this run) is skipped — recorded neither in the return map nor
    touched on disk. A flow named in `run.json` but absent from the case's
    current flows.yaml (edited since the run) is deliberately NOT special-
    cased: the lookup sits inside the same try/except as the scorer call, so
    it is recorded as a `KeyError` like any other scorer failure — rescoring
    against a config that no longer matches the run would be worse than a
    recorded error."""
    run_root = Path(run_root)
    flows_by_name = {f["name"]: f for f in load_flows(Path(case_dir) / "flows.yaml")}

    results: dict[str, str] = {}
    targets = [run_root, *sorted(run_root.glob("trial-*"))]
    for target in targets:
        run_json_path = target / "run.json"
        if not run_json_path.is_file():
            continue
        meta = json.loads(run_json_path.read_text())
        if not isinstance(meta, dict) or "flow_stats" not in meta:
            continue

        is_trial = target != run_root
        changed = False
        for name in meta.get("flows", []):
            flow_dir = target / name
            session_path = flow_dir / "session.json"
            if not session_path.is_file():
                continue
            session = json.loads(session_path.read_text())
            key = f"{target.name}/{name}" if is_trial else name
            stats = meta["flow_stats"].setdefault(name, {})
            try:
                flow = flows_by_name[name]
                card = await score_flow(flow, flow_dir, session)
            except Exception as e:  # noqa: BLE001 - isolate one flow's scorer, never abort the rescore
                error = f"{type(e).__name__}: {e}"
                card = {"error": error}
                stats["score_error"] = error
                results[key] = error
            else:
                stats.pop("score_error", None)
                results[key] = "ok"
            (flow_dir / "scorecard.json").write_text(json.dumps(card, indent=2, default=str))
            changed = True

        if changed:
            run_json_path.write_text(json.dumps(meta, indent=2, default=str))

    return results


# --- the real omnigent factories -------------------------------------------


def _title(run_dir: Path, base: str) -> str:
    # n>1 nests roles under trial-XX — put the trial in the session title so
    # the web UI's "sim: plain" chats are tellable apart across trials.
    trial = run_dir.parent.name
    return f"{trial} · {base}" if trial.startswith("trial-") else base


def _project(run_dir: Path, scenario: str) -> str:
    # <runs_root>/<run_id>/<role_dir> -> "<scenario>/<run_id>"; groups all of a
    # run's sessions into one web-UI project folder (omni_project label). n>1
    # nests trials (<run_id>/trial-01/<role_dir>) — group by the RUN, not the
    # trial, so one benchmark run is one folder.
    parent = run_dir.parent
    if parent.name.startswith("trial-"):
        parent = parent.parent
    return f"{scenario}/{parent.name}"


def make_flow_driver_omni(
    flow: dict,
    flow_dir: Path,
    *,
    scenario: str,
    artifact_name: str = "plan.md",
    git_init: bool = False,
) -> OmnigentDriver:
    return OmnigentDriver(
        run_dir=flow_dir,
        artifact_name=artifact_name,
        git_init=git_init,
        session_title=_title(flow_dir, f"flow: {flow['name']}"),
        project=_project(flow_dir, scenario),
        model=flow.get("model", "opus"),
        harness=flow.get("harness", "claude-native"),
        skills=flow.get("skills", "all"),
        skill_dirs=flow.get("skill_dirs", []),
        reasoning_effort=flow.get("reasoning_effort"),
        # A planning turn (e.g. superpowers writing-plans) runs way past the
        # driver's 240s default — live-001 lost its plan to that timeout.
        turn_timeout_s=flow.get("turn_timeout_s", 1800),
        stall_s=flow.get("stall_s", 300),
    )


def make_simulator_omni(flow: dict, sim_dir: Path, *, scenario: str) -> SessionModel:
    # Bare Claude Code (skills: none): the simulator only answers questions.
    return SessionModel(
        OmnigentDriver(
            run_dir=sim_dir,
            artifact_name="__none__",  # no artifact expected; name never matches, artifact_exists stays False
            model=SIM_MODEL,
            skills="none",
            session_title=_title(sim_dir, f"sim: {flow['name']}"),
            project=_project(sim_dir, scenario),
        )
    )


async def run_judge_omni(
    judge_md: str,
    entries: list[tuple[str, str, str]],
    judge_dir: Path,
    *,
    scenario: str,
) -> str:
    # One-shot omnigent session: judge prompt + all plans in, prose verdict out.
    model = SessionModel(
        OmnigentDriver(
            run_dir=judge_dir,
            artifact_name="__none__",  # no artifact expected; name never matches, artifact_exists stays False
            model=JUDGE_MODEL,
            skills="none",
            turn_timeout_s=600,  # one long grading turn over all full plans
            session_title=_title(judge_dir, "judge"),
            project=_project(judge_dir, scenario),
        )
    )
    try:
        out = await model.generate(build_judge_prompt(judge_md, entries))
        return out.completion
    finally:
        await model.close()


def omni_factories(scenario: str, *, artifact_name: str | None = "plan.md", git_init: bool = False):
    """The three real omnigent factories, bound to `scenario`, matching the
    2-arg `(flow, dir)` / 3-arg `(judge_md, entries, judge_dir)` contract
    run_case/run_case_n call. `artifact_name`/`git_init` are case properties
    (todo_app writes into a git-initialized flow_dir); defaults keep
    swe_planning byte-identical. `artifact_name=None` means the case declares
    no artifact — mapped to the driver's `"__none__"` sentinel."""

    return (
        functools.partial(
            make_flow_driver_omni,
            scenario=scenario,
            artifact_name="__none__" if artifact_name is None else artifact_name,
            git_init=git_init,
        ),
        functools.partial(make_simulator_omni, scenario=scenario),
        functools.partial(run_judge_omni, scenario=scenario),
    )
