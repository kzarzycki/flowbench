APPROVE

Attempt 3. All three objections from review 1 are closed, and nothing regressed.

## Objection 1 — closed

AC2 now asserts the outer repo's index file is byte-identical before and after,
and that `git -C outer status --porcelain` exits 0 with empty output under a
`GIT_*`-free env; plan T1 snapshots `(outer/".git"/"index").read_bytes()` before
the call and asserts both. That is the discriminator I verified empirically in
review 2, in both directions:

- full `GIT_` prefix scrub → outer index bytes unchanged, `status --porcelain`
  exits 0 with empty output;
- two-name scrub (`GIT_INDEX_FILE` left leaking) → the nested `git add` writes
  through the inherited index, the hash changes, and `status` fails with
  `fatal: unable to read e69de29b...`.

AC2's explanatory sentence is now correct: it names the outer index, not the
commit count, as what a two-name scrub breaks, and says explicitly that commit
count alone cannot see it.

## Objections 2 and 3 — closed

`git_init_repo` is cited at `driver.py:123`, the `subprocess.run` call site at
`driver.py:131`, and the per-repo identity config at `driver.py:135-137` — all
correct against the unfixed `master` file. AC4 and T3 no longer hardcode a pass
count; `189 passed / 1 skipped` survives only as a dated observation.

## Re-checked, unchanged

- (a) Scope still matches the issue as filed: one function, the `GIT_` prefix
  scrub the issue itself proposes. No invention, no loss.
- (b) All four ACs are objectively checkable from code and tests.
- (c) Codebase claims verified against `master`: `os` imported at module scope;
  `grep -rn '"git"' src scenarios --include='*.py'` returns the single call site;
  identity is set in the fresh repo before the commit, so dropping
  `GIT_AUTHOR_*`/`GIT_COMMITTER_*` is safe.
- (d) decisions.md entries all follow from issue plus code.
- (e) Traceability now complete: AC1 → T2, discriminated by T1's index
  assertions; AC2/AC3 → T1; AC4 → T3.
- (f) T1 (red) → T2 (green) → T3 (gates); exact paths, the env-filter expression,
  and every assertion are specified.
- (g) Test would catch the bug: reproduced the original failure — with
  `GIT_DIR`/`GIT_WORK_TREE` leaking, the nested `git commit` exits 1 and
  `nested/.git` is never created, so the test is red on master.
- (h) Proportionate to an S change.

## Non-blocking note for the implementer

Keep T1's stated assertion order: compare the index bytes *before* running
`git -C outer status`, since a status run can refresh the outer index's stat data
and would make the byte-compare self-defeating. The plan already orders it that
way; do not reorder it.
