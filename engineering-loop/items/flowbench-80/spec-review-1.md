REVISE

1. Blocking - V4 is missing. Spec/decision #10 rely on epic S02.2 line 49 saying V1/V2, but `verification.md:43-44` says V4 is mandatory after any change to `driver.py` or `loop.py`. This story moves both. Require V4 or explicitly amend the verification policy.

2. Blocking - AC4 compat surface is incomplete. Current old-path imports include: `driver`: module import (`tests/test_types.py:39`), `AgentDriver`, `OmnigentDriver`, `TurnResult`, `git_init_repo`, `_PAGE`; `loop`: `run_agent_session`, `_is_done`, `render_tail`. Sibling repo imports `OmnigentDriver` and `TurnResult`. AC4 omits `_PAGE`, `_is_done`, `render_tail`, and module import identity.

3. Blocking - Monkeypatch targets are a hidden behavior change. Tests patch `flowbench.runner.driver.asyncio.sleep/create_subprocess_exec/wait_for` and `flowbench.runner.loop.asyncio.sleep` (`tests/runner/test_driver.py`, `tests/runner/test_loop.py:236`). A docstring/re-export-only shim drops those names. Either migrate all patch targets with a grep AC over tests, or define old patch targets as intentionally unsupported.

4. Blocking - Several ACs are not machine-checkable or would pass broken code. AC2’s “touching no attribute outside `BundleSpec`” needs an AST/type check. AC7’s “no diff in shipped artifacts” is review-only; current config/bundle tests assert substrings/extracted files, not byte-identical config/tar entries. AC1’s grep would still pass shims with arbitrary top-level side effects.

5. Non-blocking - Citation error: spec says the dead marker is line 63; current `src/flowbench/runner/driver.py` has a blank line at 63 and the marker at line 64.

6. Non-blocking - Decision #3 arithmetic is directionally right and I agree with amending the roadmap rather than widening the split. Current driver is 617 lines; removing the cited ranges removes 137, leaving 480. Splitting polling just to hit ~350 conflicts with epic line 44 and churns S02.3’s incident-prone code path.
