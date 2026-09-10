# Spec — flowbench #131: a Claude session-limit banner is read as a reply

## Problem

When the Claude subscription session limit is hit, Claude Code emits one `role=assistant`
item whose whole text is a banner (`You've hit your session limit · resets 6:40pm
(Europe/Zurich)`), and the omnigent session usually flips to `failed`. `OmnigentDriver.
_send_once` sees FAILED + a new assistant message and applies row 2 of the send/retry
policy: `IDLE, flaked=True` — a completed turn. The loop relays the banner to the
simulator, the simulator (same subscription) answers with its own banner, and the two
sessions trade banners until `max_turns`/`deadline` (30 turns, 20 min, 18 `turn flaked`
lines in `s025p2-620b16b`). Nothing tells the operator to wait.

## Fix

1. `flowbench.transcript.is_quota_banner(text) -> bool`: the message starts with a
   limit-banner phrase and is at most 240 chars (decisions #3).
2. `flowbench.types.TurnStatus.QUOTA = "quota"` — "the CLI hit its subscription/rate limit;
   the turn produced a banner, not a reply".
3. `OmnigentDriver._send_once`: after settling, if the NEW assistant text
   (`new_assistant_text(items, n_before)`) is a banner, return
   `TurnResult(QUOTA, assistant_text=<banner>)` before the TIMEOUT/flaked classification,
   and print one `[flowbench] quota: <banner>` line to stderr. `send()` returns it
   unchanged (only FAILED is retried).
4. `run_agent_session`: no new branch — `QUOTA` is non-idle, so the loop stops after the
   turn and `session["exit_status"] == "quota"`.
5. `RunWatch.tick`: for each run session, read its last item (`GET
   /v1/sessions/{id}/items?limit=1&order=desc`, same read-failure handling as the sessions
   list); an assistant banner emits `QUOTA: <title> (<id>) <banner>` once per session.
6. `docs/design/runner.md`: one row appended to the send/retry table (banner → QUOTA, never
   re-sent) with its precedence sentence; one row appended to the `TurnStatus` table; the
   watcher sentence names `QUOTA`. `docs/onboarding.md` watcher line lists `QUOTA`.

## Why safe

- The rule fires only on a message that *is* a banner (anchored, length-capped); an agent
  mentioning a limit inside a reply is untouched. Verified against the captured banner and
  against every assistant text in the evidence run's transcript (none other matches).
- `QUOTA` is never re-sent, so the change cannot double-inject; the normal path
  (no banner) is byte-for-byte the previous logic — proven by the existing driver suite
  plus a live `todo_app` run.
- `StrEnum`: `"quota"` serialises as before; every existing member is unchanged.

## Acceptance criteria (checkable from diff + tests)

- AC1 `TurnStatus` has exactly the six members `idle running failed timeout stalled quota`
  (`tests/test_types.py` member table updated).
- AC2 `is_quota_banner` is True for the captured banner text (verbatim, from
  `s025p2-620b16b`) and for the `… limit reached` / `You have reached your … limit`
  families; False for `""`, for a real reply that mentions a limit mid-text, and for a
  banner-prefixed text longer than 240 chars.
- AC3 Driver: FAILED status + new banner text → `send()` returns `status == QUOTA`,
  `flaked is False`, `assistant_text` == the banner, exactly one inject, `_resend_allowed`
  never called, one `quota:` line on stderr. Same with IDLE status → `QUOTA`.
- AC4 Driver: FAILED + a new non-banner reply is still `IDLE, flaked=True` (existing test
  `test_failed_with_new_text_is_a_flaked_idle` stays green unchanged).
- AC5 Loop: a driver returning `QUOTA` on turn k stops the loop with
  `session["exit_status"] == "quota"` and the simulator is not asked again after it.
- AC6 Watcher: a run session whose last item is an assistant banner produces exactly one
  `QUOTA: …` event containing the banner, none on the next tick; a session whose last item
  is an ordinary reply produces none; an items read failure produces none and does not
  raise.
- AC7 `docs/design/runner.md` send/retry table has one added row (existing rows in the same
  order) and the `TurnStatus` table lists `QUOTA`.
- V4 Live: one `coding_workflow` `todo_app` run on the merged SHA, both flows idle,
  0 quota lines, watcher clean.
