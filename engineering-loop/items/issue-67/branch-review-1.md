REVISE

1. `src/flowbench/runner/driver.py:436` calls `/child_sessions` without `limit` or pagination. The pinned endpoint defaults to 20 children, newest-first. With 21+ child sessions where an older child is still busy and the newest 20 are idle, `busy_children` is empty, `_wait_idle` returns `idle`, and the simulator can inject while a child is still running.

2. `docs/roadmap/target-architecture.md:85` still says self-wait turns get capped free nudges. Concrete failure: future work/tests following this doc will preserve the removed `Continue.` behavior instead of the new driver-level wait contract.

3. `docs/roadmap/epics/E00-guardrails.md:53` still names `loop._MAX_CONSEC_NUDGES` as a guardrail, but the symbol is deleted. Concrete failure: the guardrail checklist asks for a regression test that can no longer be written and misses the new guardrail: paginated child polling plus frozen-child stall.

4. `docs/roadmap/current-state.md:127` and `docs/roadmap/current-state.md:130` still describe `Continue.` relay pollution and cumulative `any_child_busy` as current code issues after the branch removes both. Concrete failure: reviewers/operators reading current state diagnose live behavior against code that no longer exists.

Checks: requested commands initially exited `2` due sandbox cache permissions, then `1` due untrusted `mise.toml`. Re-run in non-login shell with cache redirected: `pytest tests/runner` exit `0`; `ruff check src tests` exit `0`.
