# Stall watchdog — flowbench#54

Owner constraint (2026-09-08): the benchmark must never lock on a question to
a user; we must be able to monitor its situation and react promptly.

## Problem

todo-app-001: an unallowlisted Bash call raised a permission prompt in each
flow. Nobody could answer it (AskUserQuestion disabled, the simulator sees
chat only). Each turn sat `running` until the 3000 s cap; the run finished
"normally" with `exit_status=running`. Cost: ~1 h and a useless scorecard.

flowbench#52 (bypassPermissions) removes that prompt. The class remains:
trust dialog, login, plan-mode approval, an omnigent policy ASK, a hung tool.

## Scope

Engine only (`flowbench`). Three pieces, one PR.

1. **Detect** (`OmnigentDriver._wait_idle`). Poll already runs every 1.5 s.
   Add a stall check while status is `running`:
   - `pending_elicitations_count > 0` on the session → stalled at once
     (`stall_reason="elicitation"`). This is how a Claude permission hook or
     policy ASK shows up in omnigent.
   - else no new item and `updated_at` unchanged for `stall_s` (default
     300 s, `Flow`/driver kwarg) → stalled (`stall_reason="no_progress"`).
   On stall: read the terminal resource (`GET /v1/sessions/{id}/resources`
   → `tmux_socket`/`tmux_target`), `tmux capture-pane -p` last 40 lines,
   best effort (missing tmux → `None`). Return status `stalled`.
2. **Record**. `TurnResult.status` gains `stalled`; `_send_once` attaches
   `stall_reason` + `pane_tail`. `run_agent_session` stops as for
   `timeout`; `session.json` gets `exit_status=stalled`, `stall_reason`,
   `pane_tail`. Scoring is unchanged: whatever was built is scored.
3. **Surface** (`flowbench.watch.RunWatch.tick`). Per run session each
   tick: `STALLED (elicitation): <title> <id>` when
   `pending_elicitations_count > 0`; `STALLED (no progress Ns): …` when
   `updated_at` is older than `stall_s` while status is `running`. Once per
   transition, like `SESSION FAILED`.

## Not in scope (stated once)

- **Auto-answering prompts.** A benchmark that resolves its own elicitations
  measures the harness, not the flow. Hard stop, record, score.
- Retrying the turn after a stall. Same reason; also non-deterministic.
- Watching non-run sessions.

## Acceptance

- AC1 offline test: fake chat that stays `running` with
  `pending_elicitations_count=1` → `send()` returns `stalled` within one
  poll; `stall_reason=="elicitation"`.
- AC2 offline test: fake chat `running`, items/`updated_at` frozen, `stall_s=0.1`
  → `stalled`/`no_progress`; with items growing → keeps waiting to timeout.
- AC3 `run_agent_session` on a `stalled` first turn: `exit_status=="stalled"`,
  `stall_reason` and `pane_tail` keys present (pane may be `None`).
- AC4 `RunWatch.tick` emits `STALLED (elicitation)` once for a session whose
  count flips 0→1, and nothing on the next tick if unchanged.
- AC5 `docs/design/runner.md`: one paragraph on turn statuses incl. `stalled`.
- AC6 100% diff coverage (CI), `uv run pytest -q` green.
- AC7 live: `todo-app-002` runs to completion with no `STALLED` event; the
  watcher output is in the journal.

## Size

~80 lines src, ~100 lines tests, 1 doc paragraph.

## Addendum — flowbench#61 (same item, widened after review)

The raw session also carries `pending_inputs` and `terminal_pending`; a trust
dialog or login lands there, not in `pending_elicitations`. The instant arm
fires on any of the three, but only when seen on two consecutive polls:
`pending_inputs` flickers for one poll on healthy turns (in-flight delivery).
The reason is `prompt` (was `elicitation`).
