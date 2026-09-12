"""Orchestrator: the simulator, each flow, and the judge all run as omnigent
sessions via flowbench's OmnigentDriver — never `claude -p`.

What is benchmarked is a `Case` (`flowbench.case`): it says what proves delivery,
how long a flow may run, what happens before and after one, and how it is graded.
Outputs land in <runs_root>/<case.name>/<run_id>/ (per-flow subfolders), never
inside the repo. Offline tests inject fakes for the three factories."""

from __future__ import annotations

import functools
import json
import shutil
import string
from pathlib import Path

from flowbench.case import check_gradable, seed_workspace
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
from flowbench.schema import SCHEMA_VERSION, RunKind, flow_outcome, validate_run_meta
from flowbench.transcript import render_transcript

NO_DELIVERABLE = "(no deliverable declared)"


def MISSING_DELIVERABLE(name: str) -> str:
    """What the judge is shown in place of a deliverable the flow never produced."""
    return f"(this flow produced no {name} — treat it as a failed run)"


def _judge_view(case, flow_dir: Path, session: dict) -> str:
    """What the judge reads for one flow. A file deliverable is its text; a
    directory has no text, so it is its sorted file listing; a declared
    deliverable the flow never produced is the missing marker; a case that
    declares none says so, and its flows are compared on the conversations alone.

    Listed paths are relative to the FLOW DIR, not to the directory itself, so a
    directory the agent left nested reads as `work/port/a.sql` — where the file
    actually is — rather than a bare `a.sql` that could be anywhere.

    Presence is the session's `artifact_exists`, never the truthiness of
    `artifact_text`: an empty file and a directory both have no text."""
    if case.deliverable is None:
        return NO_DELIVERABLE
    if not session.get("artifact_exists"):
        return MISSING_DELIVERABLE(case.deliverable)
    text = session.get("artifact_text")
    if text is not None:
        return text
    root = Path(session["artifact_path"])
    files = sorted(p.relative_to(flow_dir).as_posix() for p in root.rglob("*") if p.is_file())
    return "\n".join([f"({case.deliverable}/ — {len(files)} files)", *files])


def _capture_deliverable(case, flow_dir: Path, session: dict) -> str | None:
    """Put a found deliverable FILE where every reader looks — the declared path
    at the flow-dir root, parents created, so a declared `out/result.txt` lands
    even when the agent wrote it under a subagent's cwd. A directory is left where
    it is (a ported project can be large; copying it would double the run dir).

    Answers where the deliverable was found, relative to the flow dir, which is
    how a reader reaches one that is nested — or None when there is none."""
    found = session.get("artifact_path")
    if not session.get("artifact_exists") or found is None:
        return None
    found = Path(found)
    canonical = flow_dir / case.deliverable
    if found.is_file() and found != canonical:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(found, canonical)
    return found.relative_to(flow_dir).as_posix()


async def run_case(
    case,
    *,
    run_id: str,
    make_flow_driver,
    make_simulator,
    run_judge,
    runs_root=None,
    artifact_grace_s: float = 60.0,
    rotation: int = 0,
) -> dict:
    """Run every flow of `case` — setup, session, deliverable capture, score,
    teardown — then judge them against each other when the case carries a
    `judge.md`. Omnigent-specific spawning is injected via the three factories so
    the whole pipeline runs offline with fakes. `rotation` rotates the flow list
    left by rotation % N so multi-trial runs cancel judge position bias.

    The run dir is `<runs_root>/<case.name>/<run_id>`, `runs_root` falling back to
    the case's settings. Budgets (`max_turns`, `deadline_s`) and what proves
    delivery (`case.deliverable`) are the case's; a case that declares no
    deliverable (a build-shaped one like todo_app, judged black-box) gets no
    probe, no grace-poll and no `artifact_missing`/`artifact_lines` in `run.json`.

    Each flow dir is materialized from `case.workspace` before `case.setup` runs
    — the seed tree and, if declared, the repo holding it. `run.json` records the
    declaration under `workspace` and each flow dir's seed commit under
    `flow_stats[<flow>].seed_commit`.

    `case.score(flow, flow_dir, session)` runs after each flow's session and its
    result is written to `<flow_dir>/scorecard.json`; `None` writes no scorecard,
    and a raised exception is recorded as `{"error": ...}` for that flow instead
    of aborting the run. `case.teardown` runs even when a stage raises."""
    check_gradable(case)  # before any factory: never spend a session on an ungradable run
    task_text = (case.case_dir / "task.md").read_text()
    sim_system = (
        (case.case_dir / "simulator.md").read_text()
        + "\n\n--- WHAT YOU KNOW ---\n\n"
        + (case.case_dir / "knowledge.md").read_text()
    )
    has_judge = case.judge_path.exists()
    judge_md = case.judge_path.read_text() if has_judge else None
    has_deliverable = case.deliverable is not None
    flows = load_flows(case.case_dir / "flows.yaml")
    r = rotation % len(flows)
    flows = flows[r:] + flows[:r]

    # Resolved once, here: every dir below this root is handed to omnigent as a
    # session workspace, and the server rejects one that is not absolute (#155).
    root = Path(runs_root if runs_root is not None else case.settings.runs_root).resolve()
    run_root = root / case.name / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    workspace_declared: dict | None = None
    views: dict[str, str] = {}
    delivered: dict[str, bool] = {}
    transcripts: dict[str, str] = {}
    flow_stats: dict[str, dict] = {}
    for flow in flows:
        name = flow["name"]
        flow_dir = run_root / name
        flow_dir.mkdir(parents=True, exist_ok=True)
        sim_dir = run_root / f"_sim_{name}"
        sim_dir.mkdir(parents=True, exist_ok=True)
        try:
            # The declared workspace, before anything else touches the flow dir:
            # a case that overrides `setup` must not be able to lose it.
            seeded = seed_workspace(case.workspace, case.case_dir, flow_dir)
            seed_commit = seeded.pop("seed_commit")
            # What is left of the record is the declaration, identical for every
            # flow by construction; the commit is the one part that is a fact
            # about THIS flow dir, so it is recorded per flow.
            workspace_declared = seeded
            await case.setup(flow, flow_dir)
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
                    max_turns=case.max_turns,
                    deadline_s=case.deadline_s,
                    artifact_grace_s=artifact_grace_s,
                    artifact_probe=(
                        functools.partial(case.find_deliverable, flow_dir)
                        if has_deliverable
                        else None
                    ),
                )
            finally:
                close = getattr(simulator, "close", None)
                if close is not None:
                    await close()

            deliverable_path = _capture_deliverable(case, flow_dir, session)
            transcript_text = render_transcript(session.get("items") or [])
            (flow_dir / "transcript.md").write_text(transcript_text)
            (flow_dir / "session.json").write_text(json.dumps(session, indent=2, default=str))
            views[name] = _judge_view(case, flow_dir, session)
            delivered[name] = bool(session.get("artifact_exists"))
            transcripts[name] = transcript_text
            # A present deliverable with no text is a directory (the same
            # invariant `_judge_view` reads): `artifact_lines` is a file measure,
            # so a directory carries no such key rather than a misleading 0.
            text = session.get("artifact_text")
            is_directory = bool(session.get("artifact_exists")) and text is None
            deliverable_stats: dict = {}
            if has_deliverable:
                if not is_directory:
                    deliverable_stats["artifact_lines"] = len((text or "").splitlines())
                deliverable_stats["deliverable_path"] = deliverable_path
            flow_stats[name] = {
                "seed_commit": seed_commit,
                "exit_status": session.get("exit_status"),
                "turns": session.get("turns"),
                "duration_s": session.get("duration_s"),
                **deliverable_stats,
                "context_tokens": session.get("context_tokens"),
            }
            try:
                card = await case.score(flow, flow_dir, session)
            except Exception as e:  # noqa: BLE001 - isolate one flow's scorer, never abort the run
                error = f"{type(e).__name__}: {e}"
                card = {"error": error}
                flow_stats[name]["score_error"] = error
            flow_stats[name]["outcome"] = flow_outcome(
                session=session,
                has_deliverable=has_deliverable,
                score_error=flow_stats[name].get("score_error"),
                card=card,
            )
            if card is not None:
                # The envelope key first, and only when the card does not declare
                # its own — a case that versions its scorecard keeps that version.
                if "schema_version" not in card:
                    card = {"schema_version": SCHEMA_VERSION, **card}
                (flow_dir / "scorecard.json").write_text(json.dumps(card, indent=2, default=str))
        finally:
            await case.teardown(flow, flow_dir)

    # Rotated flow order defines this trial's judge-facing labels A, B, C…
    names = [f["name"] for f in flows]
    letters = string.ascii_uppercase[: len(flows)]
    labels = dict(zip(letters, names, strict=True))  # {"A": name, "B": name, ...}
    if has_judge:
        entries = [
            (letter, transcripts[name], views[name])
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
        "schema_version": SCHEMA_VERSION,
        "kind": RunKind.TRIAL,
        "run_id": run_id,
        "case": case.name,
        "deliverable": case.deliverable,
        # The declaration only — the case's, so one value for the run. Each flow
        # dir's actual seed commit is `flow_stats[<flow>].seed_commit`: a flow dir
        # that already held a repo keeps that repo's HEAD, so a single run-level
        # SHA could be a lie about some other flow.
        "workspace": workspace_declared,
        "flows": names,
        "labels": labels,  # {"A": flow_name, ...} — judge-facing, this trial only
        "rotation": rotation,
        "winner": verdict["winner"],  # judge letter, or tie/unknown
        "winner_flow": winner_flow,  # flow NAME (order-independent), or tie/unknown
        "scores": verdict.get("scores"),
        **(
            {"artifact_missing": [n for n, ok in delivered.items() if not ok]}
            if has_deliverable
            else {}
        ),
        "flow_stats": flow_stats,
        # Built from flow_stats, so the two maps cannot disagree. A flow that
        # raised before flow_stats[name] was set (case.setup blew up) is absent
        # from both.
        "outcomes": {n: s["outcome"] for n, s in flow_stats.items()},
        "models": {f["name"]: f.get("model") for f in flows},
        "reasoning_effort": {f["name"]: f.get("reasoning_effort") for f in flows},
    }
    # Not caught: it raises only on a manifest this engine built wrong.
    validate_run_meta(meta)
    (run_root / "run.json").write_text(json.dumps(meta, indent=2, default=str))
    if has_judge:
        render_report(run_root)  # pure reader over the files just written
    return {"run_root": str(run_root), "verdict": verdict, "meta": meta}


async def run_case_n(
    case,
    *,
    run_id: str,
    n: int,
    make_flow_driver,
    make_simulator,
    run_judge,
    runs_root=None,
    artifact_grace_s: float = 60.0,
) -> dict:
    """Run run_case n times (sequentially; a failing trial propagates) and
    aggregate the categorical verdicts. Uniform return shape for every n:
    {"run_root", "trials", "aggregate"}. n=1 delegates and keeps today's
    flat layout; n>1 writes trial-XX/ subdirs plus an aggregate run.json.
    A case without judge.md never produces a winner_flow — the aggregate is
    then {"counts": {}, "winner": None} rather than tallying None as a flow."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    names = check_gradable(case)  # the same load errors, before any factory
    kwargs = {
        "make_flow_driver": make_flow_driver,
        "make_simulator": make_simulator,
        "run_judge": run_judge,
        "runs_root": runs_root,
        "artifact_grace_s": artifact_grace_s,
    }

    if n == 1:
        result = await run_case(case, run_id=run_id, **kwargs)
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
            case, run_id=f"{run_id}/trial-{k:02d}", rotation=(k - 1) % len(names), **kwargs
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
    root = Path(runs_root if runs_root is not None else case.settings.runs_root).resolve()
    run_root = root / case.name / run_id
    aggregate_meta = {
        "run_id": run_id,
        "case": case.name,
        "deliverable": case.deliverable,
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


async def rescore_run(case, run_root) -> dict[str, str]:
    """Re-run the case's `score` over an existing run dir, without starting a
    session: rewrites `<flow>/scorecard.json` and `flow_stats[flow].score_error`
    from what is already on disk (`<flow>/session.json` + the case's current
    flows.yaml), and deletes a scorecard whose fresh score is `None`. Never
    touches transcripts or session.json, and builds no factory.

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
    # A scorer may start a grader session off `flow_dir` (todo_app does), and that
    # workspace has to be absolute — same rule as `run_case`'s root (#155).
    run_root = Path(run_root).resolve()
    flows_by_name = {f["name"]: f for f in load_flows(case.case_dir / "flows.yaml")}

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
                card = await case.score(flow, flow_dir, session)
            except Exception as e:  # noqa: BLE001 - isolate one flow's scorer, never abort the rescore
                error = f"{type(e).__name__}: {e}"
                card = {"error": error}
                stats["score_error"] = error
                results[key] = error
            else:
                stats.pop("score_error", None)
                results[key] = "ok"
            card_path = flow_dir / "scorecard.json"
            if card is None:
                # Nothing grades this flow any more: a card left behind would be
                # read as a fresh verdict by `compare`.
                card_path.unlink(missing_ok=True)
            else:
                card_path.write_text(json.dumps(card, indent=2, default=str))
            changed = True

        if changed:
            run_json_path.write_text(json.dumps(meta, indent=2, default=str))

    return results


# --- the real omnigent factories -------------------------------------------


def _run_parts(run_dir: Path) -> tuple[str, str, str | None]:
    """`(case, run_id, trial | None)` read off a role dir's own path. Every role
    of a run — a flow, its simulator, the judge, a per-flow grader — is a direct
    child of the run dir, which `run_case` lays out as
    `<runs_root>/<case>/<run_id>[/trial-XX]`. So the labels a session carries are
    the run's own layout, never something a caller has to pass in and keep
    consistent with it."""
    run_root = Path(run_dir).parent
    trial = run_root.name if run_root.name.startswith("trial-") else None
    if trial is not None:
        run_root = run_root.parent
    return run_root.parent.name, run_root.name, trial


def _title(run_dir: Path, base: str) -> str:
    # The case, because one omnigent server runs sessions from many of them; and
    # n>1 nests roles under trial-XX, so the trial too — the web UI's "sim: plain"
    # chats are otherwise not tellable apart across trials.
    case, _run_id, trial = _run_parts(run_dir)
    return " · ".join(p for p in (case, trial, base) if p is not None)


def _project(run_dir: Path) -> str:
    # "<case>/<run_id>": groups all of a run's sessions into one web-UI project
    # folder (the omni_project label). Trials group by the RUN, not the trial, so
    # one benchmark run is one folder.
    case, run_id, _trial = _run_parts(run_dir)
    return f"{case}/{run_id}"


def make_flow_driver_omni(flow: dict, flow_dir: Path) -> OmnigentDriver:
    return OmnigentDriver(
        run_dir=flow_dir,
        session_title=_title(flow_dir, f"flow: {flow['name']}"),
        project=_project(flow_dir),
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


def make_simulator_omni(flow: dict, sim_dir: Path, *, model: str) -> SessionModel:
    # Bare Claude Code (skills: none): the simulator only answers questions.
    return SessionModel(
        OmnigentDriver(
            run_dir=sim_dir,
            model=model,
            skills="none",
            session_title=_title(sim_dir, f"sim: {flow['name']}"),
            project=_project(sim_dir),
        )
    )


async def run_judge_omni(
    judge_md: str,
    entries: list[tuple[str, str, str]],
    judge_dir: Path,
    *,
    model: str,
) -> str:
    # One-shot omnigent session: judge prompt + all plans in, prose verdict out.
    judge = SessionModel(
        OmnigentDriver(
            run_dir=judge_dir,
            model=model,
            skills="none",
            turn_timeout_s=600,  # one long grading turn over all full plans
            session_title=_title(judge_dir, "judge"),
            project=_project(judge_dir),
        )
    )
    try:
        out = await judge.generate(build_judge_prompt(judge_md, entries))
        return out.completion
    finally:
        await judge.close()


def omni_factories(case):
    """The three real omnigent factories for `case`, matching the 2-arg
    `(flow, dir)` / 3-arg `(judge_md, entries, judge_dir)` contract
    run_case/run_case_n call. Only the models are the case's to choose
    (`settings.sim_model`, `settings.judge_model`; a flow names its own): the
    session labels come off the run layout, a case that needs a git repo in the
    flow dir makes one in its own `setup`, and which file proves delivery is
    `Case.deliverable`/`find_deliverable` — never the driver's."""

    return (
        make_flow_driver_omni,
        functools.partial(make_simulator_omni, model=case.settings.sim_model),
        functools.partial(run_judge_omni, model=case.settings.judge_model),
    )
