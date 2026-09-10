# Spec review 2 — issue #18 (offline suite hang / CI story)

## Verdict: APPROVE

Both objections from spec-review-1 are resolved, and the edits introduce no new inconsistencies. Scoped re-review only — prior fact-checking of codebase claims is not re-litigated.

---

## Objection 1 — pre-push-hook verification story: RESOLVED

The unsound pre-push rationale is gone from the operative text of both AC4 and D8, replaced by a diff-checkable guard plus CI-on-main as the honest verifier.

- **AC4** (spec.md:56–61) now reads: deselected run exits 0 in <60s in the worktree **AND** "the diff does not modify `test_default_runs_root_is_sibling_of_repo`". The justification is now "leaving it untouched means main's CI — once the human applies the workflow patch — remains its verifier." No pre-push claim remains. The old "verified green on the main checkout by the pre-push hook" language is gone.
- **D8** (decisions.md:46–51) now says the test "is deselected in worktree gate runs AND the diff must not modify it (checkable from the diff alone); main's CI, once the human applies the workflow patch, is its real verifier." The only mention of the pre-push hook is the parenthetical explaining *why* the mechanism was changed ("the pre-push hook cannot verify the branch's version of the file in any push topology") — it is cited as the reason the old story was dropped, not relied upon. That is correct and honest.

The checkable core the reviewer wanted kept (deselected run exits 0 in <60s in the worktree) is preserved.

## Objection 2 — CI patch comment not enforced by any AC: RESOLVED

- A new **AC8** (spec.md:68–70) exists and is machine-checkable: `gh issue view 18 --repo xebia/flowbench-scenarios --comments` contains the step name `Checkout flowbench (editable path dep` — "the CI patch comment was actually posted (checked at Phase 9, when the PR is opened)."
- Timing is stated in two places, consistently: AC8's parenthetical ("checked at Phase 9, when the PR is opened") and spec.md:44 ("The comment is posted in Phase 9, together with opening the PR"). This matches the reviewer's ask to state *when* the comment posts (with the PR, not at spec time).

## Consistency check: PASSES

- **AC8's distinctive string is present in the proposed patch text.** spec.md:37 is `- name: Checkout flowbench (editable path dep, see pyproject [tool.uv.sources])`, and decisions.md D7 reproduces the same clone step. `Checkout flowbench (editable path dep` is an exact prefix of that step name, so a comment quoting the patch verbatim satisfies the AC8 grep. The check can actually pass.
- **No contradiction with AC7.** AC7 (diff touches only run.py, the test file, and issue-18 artifacts — no CI config) is untouched by the edits. AC8 requires *posting a comment*, not a diff change, so it does not conflict with AC7's "no CI config" constraint. AC4's new "diff does not modify `test_default_runs_root_is_sibling_of_repo`" clause is consistent with AC7 (it constrains, does not expand, the diff).
- **PR-close semantics stay coherent.** spec.md:45 and D2 both keep "the PR references #18 but does not `Close` it," consistent with the CI half being delivered as a comment rather than shipped. AC8 verifying the comment aligns with that split.

No new problems introduced. The two objections are cleanly addressed with machine-checkable criteria, and the surrounding spec/decisions remain internally consistent.
