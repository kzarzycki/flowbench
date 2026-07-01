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


def test_default_run_base_anchors_outside_the_repo(monkeypatch):
    # Inspect chdir's into the eval file's directory before the task constructs, so
    # a cwd-relative default base lands run-dirs INSIDE the repo. The default must
    # anchor off __file__ to the sibling ../flowbench-runs/, regardless of cwd.
    from scenarios.coding_workflow.cases.todo_app.eval import default_run_base

    repo_root = EVAL_FILE.parents[4]
    monkeypatch.chdir(EVAL_FILE.parent)  # mimic Inspect's chdir
    base = default_run_base()
    assert repo_root not in base.parents and base != repo_root, (
        f"run base {base} must not be inside the repo {repo_root}"
    )
    assert base.name == "todo-app-eval" and base.parent.name == "flowbench-runs"
