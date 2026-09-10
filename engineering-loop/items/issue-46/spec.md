# issue-46 — resolve_invoker must not gate on one CPython error string

**Size:** S (one function + one fixture + tests).

## Problem
`resolve_invoker` (`scenarios/coding_workflow/cases/todo_app/acceptance.py:99`)
runs `python -m todo` and falls back to the declared console-script entry point
only when stderr contains the exact string `"No module named todo.__main__"`.

- A console-script-only app with no `todo` package at all (package named
  `todoapp`, entry `todo = todoapp.cli:main`) produces `"No module named todo"` —
  the fallback never fires, every acceptance check runs a broken
  `python -m todo`, and a faithful build scores **0.0** on acceptance.
- The gate is also tied to CPython's wording, which is not a stable contract.
- Side effect: the probe *executes the app's entry point* with no argv, so a
  build that writes state on startup is probed with a real run before
  acceptance's deterministic reset.

Existing coverage (`test_accepts_console_script_invocation`) only exercises the
case where a `todo` package exists without `__main__.py`, which is why the bug
survived.

## Fix
Replace the string gate with a probe of the **actual condition** — "does
`python -m todo` resolve here?" — asked of the import system instead of parsed
out of an error message, and without executing the app's entry point:

```
python -c "<resolve check>"      # cwd = app_dir
```
where the check reports runnable iff `importlib.util.find_spec("todo")` exists
and, when that spec is a package (`submodule_search_locations is not None`),
`find_spec("todo.__main__")` also exists. Any exception ⇒ not runnable.
(For a package, `find_spec("todo.__main__")` imports `todo/__init__.py` — the
package's import side effects still run; only `__main__.py` is not executed, and
an `__init__.py` that raises routes to the console shim.)
`resolve_invoker` returns `[python, -m, todo]` when runnable; otherwise the
console-script shim when `_console_entry()` finds one; otherwise, unchanged,
`[python, -m, todo]` (so the failure surfaces as failed checks, not a crash).

Rejected alternative: a regex over `No module named todo(\.__main__)?`. Cheaper,
but still reads CPython's prose and still runs the app.
Rejected alternative: prefer the console entry unconditionally when declared —
it would switch every superpowers build (which typically ships BOTH a
`[project.scripts]` entry and a working `__main__.py`) onto the shim path,
changing what acceptance measures today.

## Acceptance criteria (machine-checkable)
1. `acceptance.py` contains no match for `No module named` — asserted by a test
   over the module's own source, so the rejected regex alternative cannot slip
   back in (it would satisfy AC3 and AC4 while violating this).
2. New fixture `fixtures/console_only_app/`: package `todoapp` (no `todo`
   module anywhere), `pyproject.toml` with `[project.scripts] todo =
   "todoapp.cli:main"`, file-backed store — a faithful todo app.
3. New test: `run_acceptance(<copy of console_only_app>)` gives
   `app_runs is True` and `score == 1.0`. This test fails on master.
4. `resolve_invoker` returns `[sys.executable, "-m", "todo"]` for the existing
   `good_app` fixture (package with `__main__.py`) — asserted by a unit test, so
   the `-m` path is not silently swapped for the shim.
5. Existing todo_app acceptance tests still pass unchanged.
6. Full offline suite green; ruff clean.
