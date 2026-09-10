REVISE

1. blocking — AC12/V4 is not satisfied. `docs/roadmap/verification.md:43` makes V4 mandatory after driver/loop changes, and `gates.md` has no live `swe_planning` run id, watcher exit, parsed winner, or per-flow `plan.md`/`transcript.md`/`session.json` evidence. It ends at AC7/mechanical gates.

2. non-blocking — Docs still name stale `_to_jsonable`: `docs/roadmap/current-state.md:107` and `docs/roadmap/epics/E02-runtime-robustness.md:119`. Code now exposes `flowbench.transcript.to_jsonable`.

3. non-blocking — `start()` fake misrepresents real `SessionsChat`: installed client’s `session_id` property returns `self._session.id`, but `tests/driver/test_omnigent.py:808` injects `SimpleNamespace(session_id="conv_new", **kw)` and asserts that at `:854`. It pins calls, but not the real chat shape.

4. non-blocking — `tests/driver/test_bundle.py:203` contradicts the approved plan’s negative-control wording: it asserts `flowbench.driver.omnigent.render_config/build_bundle/session_metadata` exist as imported module attrs. Not old-path breakage, but it widens the canonical module surface. Use `bundle.render_config(...)` imports or amend the plan.
