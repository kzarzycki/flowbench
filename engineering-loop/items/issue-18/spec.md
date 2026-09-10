# Issue #18 — offline suite hang: thread `artifact_grace_s` through `run_case`

## Problem

flowbench 9c93ec5 added a grace-poll to `run_agent_session` (`runner/loop.py:116-119`): after
the DONE token, it polls `driver.artifact_path() is None` every 2s for `artifact_grace_s`
(default 60.0). The offline test fakes in `tests/test_swe_planning_run.py` (`_FakeDriver`,
`_MissingPlanDriver`) return `None` from `artifact_path()` forever, so every fake-driven
`run_case` test burns 60s per flow (2 flows per case). Reproduced on a fresh worktree from main
(0be1345): `pytest tests/test_swe_planning_run.py::test_run_case_offline` exceeds 90s (exit 124
under timeout); the rest of the suite is green in 7.8s.

`run_case` (`scenarios/swe_planning/run.py:86-94`) calls `run_agent_session` without
`artifact_grace_s`, so callers cannot turn the grace-poll off.

## Fix (loop-shippable scope)

1. `run_case` gains a pass-through kwarg `artifact_grace_s: float = 60.0` (default mirrors
   `run_agent_session`), forwarded verbatim to `run_agent_session`. `main()` does not pass it —
   live CLI behavior is unchanged.
2. The two fake-driven tests that reach the DONE path — `test_run_case_offline` and
   `test_run_case_flags_missing_plan` — pass `artifact_grace_s=0.0`.
3. A new test pins the forwarding: monkeypatch `scenarios.swe_planning.run.run_agent_session`
   with a recorder, call `run_case(..., artifact_grace_s=0.0)`, assert the recorded call
   received `artifact_grace_s == 0.0`. On main this test fails with `TypeError: unexpected
   keyword argument` — it fails without the change.

## Out of scope (delivered as an issue comment, not in the diff)

The CI half of #18 (runners cannot resolve the editable `../../flowbench` dep, so CI on main is
structurally red) requires editing `.github/workflows/ci.yml`, which the loop's gate 3 forbids
("the diff touches no CI config" — the loop must not modify its own merge arbiter). A concrete
patch is posted on #18 for a human to apply: one step before `uv sync` cloning the public
flowbench repo to the expected sibling path —

```yaml
- name: Checkout flowbench (editable path dep, see pyproject [tool.uv.sources])
  run: git clone --depth 1 https://github.com/kzarzycki/flowbench.git "$GITHUB_WORKSPACE/../../flowbench"
```

(`$GITHUB_WORKSPACE/../../flowbench` = `/home/runner/work/flowbench` = `../../flowbench` from
the repo root; unpinned `master` mirrors the local editable-sibling dev model, pinning is the
human's call; note the step is not idempotent — `git clone` fails if the dir already exists,
harmless on fresh runners.) The comment is posted in Phase 9, together with opening the PR.
Because of this split, the PR references #18 but does not `Close` it.

## Acceptance criteria (machine-checkable)

- AC1: `run_case` in `scenarios/swe_planning/run.py` has parameter `artifact_grace_s: float = 60.0`
  and its `run_agent_session(...)` call passes `artifact_grace_s=artifact_grace_s`.
- AC2: a test exists that monkeypatches `run_agent_session`, calls
  `run_case(..., artifact_grace_s=0.0)`, and asserts the forwarded value; it raises `TypeError`
  when run against main's `run_case` (fails without the change).
- AC3: `test_run_case_offline` and `test_run_case_flags_missing_plan` call `run_case` with
  `artifact_grace_s=0.0`.
- AC4: `uv run pytest -q tests/test_swe_planning_run.py --deselect
  tests/test_swe_planning_run.py::test_default_runs_root_is_sibling_of_repo` exits 0 in under
  60s inside the worktree, AND the diff does not modify
  `test_default_runs_root_is_sibling_of_repo` (the deselected test is a pre-existing
  environmental failure under `.claude/worktrees/`, decisions.md D8; leaving it untouched means
  main's CI — once the human applies the workflow patch — remains its verifier).
- AC5: full suite baseline-relative green: `uv run pytest -q` with the same single deselect
  exits 0 in the worktree.
- AC6: `main()` in `scenarios/swe_planning/run.py` does not pass `artifact_grace_s` (diff shows
  no change to `main()`'s `run_case` call).
- AC7: the diff touches only `scenarios/swe_planning/run.py`, `tests/test_swe_planning_run.py`,
  and `.claude/engineering-loop/items/issue-18/*` artifacts — no CI config, no gate definitions.
- AC8: `gh issue view 18 --repo xebia/flowbench-scenarios --comments` contains the step name
  `Checkout flowbench (editable path dep` — the CI patch comment was actually posted (checked
  at Phase 9, when the PR is opened).
