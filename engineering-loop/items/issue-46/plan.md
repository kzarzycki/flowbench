# issue-46 — plan

Constraint (verbatim from spec): probe the actual condition — "does
`python -m todo` resolve here?" — asked of the import system, without executing
the app's entry point; no `No module named` string anywhere in `acceptance.py`.

T2 and T3 land as ONE commit (T2 is the red step of a red-green pair, not a
committable state).

## T1 — fixture (no behaviour change yet)
`scenarios/coding_workflow/cases/todo_app/fixtures/console_only_app/`:
- `todoapp/__init__.py` (empty), `todoapp/cli.py` with `main()` implementing
  add/list/done/rm over a `tasks.json` in cwd, modelled on
  `fixtures/good_app/todo/__main__.py` (same output shape: `[✓] <id> (<prio>)
  <text>`), `main()` reads `sys.argv[1:]`.
- `pyproject.toml`: `[project] name="todoapp" version="0.1.0"` +
  `[project.scripts] todo = "todoapp.cli:main"`.
- No `todo` package, no `todo.py`, anywhere in the fixture.
Covers AC2.

## T2 — failing tests (red)
`tests/scenarios/todo_app/test_acceptance.py`:
- `test_console_only_app_passes_all_checks`: copytree the fixture, assert
  `app_runs is True` and `score == 1.0`. (AC3)
- `test_resolve_invoker_prefers_dash_m_for_package_app`: `resolve_invoker(<copy
  of good_app>) == [sys.executable, "-m", "todo"]`. (AC4)
- `test_acceptance_has_no_error_string_gate`:
  `assert "No module named" not in Path(acceptance.__file__).read_text()`. (AC1)
Run them; the first and third must fail on current code. Report the failure.

## T3 — fix (green)
`acceptance.py`: add a module-level probe source constant and rewrite
`resolve_invoker`'s gate to run it with `cwd=app_dir`, `timeout=30.0`, deciding
on the probe's returncode. Delete the `"No module named todo.__main__"` check
and the entry-point-executing probe. Docstring updated to say what is probed.
Covers AC1.

## T4 — gates
`uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` in the
worktree; all clean, no existing test modified (AC5/AC6).
