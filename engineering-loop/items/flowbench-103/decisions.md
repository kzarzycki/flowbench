# Decisions — flowbench #103

1. **Rows 1 and 3 are the only re-send cases; a present label naming another error is
   neither.** `_injection_undelivered` is renamed `_resend_allowed` and gains the
   "no label at all" case (row 3, the #39 behaviour generalized to every session). A
   `model_error` (or any other present code) stays non-retryable, as today: the table
   does not list it, and re-sending a delivered failure can double-deliver. An
   unreadable label read stays "no" (today's behaviour; unknown is not "no label").
2. **"New assistant text" beats the label** (row 2 before row 1). `omnigent.last_task_
   error_message` is the *last* error on the session, so it can describe an earlier
   turn. A new assistant message since our inject is direct evidence of delivery;
   re-sending on top of it would double-deliver — the failure mode the whole retry
   design avoids. Source: driver comments ("Undelivered means retrying is
   double-delivery-safe") + `_send_once` already taking `n_before`.
3. **Freshness = a non-empty message beyond the pre-send count, not text equality.**
   `SessionModel._fresh` compared strings against the previous completion, so a repeated
   identical answer read as stale. Counting alone is not enough either:
   `n_assistant_messages` counts empty messages while `last_assistant_text` skips them,
   so an empty new message would let an older reply pass as this turn's. Hence
   `new_assistant_text(items, n_before)`: the last non-empty text among the messages
   after the first `n_before`. Source: the epic ("vs. the pre-send count, which
   `_send_once` already tracks") + `transcript.py` semantics.
4. **Success-with-flag = `status=IDLE`, `flaked=True`.** The loop's contract is "only
   `IDLE` continues"; a delivered-then-flaked turn IS a completed turn, so `IDLE` is the
   truthful status and the flag carries the diagnostic. Keeping `FAILED` plus a flag
   would make every caller re-derive `status == IDLE or flaked`, the duplication the
   story removes. Server-status preservation in a typed form is S02.6's job.
5. **`flaked_turns` in `session.json`, one stderr line in the driver.** The stderr
   print is `SessionModel`'s existing diagnostic moved to where the decision is made;
   the count exists so the live gate and post-mortems can see the policy fire without
   a log. Two lines in `loop.py`.
6. **`settle_timeout_s` removed rather than kept as a sub-budget.** Every production
   caller left it `None` (= "the turn budget"); one budget per send is the story's
   rule, and a second knob would reintroduce the nesting.
7. **Re-send only when the remaining budget exceeds `send_retry_wait_s`.** Otherwise
   the driver would inject and have no time left to wait — an inject nobody observes,
   i.e. exactly the "inject into a session whose state we don't know" case the table
   forbids. Simpler alternatives (re-send whenever any budget remains) were rejected for
   that reason.
8. **`_now = time.monotonic` module indirection.** The one-budget assertion is about
   elapsed clock time; asserting it against the real clock is either slow or flaky.
   Patching `time.monotonic` itself would break asyncio's event loop. One line.
9. **`send_retry_attempts` keeps its meaning (number of re-sends after the first).**
   Default 3 → at most 4 injects per send, as today; the budget now bounds it further.
10. **Epic doc not ticked.** flowbench #122: done-state lives on the Project board.
11. **`scripts/agent_review.py` untouched.** `verdict_from` trusts text whenever there
    is one and warns on non-idle; after this change a flaked turn arrives as `IDLE` and
    the warning simply stops firing for that case. Its TUI-harness policy (trust text on
    `running`/`timeout`) is its own and out of scope.
12. **Live gate shape (validation choice, not a filed requirement).** The epic makes V4
    mandatory for this story; `verification.md` V4 is the swe_planning run and V5 the
    todo_app run. Both are run because the change touches two distinct live paths: the
    SUT loop (todo_app exercises `flaked_turns`/long turns under a 3000 s cap) and the
    simulator+judge path through `SessionModel` (swe_planning's judge is a one-shot
    `generate`). `--n 1` for swe_planning: one trial exercises every code path the change
    touches; position-bias cancelling (`--n 2`) is a benchmark concern, not a gate one.
    Both on the merged SHA (ledger rule: a live gate is only valid against the master it
    ran on).
13. **One `asyncio.timeout(turn_timeout_s)` around all of `send`; no allowance.** An
    earlier draft added a constant `overrun_s` past the deadline to avoid a race between
    the soft loop's honest `RUNNING`-at-cap exit and the timer; the gate rejected it as a
    second budget the story does not grant, and that is right: the story's rule is one
    ceiling. The race is accepted instead and documented (at the cap: `RUNNING` if the
    soft loop got there first, `TIMEOUT` if a server call straddled it — both "did not
    finish", S02.6 sharpens the taxonomy). Cancellation is safe because everything
    awaited is an idempotent read or a sleep, and a cancelled inject is the state
    `TIMEOUT` already names.
15. **`artifact_path()` under the timer via `asyncio.to_thread`.** The one synchronous
    call in a send; the gate showed a slow filesystem holds a send past the ceiling.
    `to_thread` is one line and keeps the public sync method (S02.4's concern) intact.
    At expiry nothing is read: `artifact_exists=False` = "not observed", and no consumer
    reads that field off a `TurnResult`.
14. **Worst-case figure.** Stated as a derived bound with its assumptions (moving
    heartbeat, no stall, instant server calls) next to a measured fake-clock trace, not
    as a bare number.
