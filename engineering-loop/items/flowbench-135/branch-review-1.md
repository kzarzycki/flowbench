reviewer: claude-code:subagent gate3-135 (Fable, fresh context, low effort; same vendor as implementer)

APPROVE

Verified: diff docs-only (AC2), onboarding states the rule once with the 10-min quiet condition (AC1), runner.md points only. Facts match decisions.md and `bridge.py:5148-5155` (`fail_ask_hook_output`); `GET /v1/sessions` `updated_at` is epoch seconds and heartbeats mid-turn; label filter `omni_project` matches `session_seed.py:19`. Fork script `bash -n` clean; no `set -e`; `restart-pending` cannot double-fire or orphan.

Non-blocking, folded in: `limit=1000` (API sorts by created_at, an old long-lived session was missed at 100) → fork `1c40c82c`; onboarding wrapped mid-backtick → fixed. Noted, not changed: one `first-try` stamp shared by sync and restart deferrals (acceptable under the deliberate 4 h rule); audit sub-agent sessions lack the label so restarts take the pending path (correct, just later).
