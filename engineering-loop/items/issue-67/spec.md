# flowbench #67 — driver: page past the item cap; wait out busy sub-agents; no nudges

## Problem (todo-app-004, superpowers, 3961 s, exit `timeout`; app complete at 30.7 min)

1. `OmnigentDriver._list_items` read one page (`limit=200`, no `after`). Past item #200 the
   assistant count seen by `_send_once`'s settle loop is frozen, so every later turn spins
   for the full `turn_timeout_s` and returns `timeout`. 004: item #200 = the loop's last send
   at 15.9 min; +3000 s = 66 min measured. 002 has the same signature (199 items, 12.1 min
   + 1800 s = 2531 s). `capture_session` was truncated by the same cap (#4).
2. `loop.py` nudged an idle agent whose sub-agent was busy with a literal `Continue.` and
   advanced the relay cursor only when `reply != _NUDGE`. When the *simulator* answered
   `Continue.` (every forced turn from 7.6 min on), the cursor froze and each relay resent
   the whole backlog (334 → 2782 chars, quadratic). Baseline never said `Continue.`.
3. The nudge model itself is wrong: omnigent wakes the parent with a task-notification when
   a child finishes. Nudging spent ~25 turns and ~50 items in 4 min, accelerating (1).

## Change (engine only, `src/flowbench/runner/`)

- `_list_items`: paginate with `after=page[-1]["id"]` until a short page. Serves the settle
  check and `capture_session`. Closes #4.
- `_snapshot`: when the session is `idle`, also read `GET /v1/sessions/{id}/child_sessions`
  and attach `busy_children` = `updated_at` of each child with `busy: true`.
- `_wait_idle`: `idle` + busy children counts as `running` for this turn; the children's
  `updated_at` join the heartbeat tuple, so a child frozen for `stall_s` is a
  `stalled/no_progress`. After children were seen, `idle` is returned only on the second
  consecutive quiet poll (the task-notification wake-up must not collide with our inject).
- `loop.py`: delete `_NUDGE`, `_MAX_CONSEC_NUDGES`, `_is_self_wait`; `sim_seen` advances on
  every relay. `TurnResult.child_busy` and `any_child_busy` deleted.
- `docs/design/runner.md` updated.

## Acceptance

- Unit: pagination follows `after` across 3 pages; idle+busy child waits and ends idle once
  children clear; frozen child → `stalled/no_progress`; snapshot attaches `busy_children`;
  relay never resends a line, even when the simulator replies `Continue.`.
- Live (`todo-app-005`, both flows, caffeinate, lid open): superpowers exits `idle` or by
  DONE — not `timeout`; zero `Continue.` user messages in its items; sim prompt size stays
  flat (no line relayed twice); `session.json` items count equals the server's full count.

## Behaviour change to note

A question the agent asks while its sub-agent is still busy now reaches the simulator only
after the child settles (the turn is not over). In 004 every question came with no child
busy; SDD dispatch-then-wait makes this the common shape.

## Addendum after live gate 1 (`todo-app-005`, flowbench #68 merged as d41cb1b)

- Baseline clean: acceptance 1.0, clarifying 1.0, 13 turns, 342 s, exit `idle`.
- Superpowers: exit `stalled/prompt` at 625 s, 25 turns, acceptance 0.0 (stalled mid-Task 2).
  Verified fixed from 004: zero `Continue.` nudges sent; simulator relay repeats 0 (was
  quadratic); child-busy wait held through Task 1's implementer.
- New failure: the last child cleared `busy`, the driver reported `idle` in the ~1–2 s before
  omnigent injected the child's task-notification, the simulator's reply queued behind that
  wake-up turn, and the watchdog read the queued input (`pending_inputs`) as a human prompt.
- omnigent's own docs (`runtime/pending_inputs.py`): `pending_inputs` = "un-consumed
  web-composer user messages" — OUR post before the transcript mirrors it. Never a prompt.
  #61's inclusion of it in `_PROMPT_KEYS` was wrong; removed.
- After busy children clear, `_wait_idle` reports `idle` only once a running turn has been
  observed again or `child_wake_s` (20 s) has passed. Follow-up PR; live gate `todo-app-006`.
