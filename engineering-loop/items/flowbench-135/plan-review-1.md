reviewer: claude-code:subagent gate12-135 (Fable, fresh context, low effort; same vendor as implementer) — combined spec + plan review (S-sized post-mortem)

REVISE

1. Cause is right, but the cited fail-ask code is the wrong path and the direct evidence is missing. `hook.py:811` is the PermissionRequest retry loop; `_fail_closed` is `hook.py:1086` in `_main_evaluate_policy`; neither fired. The runner log has the smoking gun: `runner-070366e2…-20260910-061113-332201.log:546` `WARN 06:20:36.148 claude_native.bridge policy_eval_relay_failure: … hook_event=PreToolUse attempts=3 last_error='All connection attempts failed'; falling back to fail-closed` — the bridge relay (`bridge.py` ~5155, `fail_ask_hook_output`), 0.8 s after the old server shut down (06:20:35.406), 11 s before the new one listened (06:20:47.416). Everything else in decision #2 checks out.
2. Patch `b0674b43` can still restart under an active run: `busy()` counts any `status == "running"`; the stalled s131 session is still `running` with `updated_at` frozen at 06:20:51, so `busy()` would be permanently true and the 4 h override a daily restart-under-run. Fix: fresh `updated_at` only; state that the 4 h override is a deliberate restart-under-run.

Non-blocking: `runner.md` restates the mechanism instead of pointing; "re-synced at 06:19" is approximate (report 06:20:18).

Resolution: fork follow-up commit (busy() = `updated_at` < 600 s, any status; comments name the zombie case and the deliberate override); decisions #2/#4, spec, ledger corrected with the runner-log citation and bridge path; `runner.md` reduced to a pointer. The zombie session is left alive: `OmnigentDriver.close` leaves sessions alive by design (`just clean-tmux` reaps them), and the guard must be correct with them present.
