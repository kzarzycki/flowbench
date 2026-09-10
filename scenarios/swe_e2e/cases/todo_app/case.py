"""todo_app's runtime shape: a build-shaped case. The deliverable is the running
app itself — judged black-box by `acceptance.py`, so no file proves delivery — and
each flow is scored on its own (there is no comparative `judge.md`).

`score_todo_app` is the case's whole grading body: black-box acceptance +
skills/phase detection + clarifying coverage + a low-confidence judge. `run_case`
reaches it through `TodoAppCase.score` and writes what it returns to
`<flow_dir>/scorecard.json`."""

from __future__ import annotations

import json
from pathlib import Path

from flowbench.case import Case
from flowbench.driver import OmnigentDriver, git_init_repo
from flowbench.model import SessionModel
from flowbench.run import _project, _title
from scenarios.swe_e2e.cases.todo_app import scorers as sc
from scenarios.swe_e2e.cases.todo_app.acceptance import run_acceptance

CASE_DIR = Path(__file__).parent


async def score_todo_app(flow: dict, flow_dir: Path, session: dict, *, make_grader) -> dict:
    flow_dir = Path(flow_dir)
    grader_model = make_grader(flow_dir)
    try:
        acc = run_acceptance(flow_dir)
        skills = sc.skills_report(session)
        phases = sc.detect_phases(
            flow_dir, session, app_runs=acc.app_runs, skills=skills["invoked"]
        )
        clarifying = sc.clarifying_coverage(session, sc.UNDERSPECIFIED_TOPICS)
        acc_d = {
            "score": acc.score,
            "passed": acc.passed,
            "total": acc.total,
            "app_runs": acc.app_runs,
            "checks": [c.__dict__ for c in acc.checks],
        }
        verdict, judge_reason = await sc.judge_build(
            shape=(CASE_DIR / "knowledge.md").read_text(),
            code=sc.collect_code(flow_dir),
            acceptance=acc_d,
            transcript=sc.transcript_for_judge(session),
            grader_model=grader_model,
        )
    finally:
        close = getattr(grader_model, "close", None)
        if close is not None:
            await close()

    (flow_dir / "acceptance.json").write_text(json.dumps(acc_d, indent=2, default=str))

    return {
        "flow": {
            "name": flow["name"],
            "harness": flow.get("harness"),
            "skills": flow.get("skills"),
            "skill_dirs": [str(p) for p in flow.get("skill_dirs", [])],
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


def make_grader_omni(flow_dir: Path, *, model: str) -> SessionModel:
    flow_dir = Path(flow_dir)
    judge_dir = flow_dir.parent / f"_judge_{flow_dir.name}"
    judge_dir.mkdir(parents=True, exist_ok=True)
    return SessionModel(
        OmnigentDriver(
            run_dir=judge_dir,
            model=model,
            skills="none",
            turn_timeout_s=600,  # one long grading turn over the produced code
            session_title=_title(judge_dir, f"judge: {flow_dir.name}"),
            project=_project(judge_dir),
        )
    )


class TodoAppCase(Case):
    """The build takes ~an hour of wall clock; the grader is a class attribute so
    an offline test can hand `score` a canned model instead of an omnigent one."""

    deliverable = None
    deadline_s = 3600.0
    grader_factory = staticmethod(make_grader_omni)

    async def setup(self, flow, flow_dir) -> None:
        """The workflow flows branch and commit, so the flow dir starts as a repo
        with something in it."""
        flow_dir = Path(flow_dir)
        if not (flow_dir / ".git").exists():
            git_init_repo(flow_dir)

    async def score(self, flow, flow_dir, session) -> dict:
        # Through the class, never `self.`: a test patching the attribute with a
        # plain function would otherwise have `self` passed to it as flow_dir.
        grader_factory = type(self).grader_factory
        return await score_todo_app(
            flow,
            flow_dir,
            session,
            make_grader=lambda d: grader_factory(d, model=self.settings.judge_model),
        )
