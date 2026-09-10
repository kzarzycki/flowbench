APPROVE

Re-review of attempt 2, scoped to objections 1–3 from review 1 plus a regression
check on the rest of the spec/plan/decisions.

1. **AC1 traceability — resolved.** AC1 now states the source-text assertion and
   names why it exists (the rejected regex would satisfy AC3/AC4 while violating
   AC1). Plan T2 adds `test_acceptance_has_no_error_string_gate` with the exact
   assertion, and T2 correctly notes it must fail on current code alongside the
   console-only test. Full mapping now closes: AC1→T2/T3, AC2→T1 (consumed by
   AC3's test), AC3→T2, AC4→T2, AC5→T4, AC6→T4.

2. **Fabricated quote — resolved.** decisions.md now attributes the choice to
   the issue's first listed option, "decide by probe returncode", and labels the
   generalization to an import-system query as an inference, not a quote. That
   matches the issue text.

3. **"Without running the app" — resolved.** The Problem section says "executes
   the app's entry point", the Fix says "without executing the app's entry
   point", and the parenthetical states explicitly that `find_spec("todo.__main__")`
   imports `todo/__init__.py`, that package import side effects still run, and
   that an `__init__.py` which raises routes to the console shim. Accurate.

Non-blocking note from review 1 also addressed: the plan states T2+T3 land as one
commit, so no committed red state.

No regressions. The verified facts from review 1 still hold and nothing they
depend on changed: `resolve_app_dir` returns the workspace root for a
`todoapp`-only fixture; `_console_entry` resolves the root `pyproject.toml` to
`('todoapp.cli', 'main')`; the probe's runnable/not verdict matches real
`python -m todo` on all five shapes (`todo.py`, package with `__main__.py`,
package without, no `todo`, namespace package); `resolve_invoker` on the
console-only shape still returns `-m todo` today, so AC3's test genuinely fails
on unfixed code. Scope, size (S), and the fixture's compatibility with
`_is_marked` and the id-based `done 1` / `rm 2` checks are unchanged.

Two cosmetic observations, neither worth another round: the rejected-alternative
line still reads "still runs the app" (accurate for the regex alternative, which
does execute the entry point), and T2's new test will need
`from scenarios.coding_workflow.cases.todo_app import acceptance` added to the
test module's imports.
