"""The todo-app case's Inspect @solver: wires the real driver to the generic
DONE-token loop (flowbench.runner.loop), then computes the case's scores and
persists the run-dir."""

from __future__ import annotations

from inspect_ai.model import get_model
from inspect_ai.solver import Generate, Solver, TaskState, solver

from flowbench.runner.driver import OmnigentDriver
from flowbench.runner.loop import run_agent_session
from scenarios.coding_workflow.cases.todo_app import flows as toy_flows
from scenarios.coding_workflow.cases.todo_app import task as toy


@solver
def todo_build_solver(
    *,
    profile: str = "cooperative_faithful",
    max_turns: int = 80,
    deadline_s: float = 3600.0,
    turn_timeout_s: float = 1800.0,
) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        from pathlib import Path

        from flowbench.runner.run_dir import RunDir, write_outputs, write_run_md
        from scenarios.coding_workflow.cases.todo_app import scorers as sc
        from scenarios.coding_workflow.cases.todo_app.acceptance import run_acceptance

        # The flow (approach under test) + its run-dir come from the Sample metadata
        # eval.py set — so N flows share this one solver, differing only by bundle.
        flow = toy_flows.by_name(state.metadata["flow"])
        run_dir = state.metadata["workspace"]

        driver = OmnigentDriver(
            run_dir=Path(run_dir),
            artifact_name="tasks.json",
            # No agent_prompt / agent_name override: the SUT is vanilla Claude Code.
            # The task is delivered as the first user message (toy.FIRST_PROMPT). The
            # ONLY per-flow variation is the bundle skills/MCPs, never a system prompt.
            harness=flow.harness,
            skills=flow.skills,
            skill_dirs=flow.skill_dirs,
            mcp_files=flow.mcp_files,
            git_init=True,
            # A full superpowers build runs long autonomous stretches (subagents
            # implementing/reviewing); the agent stays `running` for many minutes
            # between idle points. The per-turn cap must exceed any single stretch
            # so we never inject into a still-working agent. Wall-clock deadline
            # caps the whole run.
            turn_timeout_s=turn_timeout_s,
        )
        session = await run_agent_session(
            driver,
            get_model(role="user"),
            first_prompt=toy.FIRST_PROMPT,
            simulator_system=toy.simulator_system(profile),
            done_token=toy.DONE_TOKEN,
            max_turns=max_turns,
            deadline_s=deadline_s,
        )

        # --- score inputs (objective first, then judge) ---
        acc = run_acceptance(Path(run_dir))
        skills = sc.skills_report(session)
        phases = sc.detect_phases(
            Path(run_dir), session, app_runs=acc.app_runs, skills=skills["invoked"]
        )
        clarifying = sc.clarifying_coverage(session, toy.UNDERSPECIFIED_TOPICS)
        acc_d = {
            "score": acc.score,
            "passed": acc.passed,
            "total": acc.total,
            "app_runs": acc.app_runs,
            "checks": [c.__dict__ for c in acc.checks],
        }
        verdict, judge_reason = await sc.judge_build(
            shape=toy.ENVISIONED_SHAPE,
            code=sc.collect_code(Path(run_dir)),
            acceptance=acc_d,
            transcript=sc.transcript_for_judge(session),
            grader_model=get_model(role="grader"),
        )

        state.store.set("session", session)
        state.store.set("workspace", run_dir)
        state.store.set("acceptance", acc_d)
        state.store.set("phases", phases)
        state.store.set("clarifying", clarifying)
        state.store.set("skills", skills)
        state.store.set("judge", verdict)
        state.store.set("judge_error", None if verdict else judge_reason)

        # persist everything into the run-dir (no teardown). Objective vs heuristic
        # are kept separate in the scorecard so neither is read as the other.
        rd = RunDir(
            root=Path(run_dir).parent, workspace=Path(run_dir), case=Path(run_dir).parent / "case"
        )
        scorecard = {
            # which approach produced this card + the exact skill set (paths carry
            # the superpowers version), so a result is traceable to its flow.
            "flow": {
                "name": flow.name,
                "harness": flow.harness,
                "skills": flow.skills,
                "skill_dirs": [str(p) for p in flow.skill_dirs],
            },
            "objective": {
                "app_runs": acc.app_runs,
                "acceptance": acc_d["score"],
                "clarifying_coverage": clarifying["score"],
                "clarifying_asked": clarifying["asked"],
                # objective: did the superpowers workflow actually load?
                "superpowers_used": skills["superpowers_used"],
                "brainstorming_used": skills["brainstorming_used"],
                "skills_invoked": skills["invoked"],
            },
            "heuristic": {"phases": phases},
            # verdict when parsed; a labeled error (e.g. empty_grader_completion) when
            # the judge couldn't be scored — never a silent {}.
            "judge_low_confidence": verdict or {"error": judge_reason},
            # Where to browse / resume the SUT (session left alive after the run).
            "session": {
                "conversation_url": session.get("conversation_url"),
                "session_id": session.get("session_id"),
            },
        }
        write_outputs(
            rd,
            transcript=session,
            acceptance=acc_d,
            judge=verdict or {"error": judge_reason},
            clarifying=clarifying,
            scorecard=scorecard,
        )
        write_run_md(rd, scorecard)
        return state

    return solve
