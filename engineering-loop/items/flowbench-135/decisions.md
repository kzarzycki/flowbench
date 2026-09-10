# Decisions — flowbench #135 (permission card under bypassPermissions)

1. **Both hypotheses on the issue are rejected by evidence, not argument.** (a) Bridge dropping
   the flag: `terminal_launch_args` on the stalled session and the live `claude` argv (`ps`)
   both carry `--permission-mode bypassPermissions --setting-sources ""` and the bridge's
   `--settings` file sets `permissions.defaultMode: bypassPermissions` — identical to the clean
   `s024-1925` session. (b) Claude Code 2.1.266 → 2.1.267 (updated 2026-09-09 23:36, between the
   two runs): the changelog for 2.1.260–2.1.267 has no permission-mode or Write change, and the
   prompt has a sufficient cause elsewhere.
2. **The cause is a server restart mid-turn.** `~/.local/bin/omnigent server` (pid 17594)
   started 06:20:35; the stall fired 06:20:59. The restart came from the
   `dev.zarz.omnigent-autosync` launchd job (`~/.omnigent/logs/auto-sync/20260910-061655.log`:
   rebase onto upstream `e8a5ba96`, editable install re-synced to 0.14.0.dev0, report written
   06:20:18, "restarting server to load backend"). The bridge relays every `PreToolUse` policy
   evaluation to the server; with the old server gone (shutdown 06:20:35.406) and the new one
   not yet listening (06:20:47.416) the relay gave up and failed *ask* — the smoking gun is the
   runner log `~/.omnigent/logs/runner/runner-070366e24d06465daf0cb924c105048b-20260910-061113-332201.log:546`:
   `WARN 06:20:36.148 claude_native.bridge policy_eval_relay_failure: … hook_event=PreToolUse
   attempts=3 last_error='All connection attempts failed'; falling back to fail-closed`
   (`bridge.py` ~5148–5155, `fail_ask_hook_output` → `permissionDecision: "ask"`; the
   out-of-process `hook.py` `_fail_closed` path is the fallback, not what fired). Claude Code
   honours a hook's *ask* over `bypassPermissions` — hence `Do you want to create
   2026-09-10-todo-cli.md?`.
3. **Why the auto-sync did not defer.** Its "agent active" guard looked for
   `~/.omnigent/logs/host-runner/*.log` modified in the last 10 min; that directory has been
   empty since 2026-08-19 (runner logs moved), so the guard never fired.
4. **Root fix lives in the omnigent fork, not flowbench** (owner's choice, 2026-09-10): the guard
   asks the server (`GET /v1/sessions`: any session touched < 10 min, audit session excluded)
   and a sync that applied under active sessions leaves its restart to the first quiet tick
   (`restart-pending`). Status is deliberately NOT the signal: the driver leaves sessions alive
   after a run by design (`OmnigentDriver.close`), and one parked on a permission card — the
   s131 session, still `running` with `updated_at` frozen at 06:20:51 — would keep the guard busy
   forever. The 4 h starve rule stays and is a deliberate restart-under-whatever-is-active, so
   the daily sync cannot be held hostage. Commits `b0674b43` + `889a60b3` on `mine`, pushed.
   `bundle.py`, launch args and the settings shape are correct as they are — no engine change.
5. **flowbench records the signature once, in the operator doc** (`docs/onboarding.md`, fifth
   rule) and points to it from the `stalled` paragraph in `runner.md`. No new watcher line: the
   existing `STALLED (prompt)` + `pane_tail` already showed the card.
6. **Live gate = the repro run.** `s135-repro-1` runs on the same engine (`f8d39b6`) and the
   same omnigent build with no restart in its window; a clean superpowers exit (idle, no
   `STALLED (prompt)`) is the evidence that the prompt needs the restart. The guard itself is
   checked function-level (deferral with the live run active; quiet with the server down).
