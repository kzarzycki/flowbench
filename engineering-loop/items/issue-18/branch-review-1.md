# Branch review — loop/issue-18-offline-suite-ci (gate 3)

**Verdict: APPROVE**

Base: origin/main 0be1345. Reviewed the full branch diff (6 commits, 10 files: `scenarios/swe_planning/run.py` +2, `tests/test_swe_planning_run.py` +37, plus `.claude/engineering-loop/items/issue-18/*` artifacts). I went in looking for a reason to reject and did not find one. Evidence per rule:

## Rule 1 — no CI/gate/loop config touched: PASS
`git diff origin/main...HEAD --name-only` filtered against the authorized set leaves nothing (verified empty remainder). No `.github/**`, no gate definitions; the only `.claude/` paths are `items/issue-18/{spec,decisions,plan,state.json,reviews}` — all authorized artifacts.

## Rule 2 — no test deleted/skipped/weakened: PASS
The test-file diff contains **zero removed lines** (`git diff ... | grep '^-'` empty) and no new skip/xfail markers. Test count 6 → 7. The two modified tests (`test_run_case_offline` line 105, `test_run_case_flags_missing_plan` line 160) each gained exactly one kwarg line, `artifact_grace_s=0.0`; every pre-existing assertion is byte-identical to origin/main. `test_default_runs_root_is_sibling_of_repo` is untouched by the diff (deselection is runtime-only, per AC4/D8).

## Rule 3 — code change exactly as authorized: PASS
`scenarios/swe_planning/run.py` diff is 2 added lines: keyword-only `artifact_grace_s: float = 60.0` in `run_case`'s signature (run.py:54, after the bare `*`) and verbatim forwarding `artifact_grace_s=artifact_grace_s` in the `run_agent_session(...)` call (run.py:95). `main()`'s `run_case` call (run.py:247) unchanged — does not pass the kwarg (AC6). No refactoring, no drive-by edits anywhere.

## Rule 4 — tests gate: PASS
`uv run pytest -q --deselect tests/test_swe_planning_run.py::test_default_runs_root_is_sibling_of_repo` in the worktree:
80 passed, 1 skipped, 1 deselected in 0.92s — exit code 0 (checked directly, not via a pipe). On main this suite hangs >90s in `test_run_case_offline`; here the whole suite is sub-second — AC4/AC5 satisfied with margin.

**AC2 fail-without-change verified empirically**: origin/main's `run.py` checked out into the worktree — new test FAILED with `TypeError` at tests/test_swe_planning_run.py:258. Restored, `git status` clean afterwards.

## Rule 5 — semantics: PASS
- **Default identity**: `main()` doesn't pass the kwarg; `run_case` forwards an explicit `60.0` equal to `run_agent_session`'s own default (verified via inspect.signature against the venv's actual flowbench). Live behavior byte-identical to main.
- **0.0 skips the grace-poll safely**: flowbench `runner/loop.py:116-118` — with 0.0, `grace` = assignment timestamp; monotonic is non-decreasing so the first `time.monotonic() < grace` check is False (equal → False too). Zero sleep iterations, no underflow, cannot loop.

## Adversarial angles
- **Other `run_case` callers**: repo-wide grep — only the definition and `main()`. (PR #19's `run_case_n` is not on main or this branch; composition is D6's documented follow-up.)
- **Kwarg-rename protection regressed?** No — improved: the two offline tests drive the REAL `run_agent_session` with the kwarg forwarded; a flowbench rename would TypeError both. On main no test passed the kwarg at all.
- **Is `artifact_grace_s=0.0` semantically honest?** Yes — the grace-poll only waits for a DONE-claimed artifact to flush; the fakes never produce a path, so the wait can never change the outcome, only the runtime.
- **Artifacts vs shipped code**: spec/decisions/plan/reviews/state all consistent with the diff.
- **AC8 CI-patch text soundness**: repo PUBLIC (default `master`); path math holds ($GITHUB_WORKSPACE/../../flowbench = /home/runner/work/flowbench = ../../flowbench from repo root); placement before `uv sync` matches ci.yml:36; clone non-idempotency disclosed. Sound to post.

## Non-blocking notes
1. The forwarding test's recorder returns a minimal session dict; if `run_case` later reads more session keys the test needs updating — cosmetic.
2. Clone URL unpinned `master`; spec correctly flags pinning as the human's call.

No objections. APPROVE.
