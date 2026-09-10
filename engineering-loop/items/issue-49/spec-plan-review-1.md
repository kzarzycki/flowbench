REVISE

Verified by reading the code and reproducing the bug: the unfixed sequence
genuinely fails (`git -C nested commit` exits 1, `nested/.git` never created,
outer repo stays at 1 commit), so the planned test would be red on master. The
suite baseline `189 passed, 1 skipped` is accurate. Scope (solves the issue as
filed, nothing invented, nothing lost), sizing (S), the decisions.md inferences,
and the task ordering all hold.

## Blocking

1. **AC1 has no discriminating test (traceability failure).** AC1 is "`run()`
   passes an explicit `env` that contains no key starting with `GIT_`" — the
   prefix scrub is the root-cause decision recorded in decisions.md ("fixing only
   the two named in the issue leaves the same bug reachable from a different
   hook"). But T1 monkeypatches only `GIT_DIR` and `GIT_WORK_TREE`, so an
   implementation that scrubs exactly those two names passes every test in the
   plan. The distinguishing claim is unverified, and a later narrowing refactor
   would go undetected.

   Fix: in T1 also
   `monkeypatch.setenv("GIT_INDEX_FILE", str(outer / ".git" / "index"))`
   (optionally `GIT_OBJECT_DIRECTORY`). Under a two-var-only scrub the nested
   `git add -A` / `git commit` writes through the inherited index and the
   assertions break; under the prefix filter it passes. A direct assertion on the
   env dict handed to `subprocess.run` also satisfies AC1, but the behavioural
   version is stronger.

## Non-blocking (fix in passing; not grounds for another cycle)

2. Spec cites `src/flowbench/runner/driver.py:124` for `git_init_repo`; it is at
   line 123 on master. Same off-by-~3 on the "driver.py:135-137" citation for the
   per-repo identity config.
3. T3's hard-coded expectation "189 passed, 1 skipped" is correct today but will
   drift as tests are added; prefer "no new failures".

## Checked

- (a) scope: matches the issue; the widening from two vars to the `GIT_` prefix
  is the issue's own suggested fix, not invention.
- (b) ACs 1-4 are all objectively checkable from code/tests.
- (c) codebase claims verified: `os` imported at module scope
  (`driver.py:25`); `grep -rn '"git"' src scenarios --include='*.py'` returns the
  single `subprocess.run` call site in `git_init_repo`; the function sets
  `user.email`/`user.name` in the fresh repo before committing, so dropping
  `GIT_AUTHOR_*`/`GIT_COMMITTER_*` cannot break the commit.
- (d) every decisions.md entry follows from the issue plus the code.
- (e) criterion→task→test: AC2/AC3 → T1; AC4 → T3; **AC1 → T2 but no
  discriminating test** (objection 1).
- (f) T1 (red) → T2 (green) → T3 (gates); file paths and the exact env-filter
  expression are specified.
- (g) test strategy would catch the bug — confirmed red on unfixed behaviour by
  replaying the git sequence under `GIT_DIR`/`GIT_WORK_TREE`.
- (h) proportionate to an S-sized change: one function, one test.

## References

- spec: `.claude/engineering-loop/items/issue-49/spec.md`
- plan: `.claude/engineering-loop/items/issue-49/plan.md`
- test: `/Users/zarz/dev/agents/flowbench--bugs/tests/runner/test_driver_config.py:14`
- fix: `/Users/zarz/dev/agents/flowbench--bugs/src/flowbench/runner/driver.py:129-135`
