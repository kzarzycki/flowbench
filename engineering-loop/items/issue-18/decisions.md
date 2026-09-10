# Issue #18 — decisions (rule-3 self-answered questions)

D1. **Red baseline vs the blocked-by-main rule.** Q: loop.md says stop if the fresh-worktree
baseline is red — the baseline here IS red (`test_run_case_offline` exceeds 90s, exit 124).
A: proceed. The red baseline is exactly the defect #18 fixes; applying the rule literally to the
fix-the-base issue deadlocks the loop forever (nothing can ever merge to make main green).
Evidence bound: everything OUTSIDE the issue-named file is green (74 passed, 1 skipped, 7.8s,
`--ignore=tests/test_swe_planning_run.py`). All gates run baseline-relative: the only failures
tolerated pre-fix are the issue-named hang and the known environmental failure below.

D2. **Scope split: suite hang vs CI config.** Q: the issue says "worth folding a CI story into
this fix" — does the loop edit `.github/workflows/ci.yml`? A: no. Gate 3's brief is
non-negotiable: "the diff touches no CI config". That rule exists so the unattended loop cannot
modify its own merge arbiter. The loop ships the hang fix (code + tests only); the CI change is
delivered as a concrete patch proposal in an issue comment for a human to apply. The PR will say
"addresses the suite-hang half of #18" and will NOT auto-close the issue.

D3. **Fix mechanism.** Q: truthful fakes (PR #19 stopgap), thread `artifact_grace_s` through
`run_case`, or a flowbench-side knob? A: thread the kwarg — the issue names this option verbatim
("thread `artifact_grace_s` through `run_case` so offline tests pass 0"). A flowbench-side knob
lives in the sibling repo (kzarzycki/flowbench), outside this loop's remit. The PR #19 stopgap
stays on its own branch; both changes are compatible (see D6).

D4. **Default value.** `artifact_grace_s: float = 60.0` on `run_case`, mirroring
`run_agent_session`'s default (flowbench `runner/loop.py:74`) — live CLI behavior unchanged;
`main()` does not pass it.

D5. **Test value.** Offline tests pass `artifact_grace_s=0.0`, per the issue text ("offline
tests pass 0").

D6. **Interplay with unmerged PR #19.** #19 adds `run_case_n` (calls `run_case`) and truthful
fakes in the same test file. This branch is designed against main (0be1345) only. Whichever
lands second rebases; the changes compose (grace 0 makes the fakes' `artifact_path` value
irrelevant to timing). Forwarding `artifact_grace_s` through `run_case_n` is follow-up work for
whoever integrates the two — `run_case_n` does not exist on main and is not specced here.

D7. **CI proposal content.** flowbench is PUBLIC (github.com/kzarzycki/flowbench, default
branch `master`); `uv sync` on runners fails because the editable dep `../../flowbench`
(pyproject `[tool.uv.sources]`) has no sibling checkout. Proposal: one workflow step before
`uv sync` — `git clone --depth 1 https://github.com/kzarzycki/flowbench.git
"$GITHUB_WORKSPACE/../../flowbench"` (resolves to `/home/runner/work/flowbench`, matching the
relative path from the repo root; runner-writable). Clone unpinned `master` to mirror the
declared dev model (live editable sibling, CLAUDE.md); whether to pin a SHA is flagged as the
human's call in the comment.

D8. **Known environmental failure.** `test_default_runs_root_is_sibling_of_repo` fails only
under `.claude/worktrees/` (worktree path contains "flowbench-scenarios"). Handling (revised
per spec-review-1 objection 1 — the pre-push hook cannot verify the branch's version of the
file in any push topology): the test is deselected in worktree gate runs AND the diff must not
modify it (checkable from the diff alone); main's CI, once the human applies the workflow
patch, is its real verifier.
