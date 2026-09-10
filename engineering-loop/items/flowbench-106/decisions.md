# Decisions — flowbench #106 (E02 S02.6)

Q: Which sites are in scope? — Every `except Exception` in the engine repo that
`ruff check --select BLE001 src/ scenarios/` reports: `driver/omnigent.py`
(`_resend_allowed`, `_pane_tail`, `_context_tokens`, `close`), `transcript.to_jsonable`,
`watch.RunWatch._run_sessions`, and `todo_app/scorers.collect_code` (a bare
`# noqa: BLE001` with no reason). `run.py`'s two sites already carry a reasoned waiver
("isolate one flow's scorer, never abort the run") and stay. The `except Exception` inside
`acceptance.py` is program text the acceptance harness writes into the SUT, not a catch.
`_injection_undelivered` named in the issue is `_resend_allowed` since S02.3.

Q: Narrow or waive, per site? — Narrow when the failure shapes are enumerable and a
foreign exception means a driver/schema bug that must surface: the two label reads
(SDK status/body errors, transport, the read cap, a label value of the wrong type — the
whole read-and-interpret block sits inside the `try`, so "malformed server data" is a
fallback, not a raise; for `_resend_allowed` this moves `runner_error` with a null or
non-string message to `False`, the "unreadable label → no re-send" row
`docs/design/runner.md` already states — a blind re-send can double-deliver, so unknown
must never mean "retry"), `_run_sessions`
(urllib/JSON), `collect_code` (read/decode). Waive with a reason when swallowing is the
contract: `close` (teardown never masks the error that got us here), `_pane_tail` (a
watchdog probe spanning HTTP, JSON shape, tmux subprocess and timeout — a probe failure
must never abort the send it is observing; the stall decision already treats None as
"could not look") and `to_jsonable` (called per streamed event inside `_send_once`; its
docstring promises the capture survives whatever the client ships, and a recording
failure must not abort the turn being recorded — narrowing it would put a new abort on
the send path). Every site, narrowed or waived, logs the exception at DEBUG via
stdlib `logging` — silent by default, visible with `-o log_cli_level=DEBUG` or a handler.

Q: `_context_tokens` reads labels off any status code? — No longer: since S02.5 part 2
(1a6a714) both reads go through `sessions.get()`, which raises `OmnigentError` at >= 400
and on a non-object body, so the S02.3 bug class is closed by the SDK (a 3xx carrying a
complete Session is a successful read; that is the SDK's status contract, not ours to
tighten here). The two label reads share one exception tuple.

Q: Non-dict `labels` values (`[]`, `""`, `0`) — `False` or `True`? — Probed the installed
SDK (omnigent_client 0.2.0): `Session.from_dict` coerces missing/null/non-dict `labels` to
`{}`, so the driver sees "no labels" and row 3 applies (`True`). The driver cannot tell a
coerced list from an empty map; that is the SDK's contract and the test records it rather
than fights it. A partial Session body (JSON object without `agent_id`/`id`) raises
`KeyError` inside `from_dict`, which the tuple therefore includes; `from_dict` also runs
`int()` over numeric Session fields, so a `1e400` field raises `OverflowError` (probed),
as does `int()` of an `inf` token label — `OverflowError` stays in the tuple.
`AttributeError` is unreachable through the typed `Session` and dropped.

Q: A list/dict message containing "not delivered" — row 1? — No. Probed: `"not delivered"
in ["not delivered"]` is `True`, so today such a body authorizes a re-send. The undelivered
signal is a string the server writes; row 1 now requires `isinstance(msg, str)`. This is a
guard, not a catch, so it is not logged as a swallowed error.

Q: `omnigent_client` is the `live` extra — module-level import of `OmnigentError`? — No;
`omnigent_client` imports `omnigent.server.schemas`, which is why `start()` imports it
lazily. The tuple is built by `_label_read_errors()`, which does the same lazy import.

Q: Which live run? — `verification.md` V4 (`swe_planning`) is mandatory for a send-policy
change; the brief asks for a todo_app run (V5). Both, in sequence, after merge.

Q: Does narrowing a send-path catch count as a behaviour change needing a live run? —
Yes for `_resend_allowed`: a non-listed exception now propagates instead of returning
False. `_pane_tail` and `to_jsonable` — the other two catches `_send_once` reaches — are
waived, so nothing else on the send path changes. Plan Task 4 runs V4 + V5 after merge.

Q: HANDOFF.md mentions "sharpen the RUNNING-vs-TIMEOUT race at the cap" under S02.6. —
Out of scope: not in issue #106 nor the epic's S02.6 section, and changing which
`TurnStatus` the cap yields is a loop-semantics change the epic lists as a non-goal.
Left for the owner; flagged in the final report.

Q: Enable `BLE` in ruff? — Yes (`select` gains `"BLE"`), so the audit stays clean in
pre-commit; each waiver is `# noqa: BLE001 -- reason`.
