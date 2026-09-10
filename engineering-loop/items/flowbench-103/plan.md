# Plan — flowbench #103 (E02 S02.3)

Engine worktree `/Users/zarz/dev/agents/flowbench--s023`, branch
`loop/issue-103-retry-policy`. Every task: TDD (failing test → code → green), then
`uv run pytest -q` green and `uv run ruff check . && uv run ruff format --check .`
clean before the commit. Commit per task.

## Paths (every task uses these; initialise them in each shell)

```bash
ENG=/Users/zarz/dev/agents/flowbench--s023                       # engine worktree, branch loop/issue-103-retry-policy
SCEN=/Users/zarz/dev/xebia/flowbench-scenarios--s023             # scenarios worktree, same branch name
SCEN_ITEM=$SCEN/.claude/engineering-loop/items/flowbench-103
RUNS=/Users/zarz/dev/xebia/flowbench-runs                        # run dirs (never inside a repo)
ISSUE=https://github.com/kzarzycki/flowbench/issues/103
```
`scenarios.coding_workflow` (todo_app) lives in the ENGINE repo; `scenarios.swe_planning`
lives in the scenarios repo. Loop artifacts under `$SCEN/.claude/` need `git add -f` (the
shared checkout's `.git/info/exclude` ignores `.claude/`).

## Global constraints (from spec)

- The five-row policy table lands verbatim in `docs/design/runner.md`.
- One wall-clock budget per `send`: `deadline = _now() + turn_timeout_s`, computed once
  in `send`; `_wait_idle` and the settle loop poll against that deadline; a re-send
  happens only when `deadline - _now() > send_retry_wait_s`.
- `settle_timeout_s`, `_injection_undelivered`, `GENERATE_ATTEMPTS`,
  `GENERATE_RETRY_WAIT_S`, `SessionModel._fresh`, `SessionModel._last_text` are removed.
- "New assistant text" = `transcript.new_assistant_text(items, n_before)` non-empty; it
  is the settle predicate AND the row-2 predicate.
- Re-send iff `FAILED` ∧ attempts left ∧ `deadline - _now() > send_retry_wait_s` ∧
  `await self._resend_allowed()`, and `_now() < deadline` right after the sleep.
- Hard ceiling: the whole body of `send` runs under `async with
  asyncio.timeout(self.turn_timeout_s)`; expiry → `TurnResult(TurnStatus.TIMEOUT, "",
  False)` — nothing is read at expiry. No other budget field exists.
- `_send_once` checks `_now() < deadline` immediately before its inject (after the
  `n_before` read) and returns the same `TIMEOUT` result without injecting otherwise.

## Task 1 — `TurnResult.flaked` + the driver's one budget and policy

Files: `src/flowbench/types.py`, `src/flowbench/transcript.py`,
`src/flowbench/driver/omnigent.py`, `tests/test_transcript.py`,
`tests/driver/test_omnigent.py`.

0. `transcript.py`: add after `n_assistant_messages`:
   ```python
   def new_assistant_text(items: list[dict], n_before: int) -> str:
       """Text of the last NON-EMPTY assistant message beyond the first `n_before`
       assistant messages — i.e. a reply that landed after the inject `n_before` was
       taken for. "" when none did. An empty new message is not a reply: without
       this rule `last_assistant_text` would hand back an OLDER reply as this turn's."""
       msgs = [it for it in items if isinstance(it, dict) and it.get("type") == "message"
               and it.get("role") == "assistant"]
       return last_assistant_text(msgs[n_before:])
   ```
   Tests in `tests/test_transcript.py`: no new message → ""; new empty message + old
   non-empty → ""; new non-empty identical to the old text → that text; two new, last
   empty → the earlier new one's text.

1. `types.py`: add `flaked: bool = False` after `pane_tail` with the comment
   `# server reported failed AFTER a new reply landed; text trusted, status IDLE (S02.3)`.
   Update the `TIMEOUT` member comment to `# derived: idle but silent, or the send's
   budget expired`.
2. `omnigent.py`:
   - module level, after `_PAGE`: `_now = time.monotonic  # clock seam: the budget tests
     drive a fake one; never patch time.monotonic itself (asyncio uses it)`.
   - delete the `settle_timeout_s` field and its comment block; rewrite the
     `send_retry_*` comment to describe rows 1/3 (FAILED with no new assistant message
     → wait `send_retry_wait_s`, re-send the same text, at most `send_retry_attempts`
     times, only while the budget covers the wait).
   - `send(self, text)`:
     ```python
     async def send(self, text: str) -> TurnResult:
         # ONE wall-clock budget per send: the soft checks below pre-empt every wait
         # against `deadline`; the timer cancels whatever server call, back-off or
         # retry sleep is still in flight when the same instant passes. A cancelled
         # inject is the unknown-delivery state TIMEOUT names — never re-sent.
         deadline = _now() + self.turn_timeout_s
         try:
             async with asyncio.timeout(self.turn_timeout_s):
                 result = await self._send_once(text, deadline)
                 for _ in range(self.send_retry_attempts):
                     if (
                         result.status != TurnStatus.FAILED  # rows 2, 4, 5: never re-sent
                         or deadline - _now() <= self.send_retry_wait_s  # no budget to wait for it
                         or not await self._resend_allowed()
                     ):
                         return result
                     # rows 1/3: failed and no new text — the inject (likely) never landed
                     await asyncio.sleep(self.send_retry_wait_s)
                     result = await self._send_once(text, deadline)
                 return result
         except TimeoutError:
             return self._timed_out()

     def _timed_out(self) -> TurnResult:
         # nothing is read at expiry; artifact_exists=False means "not observed"
         return TurnResult(TurnStatus.TIMEOUT, "", False)
     ```
     and `_send_once` builds its result with
     `artifact_exists=(await asyncio.to_thread(self.artifact_path)) is not None`
     (the one synchronous call in a send, moved off the loop so the timer covers it).
     and in `_send_once`, right after `n_before = …` and `self._stall = None`:
     `if _now() >= deadline: return self._timed_out()  # budget gone before the inject`.
     (`asyncio.timeout` raises the builtin `TimeoutError` on 3.11+.)
   - rename `_injection_undelivered` → `_resend_allowed`, body:
     ```python
     try: labels = (await self._http.get(f"/v1/sessions/{self._chat.session_id}")).json().get("labels") or {}
     except Exception: return False  # unknown is not "no label"
     code = labels.get("omnigent.last_task_error_code")
     if not code: return True  # row 3: sim/judge sessions set no labels (#39)
     return code == "runner_error" and "not delivered" in labels.get("omnigent.last_task_error_message", "")  # row 1
     ```
     (formatted over several lines; docstring names rows 1/3 and the model_error case).
   - `_send_once(self, text, deadline)`: `status = await self._wait_idle(deadline)`;
     settle loop condition becomes `status == IDLE and not new_assistant_text(items,
     n_before) and _now() < deadline` (drop the `settle =` computation); inner
     `self._wait_idle(deadline)`; the post-loop `TIMEOUT` check uses the same predicate;
     then:
     ```python
     flaked = False
     if status == TurnStatus.FAILED and new_assistant_text(items, n_before):
         # row 2: the reply landed, then the server flaked — a completed turn
         status, flaked = TurnStatus.IDLE, True
         print("[flowbench] turn flaked: server said failed after the reply landed; "
               "using the emitted text", file=sys.stderr)
     ```
     and pass `flaked=flaked` into `TurnResult`. `import sys` at the top.
   - `_wait_idle(self, deadline, min_wait=4.0)`: loop `while _now() < deadline:`; replace
     every `time.monotonic()` in the method body with `_now()` (`start`, heartbeat,
     `cleared_at`, `settled`, `woke`). Docstring: one sentence that the deadline is the
     send's single budget.
   - `capture_session`'s `duration_s` keeps `time.monotonic()` (not part of the budget).
3. Tests in `tests/driver/test_omnigent.py`:
   - `_settle_driver`: drop `d.settle_timeout_s = 1.0`; set `d.turn_timeout_s = 1.0`.
   - Add a fake clock helper:
     ```python
     class _Clock:
         def __init__(self): self.t = 0.0
         def now(self): return self.t
         async def sleep(self, s): self.t += s
     def _fake_clock(monkeypatch):
         c = _Clock()
         monkeypatch.setattr("flowbench.driver.omnigent._now", c.now)
         monkeypatch.setattr("flowbench.driver.omnigent.asyncio.sleep", c.sleep)
         return c
     ```
   - `test_send_retries_undelivered_injection` → keep the shape, stub `_resend_allowed`
     True, fake clock, `turn_timeout_s=1000`; assert `sent == ["go on", "go on"]`, status
     IDLE, `clock.t == 30.0` (AC3).
   - `test_send_does_not_retry_delivered_failure` → keep: `_resend_allowed` stubbed False
     (a `model_error`), one send, FAILED (AC3).
   - `test_failed_exhausts_bounded_resends` (AC3): `_send_once` always `FAILED("")`,
     `_resend_allowed` True, `turn_timeout_s=1000`; `len(sent) == 1 + send_retry_attempts`,
     status FAILED.
   - `test_resend_allowed_reads_the_error_labels` (AC1), replacing
     `test_injection_undelivered_reads_the_error_labels`: `{}` labels → True;
     runner_error + "not delivered" → True; `model_error` → False.
     `test_resend_allowed_is_false_when_the_read_fails` replaces the other (False).
   - `test_failed_with_new_text_is_a_flaked_idle` (AC2): `_FakeChat([TurnStatus.FAILED])`,
     batches `[[], [_USER, _REPLY]]`, count injects via a wrapped `chat.send`; make
     `_resend_allowed` raise if called; assert `(status, flaked, assistant_text) ==
     (IDLE, True, "WINNER: B")`, one inject, capsys shows `turn flaked`.
   - `test_failed_with_only_an_empty_new_message_is_not_flaked` (AC2a): batches
     `[[_USER, _REPLY], [_USER, _REPLY, _USER2, _EMPTY_REPLY]]` (`_EMPTY_REPLY` content
     `"  "`), `send_retry_attempts = 0` → status FAILED, `flaked is False`.
   - `test_failed_with_a_repeated_identical_reply_is_flaked` (AC2 positive): batches
     `[[_USER, _REPLY], [_USER, _REPLY, _USER, _REPLY]]` → IDLE, flaked.
   - `test_idle_with_only_an_empty_new_message_keeps_settling` (row 5 + new predicate):
     FAKE clock (`_fake_clock(monkeypatch)`), `d.turn_timeout_s = 100`,
     `_FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])` (RUNNING once, then IDLE), batches
     `[[_USER, _REPLY], [_USER, _REPLY, _EMPTY_REPLY], [_USER, _REPLY, _EMPTY_REPLY,
     _REPLY2]]` (n_before probe, post-wait read = empty new message → keep settling, next
     settle read = `_REPLY2`) → IDLE with `assistant_text == _REPLY2["content"]`, and
     `clock.t < 100` (the settle continued past the empty message and stopped on the
     real one, not on the budget).
   - `test_non_failed_statuses_are_never_resent` (AC4), parametrized over
     `TurnResult(TIMEOUT, "", False)`, `TurnResult(RUNNING, "", False)`,
     `TurnResult(STALLED, "", False, stall_reason="prompt")`: fake `_send_once`; assert one
     send and the same status back.
   - Convert the real-clock cap tests to the fake clock so the hard timer cannot race
     their `RUNNING`/passthrough assertion. Under the fake clock every `_wait_idle` poll
     costs 1.5 s and `min_wait` is 4 s, so each converted test sets `d.turn_timeout_s =
     10.0` (replacing its 0.05/0.1/0.2 value) and, where it had one, `d.stall_s` stays as
     written. Per test: `test_one_poll_prompt_flicker_is_not_a_stall` → RUNNING;
     `test_moving_heartbeat_is_not_a_stall` → RUNNING (the beat changes every poll, so
     `last_beat` is always fresh); `test_queued_own_input_is_not_a_prompt` → RUNNING;
     `test_undocumented_server_status_passes_through` → `"zombie"` (drop its "NOT
     monkeypatching" comment; the fake clock advances on sleep);
     `test_cap_during_wake_wait_is_a_timeout_not_idle` → TIMEOUT (poll 1 idle+busy →
     running, poll 2 idle cleared → grace armed with `child_wake_s = 999`, polls continue
     to 10 s → cap → TIMEOUT); `test_send_settle_expiry_is_a_timeout_not_a_stale_idle` →
     TIMEOUT, with its chat changed to `_FakeChat([TurnStatus.RUNNING, TurnStatus.IDLE])`
     (pops RUNNING once, then stays IDLE — the alternating `* 10` sequence would expire
     inside `_wait_idle` and return RUNNING): first `_wait_idle` returns IDLE at 1.5 s;
     each settle round is `settle_poll_s` + a `_wait_idle` that needs `min_wait` (4 s, three
     idle polls) → rounds end at ≈ 6, 10.5 → the round that starts past 10 s finds
     `_now() >= deadline`, the loop exits with status IDLE and no new text → TIMEOUT.
     Remove `d.settle_timeout_s = 0.05` there. Trace each with the fake clock before
     committing; the asserted statuses are unchanged.
   - `test_one_budget_per_send` (AC6a): fake clock; `turn_timeout_s = 100`; snapshot
     sequence `[(RUNNING, [])]*40 + [(IDLE, [])] + [(RUNNING, [])]*10_000` via
     `_seq_snapshot` (its `updated_at` = poll count, so the heartbeat moves); batches
     `[[], [_USER]]` (no new text). 40 polls × 1.5 s = 60 s before the idle. Assert
     `result.status == TurnStatus.RUNNING` and `clock.t <= 100 + d.settle_poll_s + 1.5`.
     Comment: the pre-S02.3 code returns at ≈ 160 here (second `_wait_idle` gets its own
     `turn_timeout_s`).
   - Hard-ceiling tests (AC6d–k), REAL clock, real `_send_once`/`_wait_idle`. Reachability:
     `_wait_idle` sleeps 1.5 s real between polls and `min_wait` is 4 s, so any test whose
     target lies PAST a status poll patches the module's `asyncio.sleep` to a fast real
     sleep, `_fast_sleep = lambda s: _real_sleep(min(s, 0.001))` (`_real_sleep =
     asyncio.sleep` captured at import) — real time still flows, so the timer works.
     Common: `d.turn_timeout_s = 0.1` unless stated; injects counted by wrapping
     `chat.send`; a `hit = {}` dict set by the fake at the target so the test asserts the
     target WAS entered; each asserts `result == TurnResult(TurnStatus.TIMEOUT, "", False)`
     and `time.monotonic() - t0 < 2.0`; `async def hang(*a, **k): await asyncio.Event().wait()`.
     - `test_hard_ceiling_cancels_a_hanging_status_read` (d): `d._snapshot = hang`
       (sets `hit["snapshot"]`); 1 inject. No sleep patch needed (first poll hangs).
     - `test_hard_ceiling_stops_before_the_first_inject_when_the_initial_read_hangs` (e):
       `list_items` hangs on its 1st call; 0 injects; `hit["items"]`.
     - `test_hard_ceiling_cancels_a_hanging_post_wait_item_read` (f): `_fast_sleep`;
       `_FakeChat([RUNNING, IDLE])`; `list_items` 2nd call sets `hit` then hangs; 1 inject.
     - `test_hard_ceiling_cancels_a_hanging_second_page` (f'): `_fast_sleep`; 2nd
       `list_items` call returns `[{**_USER, "id": f"i{n}"} for n in range(200)]`, 3rd call
       sets `hit` then hangs; assert the 3rd call was made (pagination reached); 1 inject.
     - `test_hard_ceiling_cuts_read_retry_backoff` (g): real sleep (the back-off IS the
       target); `d._snapshot` always raises `httpx.ReadError("down")` and counts calls;
       assert ≥ 1 call, 1 inject.
     - `test_hard_ceiling_cancels_a_hanging_label_read` (h): `_FakeChat([FAILED])`,
       `d.send_retry_wait_s = 0.01` (so the 0.1 budget makes the re-send eligible and
       `_resend_allowed` is reached); `d._http` = object whose `get` sets `hit["labels"]`
       then hangs; assert `"labels" in hit`; 1 inject.
     - `test_hard_ceiling_cancels_an_overshooting_retry_sleep` (i): `d.turn_timeout_s =
       0.3`, `d.send_retry_wait_s = 0.1`, `_FakeChat([FAILED])`, `_resend_allowed` stub
       True, module `asyncio.sleep` patched to `lambda s: _real_sleep(s + 1.0)` and
       recording `hit["slept"] = s`; assert `hit["slept"] == 0.1`, 1 inject.
     - `test_hard_ceiling_cancels_the_resend_wait` (i'): `d.turn_timeout_s = 0.6`,
       `d.send_retry_wait_s = 0.1`, `_resend_allowed` stub True, snapshot returns
       `FAILED` on its 1st call then hangs (sets `hit`); 2 injects.
     - `test_hard_ceiling_covers_a_slow_filesystem` (k): `_fast_sleep`; `_FakeChat([RUNNING,
       IDLE])`, batches `[[], [_USER, _REPLY]]`; `d.artifact_path` replaced by a plain
       function that sets `hit["fs_started"] = time.monotonic()`, `time.sleep(1.0)`, then
       sets `hit["fs_done"] = time.monotonic()` and returns None. After `send` returns,
       assert `"fs_started" in hit`, `"fs_done" not in hit` (the worker is still running),
       result `TurnResult(TIMEOUT, "", False)`, elapsed < 1.0.
   - `test_no_inject_when_the_budget_is_gone_before_it` (AC6j, soft, fake clock, real
     `_send_once`): `_FakeChat([FAILED])`, `_resend_allowed` True, `turn_timeout_s = 31`,
     `send_retry_wait_s = 30`, fake `sleep` advancing `s + 1`; injects counted at
     `chat.send`: exactly 1, result `TIMEOUT`.
   - `test_no_inject_after_a_slow_initial_read` (AC6e', fake clock): `list_items` 1st call
     does `clock.t += d.turn_timeout_s + 1` then returns `[]`; 0 injects, `TIMEOUT`.
   - `test_resend_needs_budget_for_its_wait` (AC6b/c), parametrized
     `(turn_timeout_s, expected_sends) in [(50, 2), (10, 1)]`: fake clock;
     `send_retry_wait_s = 30`, `send_retry_attempts = 3`, `_send_once` always `FAILED("")`
     in zero clock time, `_resend_allowed` True; assert `len(sent) == expected_sends`,
     status FAILED.
   - `test_send_once_captures_the_streamed_events`: call
     `d._send_once("hi", _now() + 0.01)` — import `_now` from the module or pass
     `time.monotonic() + 0.01`.
   - `test_failed_session_status_ends_the_turn`: keep (send_retry_attempts = 0).
   - Every `_send_once` double changes signature to `(text, deadline)`: the
     `fake_send_once` in `test_send_retries_undelivered_injection`,
     `test_send_does_not_retry_delivered_failure`, `test_failed_exhausts_bounded_resends`,
     `test_non_failed_statuses_are_never_resent`, `test_resend_needs_budget_for_its_wait`
     — `async def fake_send_once(text, deadline): …`. Real-clock tests not listed under the
     fake-clock conversion keep their `d.turn_timeout_s` values.
   Commit: `feat(driver): one retry policy and one wall-clock budget per send (#103)`.

## Task 2 — `SessionModel.generate` shrinks; loop counts flaked turns

Files: `src/flowbench/model.py`, `src/flowbench/loop.py`, `tests/test_model.py`,
`tests/test_loop.py`.

1. `model.py`: delete `GENERATE_ATTEMPTS`, `GENERATE_RETRY_WAIT_S`, `_fresh`,
   `_last_text`, the `asyncio`/`sys` imports. `generate` becomes:
   ```python
   async def generate(self, prompt: str):
       if not self._started:
           await self._driver.start()
           self._started = True
       # The driver owns retry policy (docs/design/runner.md, "Send/retry policy"):
       # an idle result is a completed turn (flaked or not); anything else is not
       # re-sent here — TIMEOUT may be mid-turn after delivery, FAILED is already
       # past the driver's bounded re-sends.
       result = await self._driver.send(prompt)
       text = result.assistant_text
       if result.status != TurnStatus.IDLE or not text.strip():
           raise RuntimeError(
               f"simulator/judge turn ended {result.status!r} with "
               f"{'no' if not text.strip() else 'a'} reply"
           )
       class _Out:
           completion = text
       return _Out()
   ```
   Module docstring: drop nothing (it does not mention retries).
2. `loop.py`: `flaked = 0` on the line BEFORE `result = await driver.send(first_prompt)`
   (i.e. next to `convo = []`); `flaked += result.flaked` immediately after that first
   send AND after the in-loop `result = await driver.send(reply)`; `session["flaked_turns"]
   = flaked` next to `session["turns"]`. Update the comment at the `status != IDLE`
   break: `failed` here means "no reply after the driver's bounded re-sends".
3. `tests/test_model.py`: replace the six generate tests with:
   - `test_generate_idle_path_single_send` (kept).
   - `test_generate_accepts_a_flaked_idle_turn`: `TurnResult(IDLE, "the reply", False,
     flaked=True)` → completion, one send.
   - `test_generate_raises_on_non_idle_without_retry`, parametrized over
     `TIMEOUT("fresh but untrusted")`, `FAILED("")`, `FAILED("some text")`, `STALLED("")`:
     `RuntimeError` matching the status value, exactly one send.
   - `test_generate_raises_on_empty_idle_text`, parametrized over `""` and `"  \n"`:
     `IDLE(text)` → `RuntimeError` match `"no reply"`, one send. Comment: NEW guard —
     pre-S02.3 `generate` returned an empty completion here.
   - `test_close_closes_driver_only_after_start` (kept). Drop the `import flowbench.model
     as model_mod` line (no monkeypatching left). The removal of the module-level knobs is
     checked by the Task 3 grep, not by a test that would itself contain the names.
4. `tests/test_loop.py`: `test_loop_continues_past_a_flaked_idle_turn_and_counts_it`
   (AC9), parametrized `flaked_index in (0, 1)`: turns `[IDLE("q?", False), IDLE("done",
   True)]` with `flaked=True` set on `turns[flaked_index]`; a sim that answers once then
   DONE; assert `session["exit_status"] == TurnStatus.IDLE`, `session["flaked_turns"] ==
   1`, `session["turns"] == 1` in both cases (the first-send flake is the uninitialized-
   counter trap). Add `assert session["flaked_turns"] == 0` to the existing happy-path
   test.
   Commit: `refactor(model): SessionModel.generate is send + raise + wrap (#103)`.

## Task 3 — docs

Files: `docs/design/runner.md`, `src/flowbench/driver/omnigent.py` (docstring only if
Task 1 left a stale line), `CLAUDE.md` (no change expected — verify).

1. `docs/design/runner.md`, under "## flowbench/driver/ — the ONE package that knows
   omnigent exists", after the "Where a flow's skills live at run time" subsection, add
   `### Send/retry policy (S02.3)` containing: one sentence ("`OmnigentDriver.send` is
   the only place that decides whether a turn is re-sent; callers — the loop,
   `SessionModel`, scripts — read `TurnResult.status` and never re-derive it."), the
   five-row table copied byte-for-byte from `spec.md`, the precedence paragraph (new
   assistant text is checked first, so row 2 never reads a label; rows 1 and 3 are decided
   by one label read in `_resend_allowed` — absent code, or `runner_error` + "not
   delivered" → re-send; any other present code, or an unreadable label → no re-send), and
   a "One wall-clock budget per send" paragraph: `deadline = now +
   turn_timeout_s` computed once in `send`; `_wait_idle`, the settle loop and the retry
   sleeps all draw it down; a re-send happens only while the remaining budget exceeds
   `send_retry_wait_s`; the whole send runs under `asyncio.timeout(turn_timeout_s)`, so
   a server call, back-off or retry sleep still in flight at the cap is cancelled and
   the send reports `TIMEOUT`; at the cap the status is `RUNNING` if the soft loop got
   there first, `TIMEOUT` if the timer did; before S02.3 a single send could spend
   `(1 + send_retry_attempts) × 3 × turn_timeout_s + send_retry_attempts ×
   send_retry_wait_s` — 2 970 s with the defaults, 36 090 s on todo_app. Mention
   `TurnResult.flaked` and `session["flaked_turns"]`.
2. Same file: `TIMEOUT` row of the status table → "idle but silent, or the send's budget
   expired"; `model.py` row → "`SessionModel`: `.generate(prompt)` shim over one
   persistent omnigent session (simulator + judge); send, raise on a non-idle or empty
   result, wrap the completion".
3. Executable checks (AC1, AC7, AC8, AC10), all from the engine worktree root; every
   command's output goes into `gates.md` verbatim:
   ```bash
   diff <(sed -n '/^| Observation/,/^$/p' $SCEN_ITEM/spec.md) <(sed -n '/^| Observation/,/^$/p' docs/design/runner.md) && echo AC10-table-ok
   rg -n 'settle_timeout_s|overrun_s' src tests docs; echo "AC7-a exit=$? (1 = none found)"
   rg -n 'GENERATE_ATTEMPTS|GENERATE_RETRY_WAIT_S|_fresh\b|_last_text|_injection_undelivered' src tests; echo "AC1/AC8 exit=$? (1 = none found)"
   rg -c 'asyncio\.timeout\(' src/flowbench/driver/omnigent.py   # must print 1
   uv run python - <<'EOF'
   import ast, pathlib
   tree = ast.parse(pathlib.Path("src/flowbench/driver/omnigent.py").read_text())
   for fn in ast.walk(tree):
       if isinstance(fn, ast.AsyncFunctionDef):
           for node in ast.walk(fn):
               if isinstance(node, ast.AsyncWith) and any(
                   ast.unparse(i.context_expr).startswith("asyncio.timeout(") for i in node.items
               ):
                   print("asyncio.timeout enclosed by", fn.name); assert fn.name == "send"
   EOF
   ```
4. `docs/design/runner.md` one-budget paragraph names both layers (soft checks on
   waits and before every inject; the timer on everything) per the spec.
   Commit: `docs(runner): send/retry policy table + one budget per send (#103)`.

## Task 4 — quality gates (V1, V2, V3, V8) → `gates.md`

Files: `$SCEN_ITEM/gates.md` (scenarios worktree `/Users/zarz/dev/xebia/flowbench-scenarios--s023`,
item dir `.claude/engineering-loop/items/flowbench-103/`). Run from the engine worktree
unless stated; paste each command and its tail into `gates.md`.

1. V1: `uv run pytest -q` → green, only the `live_agent` skip.
2. V3: `uv run ruff check . && uv run ruff format --check .` → clean.
3. V2 (self-verifying, from the scenarios worktree):
   `uv run --with-editable /Users/zarz/dev/agents/flowbench--s023 python -c 'import flowbench; print(flowbench.__file__)'`
   must print a path under `/Users/zarz/dev/agents/flowbench--s023/`; then
   `uv run --with-editable /Users/zarz/dev/agents/flowbench--s023 pytest -q` → green.
4. V8: `uv run pytest -q --cov=src/flowbench --cov-report=xml && uv run diff-cover coverage.xml --compare-branch origin/master --fail-under=100` → must pass (AC11 says 100 %).
5. `git fetch origin && git rebase origin/master`; if any conflict touched code, re-run gate 3
   before continuing. Then re-run steps 1–4 on the rebased HEAD (all four, not two) and
   record those as the shipped numbers.
Commit `gates.md` in the scenarios worktree: `docs(loop): flowbench-103 gates`.

## Task 5 — ship the engine PR

```bash
cd $ENG
git push --no-verify -u origin loop/issue-103-retry-policy          # pre-push hook leaks GIT_DIR in worktrees (#49); CI is the gate
gh pr create --base master --title "feat(driver): one retry policy and one wall-clock budget per send (E02 S02.3, #103)" --body-file $SCEN_ITEM/pr-body.md
gh pr checks --watch                                                 # all green, else fix on the branch (Task 4 discipline), push, re-poll
PR=$(gh pr view --json number -q .number)
gh pr merge $PR --squash --delete-branch
MERGED=$(gh pr view $PR --json mergeCommit -q .mergeCommit.oid); echo $MERGED    # THIS PR's squash commit, not origin/master
python3 - <<EOF
import json; p="$SCEN_ITEM/state.json"; s=json.load(open(p)); s["engine_pr"]=$PR; s["engine_merge_sha"]="$MERGED"; json.dump(s, open(p,"w"), indent=1)
EOF
```
`pr-body.md` (write it first): `Closes #103`; three-line spec summary; plan summary;
pointers `flowbench-scenarios:.claude/engineering-loop/items/flowbench-103/{spec,plan,gates}.md`
and the review verdicts; last line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
`MERGED` is persisted in `state.json`; every later task reloads it from there.

## Task 6 — live gates on the merged SHA (AC12) → `gates.md`

Pin the engine to the exact merged SHA for BOTH runs — not "whatever master is now":
```bash
MERGED=$(python3 -c "import json; print(json.load(open('$SCEN_ITEM/state.json'))['engine_merge_sha'])")
cd $ENG && git fetch -q origin && git checkout -q --detach $MERGED && test "$(git rev-parse HEAD)" = "$MERGED" && echo pinned-$MERGED
uv sync --extra dev --extra live -q
env | grep -c '^ANTHROPIC_API_KEY=' ; # must print 0
```
todo_app runs from the engine checkout (that is where `scenarios.coding_workflow` lives);
swe_planning runs from the scenarios worktree with the engine overlaid from `$ENG` via
`--with-editable` (the self-verifying V2 form: `uv run` alone would re-sync the git pin).

1. **V5 todo_app** (from `$ENG`):
   ```bash
   RUN=s023-$(date +%H%M)
   nohup caffeinate -i uv run --extra live python -m scenarios.coding_workflow.run --case todo_app --run-id $RUN --runs-root $RUNS/coding_workflow > /tmp/$RUN.log 2>&1 &
   PID=$!
   (cd $SCEN && uv run python -m scenarios.swe_planning.watch $RUN --runs-root $RUNS/coding_workflow --pid $PID)
   ```
   Pass iff, under `$RUNS/coding_workflow/$RUN/`:
   - `for f in baseline superpowers; do uv run python -c "import json,sys; d=json.load(open('$RUNS/coding_workflow/$RUN/$f/scorecard.json')); sys.exit('error' in d)"; done` exits 0 both times;
   - `out=$(cd $ENG && uv run flowbench compare --run-base $RUNS/coding_workflow --run-id $RUN); rc=$?; echo "rc=$rc"; echo "$out" | grep -q baseline && echo "$out" | grep -q superpowers && ! echo "$out" | grep -q FAILED && test $rc -eq 0 && echo compare-ok` prints `rc=0` and `compare-ok` (paste the rendered table into `gates.md`);
   - `for f in baseline superpowers; do uv run python -c "import json; s=json.load(open('$RUNS/coding_workflow/$RUN/$f/session.json')); assert s['exit_status']=='idle' and 'stall_reason' not in s, s.get('exit_status'); print('$f', s['turns'], s['flaked_turns'], s['duration_s'])"; done` prints both lines;
   - `grep -c 'turn flaked' /tmp/$RUN.log` recorded (any value; it is a diagnostic).
2. **V4 swe_planning** (from `$SCEN`):
   ```bash
   uv run --with-editable $ENG --extra live python -c 'import flowbench; print(flowbench.__file__)'   # must be under $ENG
   RUN=s023-plan-$(date +%H%M)
   nohup caffeinate -i uv run --with-editable $ENG --extra live python -m scenarios.swe_planning.run --run-id $RUN --n 1 > /tmp/$RUN.log 2>&1 &
   PID=$!
   uv run python -m scenarios.swe_planning.watch $RUN --pid $PID
   ```
   Pass iff the watcher exits by itself (its last line reports `run.json`; record `echo
   watcher-rc=$?` = 0) AND this script exits 0:
   ```bash
   uv run python - <<EOF
   import json, pathlib, sys
   root = pathlib.Path("$RUNS/swe_planning/$RUN")
   run = json.load(open(root / "run.json"))
   assert run.get("winner") not in (None, "unknown"), run.get("winner")
   flows = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith("_") and (d / "session.json").exists()]
   assert flows, "no flow dirs"
   for d in flows:
       for f in ("plan.md", "transcript.md", "session.json"):
           assert (d / f).exists(), f"{d.name}/{f} missing"
       s = json.load(open(d / "session.json"))
       assert s["exit_status"] == "idle", (d.name, s["exit_status"], s.get("stall_reason"))
       print(d.name, s["turns"], s.get("flaked_turns"), s["duration_s"])
   print("winner", run["winner"], "flows", len(flows))
   EOF
   ```
   (`--n 1` writes the run at the root, not under `trial-XX/`; if a `trial-01/` exists,
   point `root` there.) Paste the script output into `gates.md`.
3. Both outcomes (run ids, per-flow table, `$MERGED`) into `gates.md` and the ledger
   entry. A failure → post-mortem first (ledger rule: `git log $MERGED..origin/master`
   before writing a fix); the fix is the same item (#103), not a new issue.

## Task 7 — paired scenarios PR

From `$SCEN`:
```bash
uv lock --upgrade-package flowbench
grep -n "flowbench?branch=master#" uv.lock          # fragment = the resolved SHA; record it (it is $MERGED unless master moved — say which in the ledger)
uv sync --extra live -q && uv run pytest -q         # V2 against the pinned engine
# ledger: append the item's entry to $SCEN/.claude/engineering-loop/LOG.md (outcome, gates, live runs, lessons)
# handoff: overwrite $SCEN/.claude/engineering-loop/HANDOFF.md (state, in flight, next)
# state:  $SCEN_ITEM/state.json  phase=MERGED, engine_pr, engine_merge_sha, live_gate ids, gates
git add -f .claude/engineering-loop uv.lock && git commit -m "docs(loop): flowbench-103 merged — ledger, handoff, engine pin"
git push --no-verify -u origin loop/issue-103-retry-policy
cat > $SCEN_ITEM/pr-body-scenarios.md <<EOF
Pairs with flowbench PR #<engine PR> (merged as <MERGED>): E02 S02.3, one retry policy at the driver.

- ledger entry + HANDOFF for flowbench-103; item dir with spec, plan, gate verdicts, gates.md
- engine pin bumped to <resolved SHA> (uv.lock)
- live gates: todo_app <run id>, swe_planning <run id> — outcomes in gates.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
gh pr create --base main --title "loop: flowbench-103 (E02 S02.3) ledger + engine pin" --body-file $SCEN_ITEM/pr-body-scenarios.md
gh pr checks --watch && gh pr merge --squash --delete-branch
$SCEN/.claude/engineering-loop/board.sh $ISSUE MERGED
gh issue comment $ISSUE --body "Merged: <engine PR url> (<sha>); ledger: <scenarios PR url>; live gates <run ids>."
```
Then remove both worktrees: `git -C /Users/zarz/dev/agents/flowbench worktree remove $ENG`
and `git -C /Users/zarz/dev/xebia/flowbench-scenarios worktree remove $SCEN`.

## Traceability

| AC | Task | Test |
| --- | --- | --- |
| AC1 | 1 | `test_resend_allowed_reads_the_error_labels`, `test_resend_allowed_is_false_when_the_read_fails`; grep in Task 3 step 3 |
| AC2 | 1 | `test_failed_with_new_text_is_a_flaked_idle`, `..._only_an_empty_new_message_is_not_flaked`, `..._repeated_identical_reply_is_flaked`; `test_new_assistant_text_*` in test_transcript.py |
| AC3 | 1 | `test_send_retries_undelivered_injection`, `test_send_does_not_retry_delivered_failure`, `test_failed_exhausts_bounded_resends` |
| AC4 | 1 | `test_non_failed_statuses_are_never_resent` |
| AC5 | 1 | `test_send_settle_expiry_is_a_timeout_not_a_stale_idle`, `test_idle_with_only_an_empty_new_message_keeps_settling` |
| AC6 | 1 | `test_one_budget_per_send`, `test_resend_needs_budget_for_its_wait`, `test_no_inject_when_the_budget_is_gone_before_it`, `test_no_inject_after_a_slow_initial_read`, `test_hard_ceiling_*` (9) |
| AC7 | 1 | grep in Task 3 step 3 (`settle_timeout_s`, `overrun_s`, `asyncio.timeout(` count) |
| AC8 | 2 | `test_generate_*` (4); Task 3 step 3 grep for the removed names |
| AC9 | 2 | `test_loop_continues_past_a_flaked_idle_turn_and_counts_it` |
| AC10 | 3 | diff + grep in Task 3 step 3 |
| AC11 | 4 | `gates.md` steps 1–4 (V1, V3, V2 with `flowbench.__file__`, V8 %) |
| AC12 | 6 | `gates.md` live section: todo_app assertions (scorecards without `error`, compare without FAILED, `exit_status` idle, no `stall_reason`) + swe_planning assertions (watcher exit, winner, artifacts, idle) |
