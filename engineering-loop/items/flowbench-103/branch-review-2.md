REVISE

1. **AC4’s no-retry tests are ineffective — `tests/driver/test_omnigent.py:381`.** The unset HTTP client makes `_resend_allowed()` return False independently of status. Mutating `send` to permit retries for TIMEOUT, RUNNING, and STALLED still passes **all 73 driver tests; exit 0**. Supply retry-authorizing labels or a forbidden-label-read stub for each status.

2. **Prior objection 5 remains unresolved — `docs/roadmap/epics/E02-runtime-robustness.md:61`.** S02.3 remains annotated DONE, with change narration and duplicated budget/flaked policy. Remove the retired item; keep the contract in `docs/design/runner.md`. Also remove obsolete split-retry claims at epic `:18` and update deleted-helper references at epic `:104` and `docs/roadmap/current-state.md:95`.

Prior objections **1–4 verified fixed**. AC6a now rejects zero-poll execution; AC2 rejects premature label reads.

Suite: **298 passed, 1 skipped; exit 0**, using a temporary uv cache after default-cache access exited 2. Static contract checks and cancellation probes passed. No CI, gate-definition, or `.claude/` changes.

The single budget covers cooperative awaits. Cancellation cannot preempt synchronous JSON/text/event processing or stderr writes, stop the filesystem worker (`omnigent.py:306`), or kill the spawned tmux process (`:428`).
