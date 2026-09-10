# Spec review — issue #18 (offline suite hang / CI story)

## Verdict: REVISE

Two objections. Both are narrow and fixable; everything else checks out — the fact-checking results are listed after the objections so the rework doesn't re-litigate what's already verified.

---

### Objection 1 — AC4/D8's verification mechanism for the deselected test is unsound as written

AC4 deselects `test_default_runs_root_is_sibling_of_repo` and justifies it with:

> "the full file is verified green on the main checkout by the pre-push hook"

and D8:

> "excluded from worktree gate runs, verified on the main checkout before push (pre-push hook runs there)"

The hook exists (`.pre-commit-config.yaml`: local `pytest` hook, `entry: uv run pytest -q`, `stages: [pre-push]`), but the claim can't be true in either possible push topology:

- **Push from the worktree** (where the branch lives): worktrees share the main repo's `.git/hooks`, and pre-commit runs `uv run pytest -q` with CWD = the worktree. There the deselected test fails environmentally — `default_runs_root()` resolves to `<...>/flowbench-scenarios/.claude/worktrees/flowbench-runs/swe_planning`, and `assert "flowbench-scenarios" not in p.parts` (tests/test_swe_planning_run.py:177) trips. The push is blocked unless the loop uses `--no-verify`/`SKIP`, in which case nothing verified anything.
- **Push from the main checkout** (via refspec, branch stays in the worktree): the hook runs pytest against **main's working tree**, i.e. main's version of `tests/test_swe_planning_run.py` — not the branch's edited file. "The full file is verified green" is then verified for the wrong code. (And main's suite currently burns the very 60s graces under fix, ~2+ min, so this path is also operationally shaky pre-merge.)

So the branch's changed test file is never executed in any environment where the deselected test passes. Fix: drop the pre-push-hook rationale and replace the guard with something checkable from the diff alone, e.g. AC4 gains "and the diff does not modify `test_default_runs_root_is_sibling_of_repo`" — that plus CI-on-main (once the human applies the workflow patch) is the honest verification story. The checkable core of AC4 (deselected run exits 0 in <60s in the worktree) is fine and should stay.

### Objection 2 — the CI half's delivery is asserted but not enforced by any AC

The scope split is legitimate (see fact-check below), but criterion for the split is that the non-shipped part is *concretely delivered*. The spec says:

> "A concrete patch is posted on #18 for a human to apply"

— present tense, yet no acceptance criterion covers it. AC1–AC7 are all code/diff checks; in an unattended loop where the gates verify ACs and nothing else, the comment can silently never be posted and every gate still passes, leaving the CI half of the issue (which the issue text explicitly asks to fold in: "Worth folding a CI story ... into this fix") delivered nowhere. Add an AC8, machine-checkable, e.g.: `gh issue view 18 --repo xebia/flowbench-scenarios --comments` contains the step name `Checkout flowbench (editable path dep` (or the clone URL). Also state *when* in the loop the comment gets posted (with the PR, not at spec time).

---

## Verified — claims that hold (checked against the cited files)

- **flowbench `runner/loop.py`**: `artifact_grace_s: float = 60.0` is the `run_agent_session` parameter default at line 74; the grace-poll (`grace = time.monotonic() + artifact_grace_s` … `await asyncio.sleep(2.0)`) is exactly lines 116–119. Spec's line refs are accurate.
- **`scenarios/swe_planning/run.py`**: the `run_agent_session(...)` call is lines 86–94 and passes no `artifact_grace_s`; `main()` (line 235) calls `run_case` without it. Spec claims true.
- **Test fakes**: `_FakeDriver.artifact_path()` returns `None` (lines 44–45); `_MissingPlanDriver` inherits it. Both `test_run_case_offline` and `test_run_case_flags_missing_plan` reach the DONE path; `test_run_case_rejects_flow_count` does not. AC3's target list is exactly right.
- **AC2's fail-without-change property**: `run.py` does `from flowbench.runner.loop import run_agent_session`, so monkeypatching `scenarios.swe_planning.run.run_agent_session` works; on main, `run_case(..., artifact_grace_s=0.0)` raises `TypeError` from `run_case` itself. Sound.
- **CI patch path math**: `[tool.uv.sources] flowbench = { path = "../../flowbench", editable = true }` (pyproject.toml:32–33). On a default checkout, `$GITHUB_WORKSPACE` = `/home/runner/work/flowbench-scenarios/flowbench-scenarios`, so `$GITHUB_WORKSPACE/../../flowbench` = `/home/runner/work/flowbench` = `../../flowbench` from the repo root. Correct, and `/home/runner/work` is runner-writable; `git clone` creates the target dir.
- **flowbench is public**: unauthenticated `GET api.github.com/repos/kzarzycki/flowbench` returns 200, `private: false`, `default_branch: master`. D7 correct. Crucially, commit `9c93ec5` (the grace-poll) **is on origin/master** (merged via `5e8d005`; local master is in sync), so a CI clone of unpinned master gets a `run_agent_session` that accepts `artifact_grace_s` — the forwarded kwarg won't TypeError on runners.
- **Workflow ordering**: the `pre-commit` CI step runs the default pre-commit stage only (the local pytest hook is `stages: [pre-push]`), so it doesn't need flowbench; inserting the clone "before `uv sync`" is the right spot.
- **PR #19**: exists, open, head `loop/issue-3-n-runs-aggregation` — matches the issue's "stopgap shipped on the issue-3 branch" and D6.
- **Environmental failure (D8's premise)**: real — verified against the actual test assertion and worktree path. Only the *verification mechanism* claim is wrong (Objection 1).

## Decisions log — all reasonable inferences

D1 (proceed on red baseline: the red baseline is the defect, applying the stop-rule literally deadlocks; evidence-bounded to the issue-named file) — sound. D2 (scope split) — supported by the issue's own framing ("Worth folding a CI story into this fix" lists options, it doesn't mandate shipping workflow edits) and the non-negotiable gate-3 rule; contingent on Objection 2. D3 (thread the kwarg) — the issue names this option verbatim. D4 (default 60.0 mirroring) — least-surprise; see minor note below. D5 (0.0) — verbatim from the issue. D6 (PR #19 interplay) — verified plausible, correctly scoped out (`run_case_n` not on main). D7 — fully verified. D8 — premise verified, mechanism flawed (Objection 1). No product-judgment guesses beyond what the issue supports.

## Minor notes (non-blocking)

1. Duplicating the `60.0` default on `run_case` can drift from flowbench's default. A sentinel (`artifact_grace_s: float | None = None`, forward only when set) avoids drift — but the spec's choice is defensible and simpler; fine to keep, just noting the tradeoff was implicitly made.
2. The proposed clone step is not idempotent (`git clone` fails if the dir exists) — harmless on fresh runners; worth one clause in the issue comment if re-run steps are ever a concern.
3. Spec says pinning master "is the human's call" — good; keep that flag in the posted comment verbatim.
