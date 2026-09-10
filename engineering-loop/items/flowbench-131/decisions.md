# Decisions — flowbench #131 (quota banner read as a reply)

1. **New `TurnStatus.QUOTA = "quota"`, not `STALLED` + `stall_reason=quota`.** `STALLED` is the
   watchdog's word for a *running* session that is stuck (a prompt nobody can answer, no
   heartbeat) and carries `pane_tail`. A quota banner is the opposite shape: the turn
   *completed* (the CLI emitted an item, the server went idle/failed) and the agent is not
   stuck — the wall lifts on its own at a stated time. The operator action differs too
   (wait vs. look at the pane), and `exit_status` in `session.json`/`run.json` must say
   which without a second field. `StrEnum` keeps it a plain `"quota"` string on disk.
2. **Recognition is a text rule in `transcript.py`**, next to `is_control_message`: pure,
   shared by the driver and the watcher, testable from the captured banner. The server
   gives no other signal — in the evidence run every `omnigent.last_task_error_*` label is
   `""` and the item is an ordinary `role=assistant` `output_text` (`session.json`, last items).
3. **Banner strings.** Claude Code (evidence, verbatim): `You've hit your session limit ·
   resets 6:40pm (Europe/Zurich)`. The rule anchors on the message start and caps the
   length so an agent *talking about* a limit mid-reply is never a banner. Covered
   families: `You've/You have hit/reached your … limit`, and `… limit reached` (Claude
   Code's `Claude usage limit reached` / `5-hour limit reached`, Codex CLI's `You've hit
   your usage limit`). Only the first is evidence-backed; no codex-native banner exists in
   any run dir or in the installed omnigent package (grepped), so the codex family is
   documented as unverified. New wording → extend the one regex.
4. **The banner check precedes every row of the send/retry table.** A banner as the new
   assistant text is `QUOTA` whatever the server status (idle, failed, or cap-hit): a
   FAILED + banner would otherwise be row 2 (flaked idle, the bug); an IDLE + banner would
   be a clean reply. `QUOTA` is not `FAILED`, so `send()` never re-sends it (the wall says
   when it lifts; re-sending burns the quota that remains).
5. **`assistant_text` carries the banner verbatim.** The status is the signal; the text is
   the diagnostic (`SessionModel`'s error message shows it; the operator line prints it).
   Nothing downstream reads a `QUOTA` result's text as conversation: the loop stops on any
   non-idle status, `SessionModel` raises on it.
6. **One operator line, verbatim banner, printed where the banner is recognised** — the
   driver prints `[flowbench] quota: <banner>` to stderr, the same channel as `turn flaked`.
   The loop needs no print of its own: it records `exit_status: "quota"` in `session.json`
   and `run.json` `flow_stats`. The issue's `"quota: resets 6:40pm"` is the banner's own
   tail; parsing a reset time out of it would break on the first differently worded banner
   (codex says `Try again at …`), so the line is `quota: ` + the banner as emitted.
7. **The watcher reads the last item of each run session.** The sessions list carries no
   text, and `session.json` lands only for flow sessions (a quota hit in the simulator/judge
   session raises out of `SessionModel` before anything is written), so `RunWatch.tick`
   reads `GET /v1/sessions/{id}/items?limit=1&order=desc` per run session (localhost, ≤ 6
   sessions, one small call each per tick) and prints `QUOTA: <title> (<id>) <banner>` once
   per session, like `SESSION FAILED`.
8. **Simulator/judge quota is not handled beyond the status.** `SessionModel.generate`
   already raises on any non-idle result; with `QUOTA` the message names the status. A
   "wait for the reset and resume" policy is a run-level decision the issue does not ask
   for; the fix stops the burn and names the cause.
9. **Live validation** is a normal `todo_app` run (V4: the send path changed); a real quota
   wall cannot be scheduled, so the banner path is proven offline from the captured text.
