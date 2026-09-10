APPROVE

# Gate 3 — branch review, `loop/issue-46-invoker-probe` (10e9546)

Diff: 5 files, +103/-4. Engine untouched; only `scenarios/coding_workflow/cases/todo_app/`
and `tests/scenarios/todo_app/test_acceptance.py`.

## Checklist

**(a) Every AC met and covered by a would-fail test — verified.**
Reproduced on a scratch copy of `origin/master` (`git archive origin/master` into
`/private/tmp/claude-501/rev46`, then the branch's fixture + test file copied in):

```
FAILED tests/scenarios/todo_app/test_acceptance.py::test_console_only_app_passes_all_checks
FAILED tests/scenarios/todo_app/test_acceptance.py::test_acceptance_has_no_error_string_gate
2 failed, 6 passed
```

- AC1 → `tests/scenarios/todo_app/test_acceptance.py:116` — fails on master. Also blocks the
  rejected regex alternative, as the spec intended.
- AC2 → `fixtures/console_only_app/` — see (f).
- AC3 → `test_acceptance.py:102` — fails on master (`app_runs=False`, all 7 checks red).
- AC4 → `test_acceptance.py:111` — passes on master too. This is a guard, not a red-green
  test, which is what the spec asks for ("so the `-m` path is not silently swapped for the
  shim"); it does discriminate against the rejected "prefer console entry unconditionally"
  design. Accepted.
- AC5/AC6 → full suite `192 passed, 1 skipped`; `ruff check` clean; `ruff format --check`
  clean (55 files).

**(b) No test weakened.** The only edit to an existing test file is the import line
(`test_acceptance.py:7`) adding `resolve_invoker`, plus `import sys`. All seven pre-existing
tests are byte-identical and still assert the same things. No skips, no xfails, no loosened
assertions.

**(c) No unexplained changes.** The diff is exactly T1–T4 of the plan. No drive-by edits.

**(d) Clean.** `git diff --name-only` shows nothing under `.github/`, `.claude/`, and no
gate or CI definition.

**(e) Probe correctness across shapes — verified empirically**, calling the branch's
`resolve_app_dir` + `resolve_invoker` on nine synthesized app dirs and then actually running
the returned invoker:

| shape | invoker | actually runs |
| --- | --- | --- |
| `todo.py` single module | `-m todo` | yes |
| `todo/` pkg with `__main__.py` | `-m todo` | yes |
| `todo/` pkg, no `__main__.py`, console entry | shim | yes |
| no `todo` at all, console entry | shim | yes |
| nothing at all | `-m todo` | fails → red checks (spec-intended) |
| namespace pkg (`todo/__main__.py`, no `__init__.py`) | `-m todo` | yes |
| `todo/__init__.py` raises + console entry | shim | yes |
| `todo/__init__.py` raises, no console entry | `-m todo` | fails → red checks |
| console entry declared but module raises | shim | fails → red checks |

All correct. `find_spec('todo')` does not import `todo`; `find_spec('todo.__main__')` imports
only the parent, so an `__init__.py` that raises is caught by the `except Exception` and routes
to the shim — as the docstring at `acceptance.py:113-120` states.

`python -c` with `cwd=app_dir`: sys.path[0] is `''` → the cwd, so `app_dir` is on the path.
Confirmed by the single-module and namespace rows above. The one way this is not guaranteed is
`PYTHONSAFEPATH`/`-P` in the inherited env — but that suppresses the cwd for the real
`python -m todo` identically, so the probe stays faithful to what it predicts. No false
positive.

**(f) Fixture is faithful.** `fixtures/console_only_app/todoapp/cli.py` is a line-for-line
analogue of `fixtures/good_app/todo/__main__.py` (same `tasks.json` store, same
`[✓] <id> (<prio>) <text>` output shape, same add/list/done/rm semantics, same usage/unknown
error paths), differing only in reading `sys.argv[1:]` inside `main()` as a console entry must.
Nothing is shaped to make a check pass. `find` over the fixture confirms no `todo` package,
no `todo.py`, no directory named `todo` — the only occurrence of the token is the script *name*
in `[project.scripts]`, which is the point of the fixture.

**(g) Residual brittleness — noted, none blocking.**

1. `acceptance.py:129` `timeout=30.0` with no `try/except TimeoutExpired`: a timeout still
   propagates out of `resolve_invoker`. Strictly better than master, though — master's probe
   *ran the app*, so an app that blocks on stdin hit that 30s wall every time; the new probe
   only touches the import system and returns in milliseconds. Non-issue.
2. `todo/__init__.py` that calls `sys.exit(0)` at import: `SystemExit` is not an `Exception`,
   so it escapes the `try`, the probe exits 0, and `-m todo` is chosen. Pathological, and the
   real `python -m todo` would behave the same way (exit 0, no output), so acceptance still
   scores it red. Not worth code.
3. **Follow-up worth filing (pre-existing, not introduced here):** the console shim at
   `acceptance.py:135-138` discards the entry function's return value — `_entry()`, not
   `raise SystemExit(_entry())` — so every shim invocation exits 0 regardless. Measured on a
   fixture whose `main()` returns 2 and writes nothing: `app_runs=True`, `score=0.429`, with
   `add_first`/`add_rest`/`done_first` all green. `-m` apps get honest exit codes; shim apps get
   a free 3/7 floor. This shipped on master and is out of this spec's scope, but this change is
   what makes the shim path routinely reachable, so the asymmetry now matters. One-line fix.

## Verdict

APPROVE. Ship it, and open the shim exit-code issue as a follow-up.
