APPROVE

# Gate 3 re-review — commit 1454b41 only

`fix(todo_app): console shim propagates the entry point's exit code (#46 gate follow-up)`
2 files, +19/-2. Scope is exactly the g3 finding; nothing else touched.

## Exit-code semantics — verified empirically

Called the branch's `resolve_invoker` against seven synthesized console-only apps and ran the
returned invoker:

| `main()` does | exit code | correct? |
| --- | --- | --- |
| returns `None` (implicit) | 0 | yes — `SystemExit(None)` is exit 0 |
| `return 0` | 0 | yes |
| `return 2` | 2 | yes |
| `sys.exit(0)` itself | 0 | yes — its own `SystemExit` unwinds before `raise SystemExit(...)` is ever reached |
| `sys.exit(3)` itself | 3 | yes, same reason |
| `raise ValueError` | 1, traceback on stderr | yes — unchanged from before |
| `return "bad input"` | 1, message on stderr | yes — the documented `SystemExit(str)` convention |

The `None` case is the one that could have regressed (the majority of real entry points return
nothing), and it is correct: `SystemExit(None)` exits 0, so `console_only_app` still scores
1.0 — confirmed by `test_console_only_app_passes_all_checks` still green. An entry point that
calls `sys.exit()` itself is unaffected because that exception propagates out of `_entry()`
before the outer `raise` evaluates. This now matches what `python -m todo` gives via
`raise SystemExit(main(...))` in `fixtures/good_app/todo/__main__.py:52` — the two invoker
paths are finally symmetric, which was the point of the finding.

## Test honesty

`tests/scenarios/todo_app/test_acceptance.py:122` `test_console_shim_propagates_exit_code`.

Verified red on the parent commit — `git archive 10e9546` into a scratch tree, branch test file
copied in:

```
FAILED tests/scenarios/todo_app/test_acceptance.py::test_console_shim_propagates_exit_code
  assert True is False  (app_runs=True; add_first/add_rest/done_first all passed)
1 failed, 8 passed
```

That is the exact free-3/7 pass I measured in review 1, so the test pins the real defect rather
than an artifact. It builds its own throwaway app inline instead of adding a permanently
misleading "broken" fixture next to `good_app`/`bad_app` — right call. The assertions are the
strong pair (`app_runs is False` AND `not any(c.passed ...)`), not a weaker `score < 1.0`, and
they are honest: `main()` returns 2 and writes nothing, so every check genuinely must fail —
`assert not any(...)` is not overfitted, it is the only correct expectation.

No existing test was touched by this commit; `test_console_only_app_passes_all_checks` is the
counterweight proving the change did not simply make the shim path fail everything.

## Gates

`uv run pytest -q` → 193 passed, 1 skipped. `ruff check` clean, `ruff format --check` clean
(55 files). Still nothing under `.github/`, `.claude/`, no gate or CI definition.

## Verdict

APPROVE. The g3 finding is closed correctly and no follow-up remains open from review 1.
