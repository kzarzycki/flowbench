"""The Inspect CLI discovers tasks by AST-scanning for a decorator literally named
`task` (inspect_ai._util.decorator.parse_decorators). Aliasing the import
(`task as inspect_task`) makes `inspect eval <file>` silently find NO tasks — a
regression the live run caught. This guards against re-aliasing."""

from pathlib import Path

from inspect_ai._util.decorator import parse_decorators

EVAL_FILE = Path(__file__).resolve().parents[3] / "scenarios/coding_workflow/cases/todo_app/eval.py"


def test_eval_task_is_discoverable_by_inspect_cli():
    found = parse_decorators(EVAL_FILE, "task")
    names = [name for name, _ in found]
    assert "todo_app_eval" in names, (
        f"`inspect eval {EVAL_FILE.name}` would find no task — the @task decorator "
        f"must be the bare name `task`, not an alias. Found: {names}"
    )


# test_default_run_base_anchors_outside_the_repo removed in S01.3/T4: importing
# eval.py now fails (scorers.py dropped build_judge/workflow_scorer, the Inspect
# scorers eval.py wired in). eval.py itself is deleted wholesale in T5; this
# whole file goes with it. The AST-only test above still passes untouched.
