REVISE

The spec’s SDK contract and decisions are sound. Two plan gaps remain.

1. **[plan] Task 4 does not reliably validate the changed engine.** [Task 4](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:144) needs corrected checkout, dependency, and process instructions:
   - The scenarios checkout’s lockfile **and installed engine** point to `f4cb85e`, before the SDK migration. Ordinary `uv run` preserves that pin. Add dependency update/sync and verification that the imported engine matches the merged revision.
   - V5 cannot run from the prescribed scenarios checkout. Probing its command with `--help` exits **1**, `ModuleNotFoundError: scenarios.coding_workflow`. Run V5 from the engine checkout and specify its actual run directory.
   - Supply the V5 watcher invocation with `scenario="coding_workflow"` and the correct runs root. The planning watcher hardcodes `swe_planning`; reusing it misses these sessions. Specify background launch/PID capture and runner exit-code checks. The existing watcher also exits **0** when the runner dies without `run.json`.

2. **[plan] Task 1’s literal default arguments break its lint gate.** [Line 65](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:65) prescribes `labels={}` defaults for both doubles. Ruff reports **B006**, exit **1**, for those signatures. Keep `labels=None` and normalize it to a fresh dictionary inside each double. This preserves the intended SDK shape and keeps Task 1 green.

Round-6 closure: **#1 and #2 closed** by overflow coverage and the string guard; **#3’s SDK rewrite closed**, but its double-default fix needs objection 2 above; **#4 closed** by the actual order T2→T1→T3; **#5 closed** by assigning coverage expansion to T3; **#6 partially closed**—Task 4 exists, but remains faulty as above.

Independent traceability:

| Criterion | Task → test/check | Assessment |
|---|---|---|
| AC1 | T3 → BLE lint and reasoned-waiver audit | Covered |
| AC2 | T1 → transport/SDK/timeout errors, malformed bodies and values, overflow, coercion, propagation, retry rows | Covered |
| AC3 | T1 → real-SDK 503 carrying token label | Covered |
| AC4 | T2 → transcript fallback, watcher fallback/propagation, unreadable scorer path | Covered |
| AC5 | T1/T2 → seven module-specific DEBUG assertions; T1 scorer assertion strengthening | Covered |
| AC6 | T1 → unchanged close/pane swallow tests | Covered |
| V1 | T3 → full suite and 100% diff coverage including scenarios | Correctly last |
| V4/V5 | T4 → live runs, watchers, artifact/result checks | Blocked by objection 1 |

Verification: SDK probes **0**; pytest **0** (**303 passed, 1 skipped**); lint **0**; formatting **0**. Explicit BLE audit **1**, identifying the four unfinished driver catches. Reviewed files unchanged.
