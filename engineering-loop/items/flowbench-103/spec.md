# Spec — flowbench #103 (E02 S02.3): one retry policy, at the driver

Size M. Engine worktree `/Users/zarz/dev/agents/flowbench--s023`, branch
`loop/issue-103-retry-policy`, base `origin/master` 883e0d0.

## Problem

Send/retry policy exists twice and the send has no single time ceiling.

1. **Two retry policies.** `OmnigentDriver.send` re-sends a `FAILED` turn only when the
   session labels confirm the inject never landed (`_injection_undelivered`). Simulator
   and judge sessions do not reliably set those labels, so `SessionModel.generate`
   (issue #39) layers a second policy on top: up to 3 sends per prompt, retrying a
   `FAILED` turn whose text is empty or equals the previous completion, trusting a
   `FAILED` turn whose text is fresh. `scripts/agent_review.py:verdict_from` re-derives
   the "trust the text of a failed turn" half of it on its own. Freshness is judged by string comparison
   against the previous completion, while the driver already knows the exact signal:
   the assistant-message count before the inject (`n_before` in `_send_once`).
2. **Nested budgets (audited bug).** `_send_once` spends up to `turn_timeout_s` in
   `_wait_idle`, then opens a settle window of another `turn_timeout_s` (when
   `settle_timeout_s` is None, which every production caller leaves it at) whose
   iterations call `_wait_idle` again, each with a fresh `turn_timeout_s`. `send`
   then repeats `_send_once` up to `send_retry_attempts` times with `send_retry_wait_s`
   sleeps between. Per `_send_once` that is ≤ 3 × `turn_timeout_s` (the settle window's
   last iteration may start a fresh `_wait_idle` just before the window closes), so one
   `send` is bounded by `(1 + send_retry_attempts) × 3 × turn_timeout_s +
   send_retry_attempts × send_retry_wait_s` = 2 970 s with the driver defaults (240 s,
   3, 30 s), assuming moving heartbeats, no stall and instantaneous server calls; a
   fake-clock trace of the current code under those assumptions reaches 2 930 s.
   todo_app configures `turn_timeout_s: 3000` inside a 3 600 s run `deadline_s`: the same
   bound is 36 090 s, so one send can outlive the run ten times over.

## Change

### Policy table (goes verbatim into `docs/design/runner.md`)

| Observation | Meaning | Action |
| --- | --- | --- |
| `FAILED` + label says undelivered | injection never landed | wait, re-send same text (bounded) |
| `FAILED` + new assistant text | turn completed, then flaked | trust the text, no retry |
| `FAILED`, no label, no new text | unknown; likely undelivered | bounded re-send (the #39 behavior, generalized) |
| `TIMEOUT` | may be mid-turn after delivery | NEVER retry (injecting into a busy terminal kills sessions) |
| `IDLE` + no new text past settle budget | lying idle | report `TIMEOUT` |

Precedence and definitions:

- "New assistant text" is checked first (row 2 before rows 1/3). A new assistant reply
  since the inject proves delivery regardless of the labels (`omnigent.last_task_error_*`
  is the *last* error on the session and may describe an earlier turn).
- "New assistant text" = a non-empty `item_text` among the assistant messages AFTER the
  first `n_before` of them (`n_before` = `n_assistant_messages` taken before the inject).
  New helper `transcript.new_assistant_text(items, n_before) -> str` returns the last
  such text or `""`. An empty new message is NOT new text (it would otherwise let
  `last_assistant_text` hand back an older reply as this turn's). The settle loop uses
  the same predicate, so a lying idle with an empty new message keeps settling.
- Rows 1 and 3 are the only re-send cases. `_injection_undelivered` becomes
  `_resend_allowed`: read the session labels; `True` when
  `omnigent.last_task_error_code` is absent (row 3) or is `runner_error` with "not
  delivered" in the message (row 1); `False` for any other present code (e.g.
  `model_error` — a delivered failure, re-sending could double-deliver) and `False`
  when the read itself fails (unknown ≠ "no label"; today's behaviour, kept).

### `send` owns the policy

- `_send_once(text, deadline)`: inject, `_wait_idle(deadline)`, settle. A `FAILED`
  status with new assistant text returns as `TurnResult(status=IDLE, flaked=True, ...)`
  (row 2) and prints one `[flowbench] turn flaked: server said failed after the reply
  landed; using the emitted text` line to stderr. Everything else is unchanged: `IDLE`
  with no new text settles until the deadline then becomes `TIMEOUT` (row 5);
  `RUNNING`/`STALLED`/undocumented statuses pass through.
- `send(text)`: computes `deadline = now + turn_timeout_s` ONCE, calls `_send_once`,
  and re-sends only when ALL of: the result is `FAILED` (after `_send_once`, that means
  "no new text"); `send_retry_attempts` re-sends have not been used; the remaining
  budget exceeds `send_retry_wait_s` (a re-send needs time to be waited for — the
  budget is re-checked immediately before every re-inject); `_resend_allowed()` is
  true. Between re-sends it sleeps `send_retry_wait_s`. `TIMEOUT`, `RUNNING`,
  `STALLED` and `IDLE` (flaked or not) return at once (row 4).
- `TurnResult` gains `flaked: bool = False`. `run_agent_session` records
  `session["flaked_turns"]` (count of turns with `flaked=True`) so a live run's
  `session.json` shows where the policy fired.

### One wall-clock budget per send

One `deadline = _now() + turn_timeout_s`, taken once at the top of `send`, and the
entire body of `send` — initial transcript read, inject, `_wait_idle`, settle polls,
`_resend_allowed`'s label read, retry sleeps, re-injects, final reads — runs inside
`async with asyncio.timeout(self.turn_timeout_s)`. Nothing in a send runs past
`turn_timeout_s` of wall clock. There is no second budget and no allowance.

- **Soft checks pre-empt waits so the common case ends with an honest status.**
  `_wait_idle(deadline, min_wait=4.0)` polls `while _now() < deadline`; the settle loop
  polls `while … and _now() < deadline`; a re-send is attempted only when `deadline -
  _now() > send_retry_wait_s` before the sleep; `_send_once` checks `_now() < deadline`
  immediately before EVERY inject (the first one included, after its `n_before` read)
  and returns `TurnResult(TurnStatus.TIMEOUT, "", artifact_exists)` without injecting
  when the budget is already gone. `stall_s`, `child_wake_s`, `min_wait`,
  `settle_poll_s` are unchanged. `settle_timeout_s` is removed (its `None` default meant
  "the turn budget", which is now the only budget).
- **The hard ceiling is the same number, enforced by cancellation.** When the timer
  fires, whatever is in flight (a status read, an item page, `_read_retry`'s back-off,
  `_pane_tail`, the label read, a retry sleep, the inject envelope) is cancelled and
  `send` returns `TurnResult(TurnStatus.TIMEOUT, "", artifact_exists)`. Cancelling is
  safe: every awaited operation is an idempotent read or a sleep, except the inject
  envelope — and a cancelled inject is exactly the unknown-delivery state `TIMEOUT`
  names (row 4: never re-sent). For a flow (SUT) send, `TIMEOUT` stops the loop and the
  flow's `capture_session` reads the full transcript, so the empty `assistant_text`
  costs nothing there. For a simulator/judge send, `SessionModel.generate` raises
  `RuntimeError` on `TIMEOUT` exactly as it does today; `run_case` handles that
  exception as it does today (a raising simulator skips the flow's capture — unchanged
  behaviour, not a property of this change).
- **Filesystem work is under the timer too.** `artifact_path()` (an `exists()` plus an
  `rglob` over the run dir) is the only synchronous work in a send. `_send_once` calls it
  as `await asyncio.to_thread(self.artifact_path)`, so a slow filesystem cannot hold the
  send past the ceiling (the worker thread finishes on its own; the send does not wait
  for it). The expiry result is `TurnResult(TIMEOUT, "", artifact_exists=False)` —
  nothing is read at expiry; `artifact_exists` on a `TIMEOUT` means "not observed", and
  no consumer reads `TurnResult.artifact_exists` (`grep` in `src/` and `scenarios/`: the
  loop and `run_case` read the artifact through `driver.artifact_path()` /
  `capture_session`). The public sync `artifact_path()` is unchanged (S02.4 owns the
  artifact concern).
- **At the cap, the status is whichever layer got there first.** A turn still running
  when the soft loop's last poll finishes reports `RUNNING` (or an undocumented server
  status verbatim, as today); if the cap falls inside a server call instead, the hard
  ceiling reports `TIMEOUT`. Both mean "the turn did not finish inside the budget";
  the distinction is diagnostic and S02.6's to sharpen.

The clock the soft checks read is a module-level `_now = time.monotonic`, so the
soft-deadline tests drive a fake clock deterministically (asyncio's own use of
`time.monotonic` must not be patched; under a fake clock the real-time hard ceiling
never fires, which is what makes those tests deterministic). The hard ceiling's tests
use hanging or slow operations under a real `turn_timeout_s` of 0.1 s.

### `SessionModel.generate` shrinks

Send; raise `RuntimeError` when `status != IDLE` or `assistant_text` is empty after
`strip()`; return the completion. `GENERATE_ATTEMPTS`, `GENERATE_RETRY_WAIT_S`,
`_fresh`, `_last_text` are deleted. Its tests move to the driver (rows 1–3) or shrink
with it. The empty-text raise is NEW: today `generate` returns an `IDLE` turn's text
even when it is empty or whitespace. The epic's "raise on `TIMEOUT`/no-text" makes an
empty completion an error (an `IDLE` from the driver always carries new non-empty text
by construction, so this fires only if that invariant breaks).

### Docs

- `docs/design/runner.md`: the policy table verbatim + the one-budget rule (new
  subsection under `flowbench/driver/`), `model.py` row loses "freshness-retry policy",
  `TIMEOUT` row says "the send's budget expired".
- `docs/roadmap/epics/E02-runtime-robustness.md` §S02.3: not edited (done-state lives
  on the board, flowbench #122).
- Driver field comments updated where they describe the removed behaviour.

## Out of scope (S02.4–S02.6)

Artifact concern, omnigent public-API migration, error taxonomy. No change to
`_wait_idle`'s stall/child/wake-up logic beyond taking the deadline. No change to
`scripts/agent_review.py` (its `verdict_from` keeps working: a flaked turn now arrives
as `IDLE`).

## Acceptance criteria (checkable from the diff and tests)

- AC1 `_resend_allowed` returns True for an absent error code and for
  `runner_error` + "not delivered"; False for `model_error` and when the label read
  raises. `_injection_undelivered` does not exist in `src/`.
- AC2 Row 2: a `FAILED` server status with `new_assistant_text(items, n_before)`
  non-empty yields `TurnResult(status=TurnStatus.IDLE, flaked=True)` from a single
  `_send_once` — test asserts exactly one inject and no label read. Counter-cases,
  each ending as a re-send candidate (`FAILED`), not a flaked idle: (a) the only new
  assistant message is empty/whitespace while an older non-empty reply exists; (b) no
  new message at all. Positive case: a new reply identical to the previous turn's text
  IS new text (count-based, not equality-based).
- AC3 Rows 1/3: a `FAILED` status with no new assistant text and `_resend_allowed()`
  true re-sends the same text after `send_retry_wait_s`, at most `send_retry_attempts`
  times, and returns `FAILED` when exhausted — test asserts the sent-text list and the
  count. With `_resend_allowed()` false (a `model_error` label) the first `FAILED`
  returns at once.
- AC4 Row 4: `TIMEOUT`, `RUNNING` and `STALLED` results return from `send` after one
  `_send_once` (no retry), test per status.
- AC5 Row 5: `IDLE` with no new text past the deadline returns `TIMEOUT` (existing
  test `test_send_settle_expiry_is_a_timeout_not_a_stale_idle`, kept, driven by
  `turn_timeout_s`).
- AC6 One budget. Soft deadline, fake clock (each poll's sleep advances it): (a) `turn_timeout_s =
  100`; the session is `RUNNING` with a moving heartbeat for ~60 s of clock, then `IDLE`
  with no new text, then `RUNNING` forever. Assert the send returns `RUNNING` with
  `clock ≤ 100 + settle_poll_s + 1.5` (one settle poll + one status poll of slop). The
  pre-S02.3 code returns at ≈ 60 + 100 here (its second `_wait_idle` gets a fresh
  `turn_timeout_s`). (b) `turn_timeout_s = 50`, `send_retry_wait_s = 30`,
  `send_retry_attempts = 3`, `_send_once` stubbed to return `FAILED("")` in zero clock
  time, `_resend_allowed` stubbed True: exactly 2 sends (after the first, 50 > 30 → wait
  → 20 left, 20 ≤ 30 → stop). (c) same with `turn_timeout_s = 10`: exactly 1 send.
  Hard ceiling, real clock and real sleeps, `turn_timeout_s = 0.1` unless stated, the
  REAL `_send_once`/`_wait_idle`, injects counted at the fake chat's `send`; each asserts
  `send` returns `TurnResult(TIMEOUT, "", False)` in < 2 s wall clock:
  (d) `_snapshot` awaits forever — 1 inject;
  (e) the INITIAL `n_before` `_list_items` hangs — 0 injects;
  (e') [fake clock, real `_send_once`] the initial read completes but its fake
  `list_items` advances the fake clock by `turn_timeout_s + 1` before returning `[]` —
  0 injects, result `TIMEOUT`: the pre-inject check fires (the real-time timer cannot,
  under a fake clock);
  (f) the post-wait `_list_items` hangs — 1 inject;
  (f') delayed pagination: the post-wait read returns a full 200-item first page, then
  hangs on the second page — 1 inject;
  (g) `_read_retry`'s back-off: `_snapshot` always raises `httpx.ReadError` so the
  back-off sleeps 2 s, 4 s, … — 1 inject;
  (h) a `FAILED` first turn whose `_resend_allowed` label read hangs — 1 inject;
  (i) an eligible retry sleep that overshoots: `turn_timeout_s = 0.3`,
  `send_retry_wait_s = 0.1`, `_FakeChat([FAILED])`, `_resend_allowed` True, and the
  driver module's `asyncio.sleep` patched to sleep `s + 1.0` real seconds — the sleep was
  eligible (0.3 > 0.1) yet the timer cancels it: 1 inject, `TIMEOUT`, no re-inject;
  (i') an eligible re-send whose second wait hangs: `turn_timeout_s = 0.6`,
  `send_retry_wait_s = 0.1`, snapshot reports `FAILED` once then hangs, `_resend_allowed`
  True — 2 injects, `TIMEOUT`;
  (k) slow filesystem: `d.artifact_path` patched to a function that `time.sleep(1.0)`s
  (synchronous) then returns `None`, `_FakeChat([RUNNING, IDLE])` with the reply landing
  — `send` returns `TurnResult(TIMEOUT, "", False)` in < 2 s and the thread's result is
  discarded;
  Soft, fake clock, real `_send_once`: (j) `_FakeChat([FAILED])`, `_resend_allowed`
  True, `turn_timeout_s = 31`, `send_retry_wait_s = 30`, the fake sleep advancing
  `s + 1` → after the sleep `_now() >= deadline`, the second `_send_once` returns
  `TIMEOUT` before injecting — exactly 1 inject counted at the fake chat.
- AC7 `settle_timeout_s` and `overrun_s` do not appear in `src/`, `tests/` or `docs/`;
  `asyncio.timeout(` appears exactly once in `omnigent.py`, in `send`.
- AC8 `SessionModel.generate` has no loop and no sleep: `IDLE` → completion (flaked
  or not); any other status → `RuntimeError`; `IDLE` with `""` and `IDLE` with `"  \n"`
  → `RuntimeError` (two explicit cases); exactly one `send` per `generate` in every
  test. `GENERATE_ATTEMPTS`/`GENERATE_RETRY_WAIT_S`/`_fresh`/
  `_last_text` do not appear in `src/` or `tests/`.
- AC9 `run_agent_session` continues past a flaked idle turn and writes
  `session["flaked_turns"]` (test: two idle turns, one flaked → `flaked_turns == 1`,
  `exit_status == idle`).
- AC10 `docs/design/runner.md` contains the five-row table byte-identical to the one
  above (`diff <(sed -n '/^| Observation/,/^$/p' spec.md) <(same on runner.md)` is
  empty) and the string `settle_timeout_s` appears nowhere in `docs/` or `src/`.
- AC11 V1 green; V2 green in the scenarios worktree with `flowbench.__file__` under
  the engine worktree; V8 diff-cover 100 % on changed lines.
- AC12 Live (mandatory, both on the merged SHA, `caffeinate -i`):
  - V5 todo_app: both flow dirs hold `scorecard.json` with no `error` key;
    `flowbench compare` renders both columns with no FAILED banner; both
    `session.json` have `exit_status == "idle"` and `stall_reason` absent;
    `flaked_turns` values reported in `gates.md`.
  - V4 swe_planning `--n 1`: watcher exits on `run.json`, no failed sessions, `winner`
    parsed (not `unknown`), every flow dir holds `plan.md` + `transcript.md` +
    `session.json`, all `exit_status == "idle"`.
