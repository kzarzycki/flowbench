REVISE

Verified against the code (probe run on all five shapes; `resolve_app_dir` /
`_console_entry` / `resolve_invoker` called on a `todoapp`-only fixture):

- `resolve_app_dir` does return the workspace root for a fixture with no `todo`
  module — confirmed.
- `_console_entry` does find the root `pyproject.toml` and returns
  `('todoapp.cli', 'main')` — confirmed.
- The proposed import-system probe classifies all four shapes correctly, and
  also the fifth (namespace package: `todo/__main__.py`, no `__init__.py`):
  probe exit code matched real `python -m todo` exit status in every case
  (`todo.py` → runnable, pkg + `__main__` → runnable, pkg w/o `__main__` → not,
  no todo → not, namespace pkg → runnable).
- The bug reproduces: `resolve_invoker` on the console-only shape returns
  `['…python3','-m','todo']` today, so AC3's new test genuinely fails on
  unfixed code. Test strategy (g) holds.
- Fixture output format (T1, `[✓] <id> (<prio>) <text>`) is compatible with
  `_is_marked` and the `rm 2` / `done 1` id-based checks — score 1.0 is
  achievable.
- Scope (a) and proportionality (h) are fine: exactly the issue's three asks
  (gate fix, `fixtures/console_only_app`, test), no invention. Decisions 2 and 3
  in decisions.md are verified-true inferences.

## Objections

1. **AC1 has no test — traceability gap (blocking).** AC1 ("`acceptance.py`
   contains no match for `No module named`") maps to T3 but to no test in T2 or
   anywhere else. It is exactly the criterion that separates the chosen fix from
   the rejected regex alternative (`No module named todo(\.__main__)?` would
   satisfy AC3 and AC4 while violating AC1), so nothing in the suite pins the
   decision. Fix: add to T2 a one-line source assertion, e.g. in
   `tests/scenarios/todo_app/test_acceptance.py`,
   `assert "No module named" not in Path(acceptance.__file__).read_text()`, and
   cite it under AC1.

2. **decisions.md attributes a quote to the issue that the issue does not
   contain.** It says: *Source: the issue's own words "check for the actual
   condition, not the string"*. Issue 46's text says only `Fix: decide by probe
   returncode / a regex over ... or probe the console entry first when
   _console_entry() finds one`. The reasoning is sound, but the citation is
   fabricated; restate it as an inference ("the issue's first option, `decide by
   probe returncode`, generalized to an import-system query") rather than a
   quotation.

3. **The spec's "without running the app" is overstated for the package case.**
   `importlib.util.find_spec("todo.__main__")` imports the parent package, so
   `todo/__init__.py` *is* executed by the probe; only `__main__.py` is not. A
   build whose `__init__.py` writes state is still touched (harmlessly —
   `run_acceptance` unlinks `tasks.json` after `resolve_invoker`), and an
   `__init__.py` that raises now routes to the console shim instead of `-m`.
   Reword the Problem/Fix claim to "without executing the app's entry point" and
   state the `__init__.py` import explicitly, so the next reader does not rely on
   a guarantee the fix does not give.

Non-blocking note (no change required): T2 deliberately leaves the branch red,
which is the standard red-green step but formally breaks "tests green after each
task" — land T2 and T3 as one commit, or mark T2 as a non-commit step in the
plan.

Everything else in (b), (d), (e), (f), (g), (h) checks out; addressing 1–3
clears the review.
