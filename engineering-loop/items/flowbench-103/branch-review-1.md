REVISE

1. **Unsafe retries after failed label reads — `src/flowbench/driver/omnigent.py:255`.** Missing `resp.raise_for_status()` treats HTTP errors without labels as permission to resend. Probes with 401/404/500/503 each produced four sends. Validate HTTP success and test that failed reads prevent retries.

2. **Vacuous AC6a test — `tests/driver/test_omnigent.py:465`.** Replacing `_wait_idle` with an immediate `RUNNING` return passes with zero polls and zero elapsed fake time. Assert traversal through running → silent idle → running, and that the deadline is reached.

3. **AC2’s no-label-read assertion is ineffective — `tests/driver/test_omnigent.py:398`.** The test’s 1-second budget cannot cover the 30-second retry wait, independently bypassing label inspection. Moving label reads before the status check still passes all 71 driver tests. Give this test a retry-eligible budget.

4. **Retired behavior remains in the design contract — `docs/design/runner.md:94`.** The “Before S02.3” paragraph documents removed budgets and timings. Remove it under the explicit current-truth-only rule.

5. **Policy is duplicated and retired work remains documented — `docs/roadmap/epics/E02-runtime-robustness.md:61` and `docs/roadmap/current-state.md:71`.** The roadmap repeats the policy table and retains implemented S02.3 work; current-state still lists split retries as debt and advertises freshness retry at line 23. Remove retired material; keep the policy in `docs/design/runner.md`.

Verification: suite **296 passed, 1 skipped; exit 0**. Static contract checks and cancellation probes exited 0. No CI, gate-definition, or `.claude/` changes.

The shared timeout covers cooperative awaits. It cannot preempt synchronous JSON/text processing or stderr writes (`omnigent.py:297`), stop the filesystem worker (`:305`), or terminate a spawned tmux process (`:429`). Those can outlive the budget.
