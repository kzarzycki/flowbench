reviewer: claude-code:subagent gate12-135 (Fable, fresh context, low effort; same vendor as implementer) — combined spec + plan re-review

APPROVE

Verified: decisions #2 cites runner log line 546 (06:20:36.148, `policy_eval_relay_failure … falling back to fail-closed`) and `bridge.py` `fail_ask_hook_output`; shutdown 06:20:35.406 / new listener 06:20:47.416 match the server logs. Fork `889a60b3` drops the `status == "running"` clause; reviewer ran `busy()`: live rc 0 (mid-turn session heartbeats `updated_at`), `PORT=1` rc 1. Zombie no longer pins the guard; 4 h override stated as deliberate in script, decisions #4, ledger. `runner.md` is a pointer only; diff touches `docs/` only.

Non-blocking, folded in: onboarding.md/AC1 quiet condition reworded to "no session touched in the last 10 min" (status ignored); spec Fix #1 and decisions #4 name `889a60b3`.
