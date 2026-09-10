REVISE

1. blocking: AC7 / T0 incomplete. Spec requires `_create_metadata()` for `claude-native`, `codex-native`, and unknown harness, each with and without `session_title`/`project`. `gates.md` has bare only for `claude-native`; missing bare `codex-native` and bare unknown. T2 goldens would not catch label/title leakage for those variants.

2. blocking: AC2 is under-checked in the plan. T2’s mechanical “body verbatim apart from `self.` -> `spec.`” can leave `build_bundle()` calling `spec.render_config()`, which violates “read only BundleSpec fields”. Existing driver-backed bundle tests stay green because `OmnigentDriver` still has `render_config()`. Plan must explicitly add the `SimpleNamespace` AC2 test from the spec and require `build_bundle()` calls `render_config(spec)`.

3. non-blocking: T2/T3 mechanical import list omits scenarios repo code imports: `/Users/zarz/dev/xebia/flowbench-scenarios--s022/scripts/codex_review.py:23` and `tests/test_codex_review.py:7`. The plan defers them to the “Scenarios PR”, so engine V2 stays green via shim, but this is exactly a green-suite unpatched site until the paired PR lands.

4. non-blocking: shim design is acceptable. `__all__` plus `# noqa: F401` survives ruff, and the AST import-only check allows docstring/imports/`__all__`. No import cycle if `omnigent.py` imports `flowbench.driver.base` / `.bundle`, not `flowbench.driver`.

5. non-blocking: V4 command flags match `scenarios/swe_planning/run.py` and `watch.py`; the omitted watcher `--runs-root` is harmless here because its default resolves to the same `/Users/zarz/dev/xebia/flowbench-runs/swe_planning`. `uv run --extra live --with-editable /Users/zarz/dev/agents/flowbench--s022 ...` should exercise the engine branch if the recorded `flowbench.__file__` check is run under the identical invocation.
