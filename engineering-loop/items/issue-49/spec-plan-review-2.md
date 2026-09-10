REVISE

Attempt 2. Objection 3 is fixed. Objection 2 is fixed (and was partly my error —
see below). **Objection 1 is not fixed**: `GIT_INDEX_FILE` was added to the test
env, but none of AC2's assertions can see its effect, so a two-name scrub still
passes. The revision also introduced a factually wrong sentence in AC2.

## Blocking

1. **AC2 still does not discriminate the `GIT_` prefix scrub from a two-name
   scrub, and its new justification is false.** AC2 now says: "under a two-name
   scrub the nested `git add` writes through the inherited index and the
   assertions break." I replayed exactly that case (`GIT_DIR`/`GIT_WORK_TREE`
   scrubbed, `GIT_INDEX_FILE` left in the environment, then the real
   `git_init_repo` sequence against a fresh `nested/`):

   ```
   EXIT=0
   nested .git: yes
   nested rev-parse: b3c557a0...
   outer count: 1
   ```

   All four of AC2's assertions pass — it does not raise, `nested/.git` exists,
   `rev-parse HEAD` resolves, and the outer repo gained no commit. The nested
   `git add` does write through the inherited index, but the damage lands
   somewhere AC2 never looks: the outer repo's index is left corrupt
   (`git -C outer status` afterwards → `fatal: unable to read e69de29b...`),
   while its commit count is untouched. So the added `setenv` changes nothing
   about what the test can detect, and the sentence explaining why it does should
   not stand as written.

   Fix — add one assertion that observes the outer index. Either is sufficient:
   - snapshot `(outer / ".git" / "index").read_bytes()` before calling
     `git_init_repo` and assert it is byte-identical after; or
   - assert `git -C outer status --porcelain` (run with the scrubbed env helper
     `_no_git_env()`) exits 0 and prints nothing.

   I verified both directions: under the full `GIT_` prefix scrub the outer index
   is unchanged and `status --porcelain` exits 0 with empty output; under the
   two-name scrub the index hash changes and `status` fails. That is a real
   discriminator; `GIT_INDEX_FILE` alone is not.

   Keeping the `GIT_INDEX_FILE` setenv is right — it just needs an assertion that
   can fail because of it. Update the AC2 explanatory sentence to say the outer
   index (not the commit count) is what breaks.

## Resolved

2. Line citations — resolved, and my original objection was half wrong: against
   `master`, `git_init_repo` is at line 123 (spec previously said 124; now
   corrected), but `driver.py:131` for the `subprocess.run` call and
   `driver.py:135-137` for the per-repo identity config were already correct for
   the unfixed file — those cites in the spec's Fix section and in decisions.md
   need no change. Verified against `git show master:src/flowbench/runner/driver.py`.
3. Hard-coded test count — resolved. AC4 now reads "no new failures" and T3 keeps
   `189 passed / 1 skipped` only as a dated observation.

## Nothing else regressed

Scope, size (S), the `Fix`/`Why safe` reasoning, decisions.md, and the T1→T2→T3
ordering are unchanged from attempt 1 and still hold. AC3 (test red on master)
still holds: I reproduced the original failure — the nested `git commit` exits 1
and `nested/.git` is never created when `GIT_DIR`/`GIT_WORK_TREE` leak.
