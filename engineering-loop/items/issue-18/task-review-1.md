# Task review — commit 0e843a9 (thread artifact_grace_s through run_case)

## Verdict: APPROVE

- AC1: `artifact_grace_s: float = 60.0` keyword-only (run.py:53, after the bare `*`); forwarded at run.py:99. Verified by reading the file.
- AC2: fail-without-change verified directly — parent run.py checked out (no stash), new test failed with `TypeError: run_case() got an unexpected keyword argument 'artifact_grace_s'`, restored clean.
- AC3: both offline tests gained `artifact_grace_s=0.0`, nothing else touched in them.
- AC4: deselected file run = `6 passed, 1 deselected in 0.07s`; diff does not touch `test_default_runs_root_is_sibling_of_repo`.
- AC6: `main()` unchanged.
- Quality: new test matches neighbors (plain function, asyncio.run, reuses _FakeDriver/_StubSim), minimal; no weakened assertions; no scope creep.

No objections.
