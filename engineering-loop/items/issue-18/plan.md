# Issue #18 — implementation plan

Spec: `spec.md` (approved, spec-review-2). One small change; a single TDD task plus gate runs.
Worktree: `.claude/worktrees/loop+issue-18-offline-suite-ci`, branch `loop/issue-18-offline-suite-ci`.

## Task 1 — thread `artifact_grace_s` through `run_case` (TDD)

Files: `scenarios/swe_planning/run.py`, `tests/test_swe_planning_run.py`. Nothing else.

1. **RED** — append to `tests/test_swe_planning_run.py`:
   `test_run_case_forwards_artifact_grace(tmp_path, monkeypatch)`:
   - monkeypatch `scenarios.swe_planning.run.run_agent_session` with an async recorder that
     captures its kwargs and returns `{"items": [], "events": [], "artifact_text": "# p"}`;
     also monkeypatch-or-stub `run_judge` (fake returning `"WINNER: A"`); use the existing
     `_FakeDriver`/`_StubSim` factories from the file for the rest.
   - call `run_case(case, run_id="t", ..., runs_root=tmp_path, artifact_grace_s=0.0)`
   - assert the recorder saw `artifact_grace_s == 0.0`.
   Run it: must FAIL with `TypeError: run_case() got an unexpected keyword argument` (AC2's
   fail-without-change property).
2. **GREEN** — in `run.py`: add `artifact_grace_s: float = 60.0` to `run_case`'s keyword-only
   params (after `deadline_s`) and pass `artifact_grace_s=artifact_grace_s` in the
   `run_agent_session(...)` call. Do NOT touch `main()` (AC6).
3. Update `test_run_case_offline` and `test_run_case_flags_missing_plan` to pass
   `artifact_grace_s=0.0` (AC3) — this is what makes the file fast again.
4. Verify AC4: `uv run pytest -q tests/test_swe_planning_run.py --deselect tests/test_swe_planning_run.py::test_default_runs_root_is_sibling_of_repo`
   exits 0 in <60s.
5. Commit: `fix: thread artifact_grace_s through run_case so offline tests pass 0 (#18)`.

Implementer: sonnet (mechanical, fully specified). Task reviewer: sonnet, checks AC1–AC4, AC6
against the diff.

## Gates (main session)

- AC5: full suite in worktree with the single D8 deselect → exit 0.
- AC7: `git diff origin/main --name-only` ⊆ {run.py, test file, issue-18 artifacts}.
- AC4 guard: diff does not touch `test_default_runs_root_is_sibling_of_repo`.
- Gate 3 adversarial branch review (Fable) → mechanical gates (rebase if main moved, suite,
  pre-commit) → push from main checkout → PR referencing #18 (no `Closes`) + post the CI-patch
  comment on #18 (AC8 check) → merge path per loop.md Phase 9.

## Non-goals

No `run_case_n` changes (not on main — D6), no CI config edits (D2), no flowbench edits.
