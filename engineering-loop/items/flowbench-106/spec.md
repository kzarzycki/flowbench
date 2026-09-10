# Spec — flowbench #106 (E02 S02.6): error taxonomy

Size S. Engine worktree `/Users/zarz/dev/agents/flowbench--s026`, branch
`loop/issue-106-error-taxonomy`, base `origin/master` 1a6a714 (after S02.5 part 2: both label
reads go through the SDK's `sessions.get()` under `asyncio.timeout(_LABEL_READ_S)`).

## Problem

Seven `except Exception` sites swallow every failure, including driver bugs and server
schema drift, and say nothing: `ruff check --select BLE001 src/ scenarios/` lists
`driver/omnigent.py` ×4 (`_resend_allowed`, `_pane_tail`, `_context_tokens`, `close`),
`transcript.to_jsonable`, `watch._run_sessions`, plus `todo_app/scorers.collect_code`
behind a reasonless `# noqa: BLE001`. A `TypeError` from a changed label shape reads as
"no label"; a broken watcher reports "all healthy" forever. The rule is not enabled, so
new sites appear unnoticed.

## Change

- **Narrow** where the failure shapes are known. The two label reads
  (`_resend_allowed`, `_context_tokens`) catch one tuple, `_label_read_errors()`:
  `(OmnigentError, httpx.HTTPError, TimeoutError, KeyError, ValueError, TypeError,
  OverflowError)` — what
  `sessions.get()` raises on a >= 400 status or a body that is not a JSON object
  (`OmnigentError`), a transport failure (`httpx.HTTPError`, unwrapped by the SDK), the
  driver's own read cap (`TimeoutError` from `asyncio.timeout(_LABEL_READ_S)`), a JSON
  object that is not a complete Session (`Session.from_dict` → `KeyError`), and a label
  *value* of the wrong type (`int("lots")` → `ValueError`; `"not delivered" in None` / `in
  7` → `TypeError`). The tuple is built by a function because `omnigent_client` is the
  `live` extra and is imported lazily, as `start()` does. The `try` encloses the read
  **and every label lookup/conversion**, so a malformed label value takes the fallback
  (`False` = "unknown, do not retry"; `None` = no cost signal) instead of raising. `labels`
  is used as the SDK hands it (`Session.labels`, always a dict: `Session.from_dict` coerces
  a missing/null/non-dict `labels` to `{}`), with no `or {}` — a missing code is still
  row 3 (`True`), so the legitimate sim/judge retry is untouched. Row 1 requires the message
  to be a `str` containing "not delivered": a non-string message (null, number, list, dict)
  is not the undelivered signal and yields `False` by the guard, not by an exception.
  Anything else propagates.
  `_run_sessions` catches `(OSError, http.client.HTTPException, ValueError,
  AttributeError)`. `collect_code` catches `(OSError, ValueError)`.
- **Waive with a reason** where swallowing is the contract: `close` (teardown never masks
  the error that got us here), `_pane_tail` (best-effort watchdog probe inside the send)
  and `to_jsonable` (records streamed events inside `_send_once`; the capture must survive
  whatever the client ships and never abort the turn it records) keep
  `except Exception  # noqa: BLE001 -- why`.
- **Every site logs** the swallowed exception at DEBUG through
  `logging.getLogger(__name__)`.
- **`BLE` enabled** in `[tool.ruff.lint] select`; `run.py`'s existing reasoned waivers stand.
- `_resend_allowed`'s policy (rows 1/3) is unchanged. Body shape is the SDK's: a non-dict
  `labels` is `{}` (row 3) before the driver sees it, and a 3xx that carries a complete
  Session is a successful read (the SDK raises only at >= 400). What moves to the
  "unreadable label → no re-send" row that `docs/design/runner.md` ("Precedence and
  mechanics") already states: `runner_error` with a non-string message — `null`/number
  raise `TypeError` today, a list or dict containing "not delivered" passes the `in` test
  today and would authorize a re-send; all now `False`.
- Coverage measures `scenarios` as well as `src` (`[tool.coverage.run] source`), so the
  scorer catch is inside V1's diff-cover gate.

## Why safe

Fallback values are unchanged for every input the old catches handled, with one intended
transition: `_resend_allowed` returns `False` for `runner_error` with a non-string message
(raised, or for containers wrongly re-sent, before). Every failure the SDK or the read cap raises today is inside the tuple;
what now propagates is a category the old code hid: our own bugs. On the send path only
`_resend_allowed` narrows (`_pane_tail` and `to_jsonable` are waived, so `_send_once`'s
capture and the watchdog probe behave as before). Live validation after merge: V4
(`swe_planning`, mandatory for driver/send-policy changes) and V5 (`todo_app`, the brief).

## Acceptance criteria

- AC1: `uv run ruff check .` passes with `"BLE"` in `select`. The audit is ruff's
  (executable catch sites only; the program-text literal in `acceptance.py` is a string).
  Each remaining `except Exception` in `src/` and `scenarios/` carries `# noqa: BLE001`
  followed by a reason; the two existing reasoned waivers in `run.py` are accepted as
  written, the new ones use `# noqa: BLE001 -- <reason>`.
- AC2: `_resend_allowed` returns `False` and `_context_tokens` returns `None` on each of:
  an `httpx.HTTPError`, an `OmnigentError`, a `TimeoutError`, a `KeyError` from the client
  double (partial Session body), and — through the real SDK over `httpx.MockTransport` — a
  503, an HTML 200, a JSON object lacking Session fields; plus, for `_resend_allowed`, the
  payload `{"omnigent.last_task_error_code": "runner_error",
  "omnigent.last_task_error_message": null}` and the same with message `7`,
  `["not delivered"]`, `{"not delivered": true}` (guard, no log), and for `_context_tokens`
  a token label `"lots"`, `1e400` (`inf`) and `[1]`; and, real SDK, a Session body whose
  `created_at` is `1e400` (both fall back). Both re-raise a `RuntimeError` from the client.
  `_resend_allowed` still returns `True` for `labels` `{}` and for the undelivered
  runner_error pair; through the real SDK, `labels` `[]`/`""`/`0`/absent/null each yield
  `True` (the SDK coerces to `{}`; the test records that the coercion is the SDK's).
- AC3: `_context_tokens` on a 503 body carrying a token label (real SDK) returns `None`.

- AC4: `to_jsonable` still falls back on `ValueError` and on `RuntimeError` from
  `model_dump`. `_run_sessions` still returns `[]` on `OSError`; a `RuntimeError`
  propagates. `collect_code` skips an unreadable path (a directory named `*.py`).
- AC5: each of the seven catch sites (`_resend_allowed`, `_context_tokens`, `_pane_tail`,
  `close`, `to_jsonable`, `_run_sessions`, `collect_code`) has a `caplog` assertion that a
  swallowed exception produces a DEBUG record from that module's logger.
- AC6: existing `close`/`_pane_tail` swallow tests still pass unchanged.
- V1: full suite green, diff-cover 100 % (coverage source includes `scenarios`).
- V4 + V5 after merge (plan Task 4): clean live runs as defined there.
