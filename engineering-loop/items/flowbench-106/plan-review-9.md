REVISE

1. **V5’s watcher still reads the wrong directory.** [Plan:169–173](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:169) uses `<<'PY'`, so `Path("$RUNS")` stays literal. Shell probe resolved it to `<engine>/$RUNS/probe`; completion returned `None` despite an existing real `run.json`. Pass the root through argv or an explicitly exported environment variable. The launch-root correction is sound; the executable RunWatch objection remains open.

2. **V5 waits for the watcher, not the runner.** [Plan:183](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:183) prescribes `wait $!` after backgrounding the watcher. Probe: that wait returned **0** while the saved runner returned **7**. Explicitly assign `runner_pid=$!` immediately after launch, pass it to the watcher, then `wait "$runner_pid"` and capture its status. Use named PIDs consistently in both runs.

The flake-field objection is **closed**: session-level counts, idle status through `flow_stats`, positive counts explicitly accepted. Checkout and engine-pin requirements are sound.

Remaining plan passes: AC→task→test traceability; T2→T1→T3 ordering with BLE enabled last; named interfaces and artifact assertions. Proposed tests target actual bugs: probes reproduced container-message retries and swallowed foreign `RuntimeError`s.

Verification: **303 passed, 1 skipped**; suite, lint, formatting, CLI help, corrected-signature lint and behavior/watcher probes exited **0**. Mutable-default control exited **1/B006**, expected. Used temporary uv cache with `--no-sync`. No reviewed files changed; no live runs launched.
