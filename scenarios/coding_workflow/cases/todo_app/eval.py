"""Inspect Task: drive subscription claude through the full superpowers workflow
to build a CLI todo app, then score objectively + with a judge. All subscription.

    RUN_LIVE_AGENT=1 TODO_RUN_ID=first \\
      uv run inspect eval scenarios/coding_workflow/cases/todo_app/eval.py \\
        --model claudesub/sonnet \\
        --model-role user=claudesub/sonnet --model-role grader=claudesub/sonnet
"""

from __future__ import annotations

import os
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from flowbench.runner import subscription_model as _sub  # noqa: F401  (registers claudesub)
from flowbench.runner.run_dir import prepare_run_dir
from scenarios.coding_workflow.cases.todo_app import task as toy
from scenarios.coding_workflow.cases.todo_app.flows import FLOWS
from scenarios.coding_workflow.cases.todo_app.scorers import build_judge, workflow_scorer
from scenarios.coding_workflow.cases.todo_app.solver import todo_build_solver


def default_run_base() -> Path:
    """Sibling `../flowbench-runs/todo-app-eval`, anchored off THIS FILE — not cwd.
    Inspect chdir's into the eval file's directory before the task constructs, so a
    cwd-relative default would land run-dirs inside the repo.
    __file__ is <repo>/scenarios/coding_workflow/cases/todo_app/eval.py → parents[4] is the repo root."""
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root.parent / "flowbench-runs" / "todo-app-eval"


# NOTE: decorator MUST be the bare name `task` — Inspect discovers tasks by AST
# scanning for a decorator literally named `task` (inspect_ai._util.decorator),
# so aliasing it (`task as inspect_task`) makes `inspect eval <file>` silently find
# nothing. Do not rename this import.
@task
def todo_app_eval() -> Task:
    # Must be absolute: the omnigent host rejects a relative workspace path.
    base = Path(os.environ.get("TODO_RUN_BASE", default_run_base())).resolve()
    run_id = os.environ.get("TODO_RUN_ID", "manual")
    # One Sample per flow — Inspect iterates samples, so N flows run from a single
    # `inspect eval` invocation. Each flow gets its own run-dir <run_id>/<flow>/ so
    # `flowbench compare` can read <run_id>/*/scorecard.json side by side.
    samples = []
    for flow in FLOWS:
        rd = prepare_run_dir(base, f"{run_id}/{flow.name}", toy.CASE_DIR)
        samples.append(
            Sample(
                input=toy.FIRST_PROMPT,
                metadata={
                    "case": "todo-app",
                    "profile": "cooperative_faithful",
                    "flow": flow.name,
                    "workspace": str(rd.workspace),
                },
            )
        )
    return Task(
        dataset=samples,
        solver=todo_build_solver(),
        scorer=[workflow_scorer(), build_judge()],
        message_limit=400,
    )
