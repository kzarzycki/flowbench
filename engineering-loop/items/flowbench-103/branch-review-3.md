REVISE

1. **Retired S02.3 material remains.** `docs/roadmap/epics/E02-runtime-robustness.md:58` retains the item with a “Contract” annotation instead of removing it. `docs/roadmap/current-state.md:118` still lists nested budgets as an active bug; `:132` says retry exhaustion is untested. `docs/roadmap/epics/E00-guardrails.md:57` still describes fresh-text handling as awaiting migration. Remove the retired material and stale claims.

2. **Policy ownership is duplicated.** `docs/roadmap/current-state.md:23` repeats “retry policy is the driver's,” already owned by `docs/design/runner.md:64`. Keep the inventory entry focused on the module’s role.

3. **Cancellation documentation overclaims.** `docs/design/runner.md:90` says the synchronous filesystem operation “is cancelled.” Only its await is cancelled; the worker continues. State that distinction.

Prior runtime/test objections verified fixed. Mutation checks reject unsafe status retries, zero-poll budget execution, and unchecked HTTP errors; each exited 1 as expected. Suite: **298 passed, 1 skipped; exit 0**. Static checks and corrected cancellation probes exited 0. No CI, gate-definition, or `.claude/` changes.

The single timeout covers cooperative awaits. It cannot preempt synchronous imports, JSON/text/event processing or stderr writes, stop the filesystem worker (`omnigent.py:306`), or terminate the spawned tmux process (`:428`). External cancellation during injection propagates correctly.
