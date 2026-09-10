# issue-39 spec — OmnigentModel.generate must survive failed turns

## Problem
`OmnigentModel.generate` (scenarios/swe_planning/run.py:254) raises on the first
non-idle TurnResult. The omnigent terminal-readiness flake ("Claude Code terminal
did not become ready within 30.0s … The message was not delivered") surfaces as
status='failed'; OmnigentDriver.send only retries when the session labels confirm
non-delivery, which simulator sessions don't reliably set. Result: 2/2 live runs
crashed on a simulator's first turn (issues #30, #34 Phase 9.5 blocked).

## Fix (scenario-side, minimal; rev 2 after gate-1 REVISE)
Gate-1 objections: (a) a failed turn's `assistant_text` in a MULTI-TURN session
can be the previous turn's reply (stale) — trusting any non-empty text corrupts
the dialog; (b) failed+empty does not prove non-delivery, so resend must be
justified. Revised behavior in `OmnigentModel.generate`:
1. Track the previous turn's completion (`self._last_text`). A 'failed' turn
   whose text is non-empty AND differs from `_last_text` is a FRESH reply that
   landed before the flake fired → log to stderr and use it.
2. A 'failed' turn with empty or stale (== previous) text produced no new reply
   → retry `driver.send(prompt)` up to 2 more times, 30s apart. If the prompt
   had actually been delivered, the retry is a repeated question to a stateful
   dialog agent — semantically idempotent for simulator/judge prompts (worst
   case: the simulator answers the same question again); it cannot corrupt
   scoring because only the retried turn's fresh reply is consumed.
3. 'timeout' status: unchanged — raise immediately (a delivered prompt may be
   mid-turn; resending there is the known busy-terminal kill).
4. Still failed with no fresh text after all attempts → RuntimeError with
   attempt count.

## Acceptance criteria
- AC1: failed + fresh non-empty text → returned, single send, no raise.
- AC2: failed + empty text, next send idle → retry's text returned; send called
  exactly twice with the same prompt.
- AC3: failed + STALE text (== previous turn's completion) → retried, not
  trusted; fresh retry reply returned.
- AC4: all attempts failed with no fresh text → RuntimeError mentioning attempts.
- AC5: idle path unchanged (single send); 'timeout' still raises immediately
  without retry.
- AC6: retry wait patchable/zero-able in tests (module constant).
- AC7: suite green; diff confined to scenarios/swe_planning/run.py + tests.

## Non-goals
Fixing the omnigent terminal-readiness detection itself (upstream); changing
OmnigentDriver.
