# Spec — flowbench #135: superpowers stalled on a permission card despite bypassPermissions

## Problem
In `s131-f8d39b6` the superpowers flow's `Write` raised a Claude Code permission card under
`--permission-mode bypassPermissions`; the watchdog ended the turn `STALLED (prompt)`.

## Cause (decisions #1–#3)
A server restart 24 s before the stall, triggered by the omnigent fork's `auto-sync` launchd
job whose "agent active" guard keyed on a log directory that no longer receives logs. With the
server unreachable, the bridge's `PreToolUse` policy relay fails *ask* by design (runner log
`policy_eval_relay_failure … falling back to fail-closed`, 06:20:36), and a hook's *ask*
outranks the permission mode.

## Fix
1. Omnigent fork (`mine`, `b0674b43` + `889a60b3`): the guard asks the server for active sessions and a
   sync that applied under activity defers its restart to the first quiet tick.
2. flowbench (docs only): `docs/onboarding.md` gets a fifth live-run rule, "No server restart
   under a run", with the signature and the quiet condition; `docs/design/runner.md`'s
   `stalled` paragraph gains one sentence pointing at it.

## Acceptance criteria
- AC1 `docs/onboarding.md` states the rule once (signature: prompt card under
  bypassPermissions; cause: hook fail-ask on an unreachable server; condition: no session
  touched < 10 min) and `docs/design/runner.md` links to it without restating it.
- AC2 No engine code changes (diff touches `docs/` only).
- AC3 Fork guard: with the live server showing a session touched < 10 min, `defer_or_go` returns 1
  and writes a `deferred` tick; a `running` session with a stale `updated_at` does not count;
  with the server down, `busy` returns 1 and `defer_or_go` returns 0.
- V Live: `coding_workflow/s135-repro-1` on `f8d39b6` — superpowers exits `idle`, no
  `STALLED (prompt)`, watcher clean.
