"""todo_app's runtime shape: a build-shaped case. The deliverable is the running
app itself — judged black-box by `acceptance.py`, so no file proves delivery — and
each flow is scored on its own (there is no comparative `judge.md`)."""

from __future__ import annotations

from pathlib import Path

from flowbench.case import Case
from flowbench.driver import git_init_repo
from scenarios.coding_workflow.cases.todo_app.scoring import make_grader_omni, score_todo_app

SCENARIO = "coding_workflow"


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
            make_grader=lambda d: grader_factory(d, scenario=SCENARIO),
        )
