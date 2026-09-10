# Plan — flowbench #131

Worktree: `/Users/zarz/dev/agents/flowbench--i131` (branch `loop/issue-131-quota-banner`,
off `origin/master` ≥ 512e711). Each task: tests first (red), then code (green),
`uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .` green before
the next task. Global constraints (from spec): the no-banner path is unchanged; `QUOTA` is
never re-sent; recognition is anchored + length-capped; docs state the truth once.

## Task 1 — vocabulary + recognition (AC1, AC2)

Files: `src/flowbench/types.py`, `src/flowbench/transcript.py`, `tests/test_types.py`,
`tests/test_transcript.py`.

- `TurnStatus.QUOTA = "quota"` with a one-line comment (derived: the CLI's limit banner).
  Update the `TurnResult.status` doc comment if it lists members. `tests/test_types.py::
  test_members_are_their_values` gains `"QUOTA": "quota"`.
- `transcript.py`: `_QUOTA_BANNER = re.compile(r"\A\s*(?:You(?:'ve| have) (?:hit|reached)
  your [\w -]{0,40}?limit\b|(?:Claude )?(?:usage|session|weekly|\d+-hour) limit reached\b)")`
  — both families pinned to the banner wording; no free `<word> limit reached` alternative, `_QUOTA_BANNER_MAX = 240`,
  `def is_quota_banner(text: str) -> bool`. Comment names the source (Claude Code banner
  from `s025p2-620b16b`; codex family unverified) and the ceiling (`# ponytail: one regex;
  extend it when a new wording shows up`).
- Tests in `tests/test_transcript.py`: parametrized True cases — the verbatim captured
  banner `You've hit your session limit · resets 6:40pm (Europe/Zurich)`, `Claude usage
  limit reached. Your limit will reset at 3pm (Europe/Zurich).`, `You have reached your
  weekly limit`, `You've hit your usage limit. Try again at 3:40 PM.`; False cases — `""`,
  `"I've hit the rate limit on the API, retrying"`, `"Ok. You've hit your session limit"`
  (not at start), `"The rate limit reached by the API was 5 rps, so I retried and then fixed
  the bug"` (a short ordinary reply starting `<word> limit reached`), and the banner
  followed by 300 chars of text (length cap).

## Task 2 — driver ends the turn as QUOTA (AC3, AC4)

Files: `src/flowbench/driver/omnigent.py`, `tests/driver/test_omnigent.py`.

- Import `is_quota_banner`. In `_send_once`, after the settle loop and before the
  `IDLE + no new text → TIMEOUT` line:
  ```python
  new_text = new_assistant_text(items, n_before)
  if is_quota_banner(new_text):
      # the wall, not a reply (#131): QUOTA whatever the server said, never re-sent
      print(f"[flowbench] quota: {new_text.strip()}", file=sys.stderr)
      return TurnResult(TurnStatus.QUOTA, new_text.strip())
  ```
  Use `new_text` in the two existing `new_assistant_text(items, n_before)` calls below it.
  `send()` needs no change (`QUOTA != FAILED` → returned after one `_send_once`); add `QUOTA`
  to the comment listing the never-re-sent rows. Update the dataclass comment block
  ("FAILED with a new assistant message is a flaked idle") to mention the banner exception.
- Tests (pattern of `test_failed_with_new_text_is_a_flaked_idle`): `_BANNER` item with the
  verbatim text.
  - `test_failed_with_a_quota_banner_is_quota_not_flaked`: `_FakeChat([FAILED])`, batches
    `[[], [_USER, _BANNER]]`, `turn_timeout_s = 1000`, `_resend_allowed` raises if called,
    counting inject → `(status, flaked, assistant_text) == (QUOTA, False, banner)`, one
    inject, `"quota:"` in stderr.
  - `test_idle_with_a_quota_banner_is_quota`: `_FakeChat([RUNNING, IDLE])`, same batches →
    `status == QUOTA`.
  - Add `TurnResult(TurnStatus.QUOTA, "banner")` to the `test_non_failed_statuses_are_never_
    resent` parametrization.
  - AC4: `test_failed_with_new_text_is_a_flaked_idle` unchanged and green.

## Task 3 — loop stops, watcher prints (AC5, AC6)

Files: `src/flowbench/loop.py` (comment only), `src/flowbench/watch.py`, `tests/test_loop.py`,
`tests/test_watch.py`.

- `loop.py`: extend the "Only an idle turn is a clean boundary" comment with `quota` (the
  banner ended the session; the simulator is not asked again). No logic change.
- `tests/test_loop.py::test_loop_stops_on_quota`: `_FakeDriver` + `_StubModel` from `tests/test_loop.py` (pattern of `test_loop_bails_on_failed_status`) whose
  2nd send returns `TurnResult(TurnStatus.QUOTA, "You've hit your session limit · resets
  6:40pm (Europe/Zurich)")`; `StubSim` that records prompts → `session["exit_status"] ==
  "quota"`, `session["turns"] == 1`, the sim was called exactly once.
- `watch.py`: `self._session_quota: set[str] = set()` declared in `__init__` next to
  `_session_stall`. `_last_assistant_text(session_id) -> str` reads
  `{server}/v1/sessions/{id}/items?limit=1&order=desc` (`json.load(r)["data"]`) with the same
  `except` tuple and `log.debug` as `_run_sessions`; returns `transcript.item_text(item)`
  only when the single item has `type == "message"` and `role == "assistant"`, else `""`
  (a user/tool item, an empty list, or a read failure are all `""`).
  In `tick()`, per session, after the FAILED check: `if s["id"] not in self._session_quota`
  and `is_quota_banner(text := self._last_assistant_text(s["id"]))` → append
  `f"QUOTA: {s.get('title')} ({s['id']}) {text.strip()}"` and add the id to the set.
  Docstring's event list gains "quota banners".
- `tests/test_watch.py::test_run_watch_quota_banner_once`: stub `_run_sessions` (one
  session) and `_last_assistant_text` (returns the banner) → exactly one `QUOTA:` event
  containing the banner; second tick → none. Stub returning `"WINNER: B"` → none. Stub
  returning `""` (the read-failure value) → none. Plus `test_last_assistant_text_reads_only_an_assistant_message`:
  monkeypatch `flowbench.watch.urllib.request.urlopen` with a fake context manager whose body
  is `{"data": [item]}` — an assistant message item carrying the banner → the banner text;
  a `role: user` message item carrying the banner → `""`; a `type: function_call` item →
  `""`; and `test_last_assistant_text_read_failure_is_empty`: `urlopen` raising `OSError`
  → `""` (no raise).

## Task 4 — docs (AC7)

Files: `docs/design/runner.md`, `docs/onboarding.md`.

- Send/retry table: append `| any status + the new text is a CLI limit banner | the
  subscription/rate wall, not a reply | report QUOTA with the banner as text; never re-sent |`.
  Precedence paragraph: one sentence — the banner check runs before every row (a FAILED +
  banner is not row 2), the driver prints one `[flowbench] quota:` line, the loop stops and
  `exit_status` is `quota`, the watcher prints `QUOTA: …`.
- `TurnStatus` table: append `| QUOTA | the CLI's limit banner was the turn's only output |
  _send_once |`. Sentence after the `stalled` paragraph: `quota` is `is_quota_banner` in
  `transcript.py` (anchored, ≤ 240 chars), the only signal the server gives.
- `docs/onboarding.md:181` watcher line: add `QUOTA (…)` to the listed anomaly kinds.

## Traceability

| AC | task | test |
| --- | --- | --- |
| AC1 | 1 | `test_types.py::test_members_are_their_values` |
| AC2 | 1 | `test_transcript.py::test_is_quota_banner[...]` |
| AC3 | 2 | `test_failed_with_a_quota_banner_is_quota_not_flaked`, `test_idle_with_a_quota_banner_is_quota`, `test_non_failed_statuses_are_never_resent[QUOTA]` |
| AC4 | 2 | `test_failed_with_new_text_is_a_flaked_idle` (unchanged) |
| AC5 | 3 | `test_loop.py::test_loop_stops_on_quota` |
| AC6 | 3 | `test_watch.py::test_run_watch_quota_banner_once`, `test_last_assistant_text_reads_only_an_assistant_message`, `test_last_assistant_text_read_failure_is_empty` |
| AC7 | 4 | diff review (docs) |
| V4 | ship | live `coding_workflow` `todo_app` run on the merged SHA |
