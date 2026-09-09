# Runner design

The engine's execution core is `flowbench/driver/` + `flowbench/loop.py`; `run.py`
orchestrates a case on top of them. Scenarios own content and scenario-specific
scoring only.

## flowbench/driver/ — the ONE package that knows omnigent exists

Split out of the old `runner/driver.py` in E02 S02.2. `flowbench.runner.driver`
and `flowbench.runner.loop` re-export the old names for one release.

| Module | Holds |
| --- | --- |
| `base.py` | `AgentDriver` ABC |
| `bundle.py` | `render_config` / `build_bundle` / `session_metadata` — pure functions of a `BundleSpec` |
| `omnigent.py` | `OmnigentDriver`: lifecycle, send/settle, capture, URLs, `git_init_repo` |

- `AgentDriver` (ABC): `start / send / capture_session / artifact_path / close`.
  All spawning goes through implementations of this seam; scenarios and tests
  inject fakes.
- `OmnigentDriver`: spawns a vanilla-Claude-Code agent as an omnigent session
  (HTTP + `omnigent_client`), per-session `model`, `reasoning_effort`,
  `harness`, `skills`, `cwd`. Guards `ANTHROPIC_API_KEY` UNSET (subscription
  billing). `close()` leaves the omnigent session/runner/tmux alive on purpose
  — a human resumes via `conversation_url`; only HTTP clients are closed.
- `capture_session()` returns plain data: `items`, `events`, `duration_s`,
  `artifact_*`, `model`, `session_id`, `conversation_url`.

### Where a flow's skills live at run time

A flow's skills never load from the host `~/.claude`. `flowbench.driver.bundle.build_bundle`
copies them into a per-flow tarball, POSTs it to omnigent, and the agent loads them from
there (`--plugin-dir`); with `skills: "none"` the host skills are hidden. That is what
makes a flow identical on any machine.

```mermaid
flowchart LR
  subgraph src[Sources on disk]
    sp[superpowers plugin dir]
    own[our skill dirs<br/>each with SKILL.md]
    mcp[per-flow MCP yaml]
  end
  f[Flow: harness, skills filter,<br/>skill_dirs, mcp_files]
  subgraph bundle[agent.tar.gz, built per flow]
    cfg[config.yaml<br/>harness, skills: none]
    sk[skills/&lt;name&gt;/SKILL.md]
    tm[tools/mcp/*.yaml]
  end
  subgraph sess[omnigent session]
    cli[claude CLI, vanilla<br/>--plugin-dir → bundle skills<br/>host ~/.claude skills hidden]
    ws[workspace/ = run dir/&lt;flow&gt;/]
  end
  sp & own --> sk
  mcp --> tm
  f --> cfg
  bundle -- POST --> sess
  cli -- reads/writes --> ws
```

Baseline is the same picture with an empty `skills/`. Nothing else changes.

### Send/retry policy

`OmnigentDriver.send` is the only place that decides whether a turn is re-sent; callers —
the loop, `SessionModel`, scripts — read `TurnResult.status` and never re-derive it.

| Observation | Meaning | Action |
| --- | --- | --- |
| `FAILED` + label says undelivered | injection never landed | wait, re-send same text (bounded) |
| `FAILED` + new assistant text | turn completed, then flaked | trust the text, no retry |
| `FAILED`, no label, no new text | unknown; likely undelivered | bounded re-send (the #39 behavior, generalized) |
| `TIMEOUT` | may be mid-turn after delivery | NEVER retry (injecting into a busy terminal kills sessions) |
| `IDLE` + no new text past settle budget | lying idle | report `TIMEOUT` |

Precedence and mechanics: "new assistant text" is checked first, so row 2 never reads a
label; a new reply is `transcript.new_assistant_text(items, n_before)` — a NON-EMPTY
assistant message beyond the count taken before the inject (an empty new message is not
a reply; it would let an older one pass as this turn's). Rows 1 and 3 are decided by one
label read in `_resend_allowed`: no error code, or `runner_error` + "not delivered" →
re-send; any other present code (a delivered failure such as `model_error`), or an
unreadable label → no re-send. A row-2 turn returns as `status=IDLE, flaked=True` and
prints one `[flowbench] turn flaked` line; the loop counts them into
`session["flaked_turns"]`.

**One wall-clock budget per send.** `deadline = now + turn_timeout_s`, taken once at the
top of `send`; `_wait_idle`, the settle loop and the retry sleeps all draw it down, a
re-send happens only while the remaining budget exceeds `send_retry_wait_s`, and every
inject is preceded by a deadline check. The whole send also runs under
`asyncio.timeout(turn_timeout_s)`, so a server call, back-off, label read, retry sleep or
the synchronous `artifact_path()` (run via `asyncio.to_thread`) still in flight at the cap
is cancelled and the send reports `TIMEOUT` with empty text and `artifact_exists=False`
("not observed"). At the cap the status is `RUNNING` (or an undocumented server status,
verbatim) if the soft loop got there first, `TIMEOUT` if the timer did — both mean the
turn did not finish. Before S02.3 a send stacked a `turn_timeout_s` in `_wait_idle`, a
second one as the settle window and a third in that window's last `_wait_idle`, times
`1 + send_retry_attempts`: `(1 + 3) × 3 × turn_timeout_s + 3 × send_retry_wait_s`, 2 970 s
at the driver defaults and 36 090 s on todo_app's 3 000 s turn cap inside a 3 600 s run.

## loop.py — the mediated DONE-token loop

`run_agent_session(driver, user_model, *, first_prompt, simulator_system,
done_token, max_turns, deadline_s)`:

- Only an `idle` turn is a clean boundary; any other `TurnStatus` stops the loop
  and scores what was built. The vocabulary lives in `flowbench/types.py`:

  | member | meaning | produced by |
  | --- | --- | --- |
  | `IDLE` | turn settled: the agent is awaiting the user | omnigent server |
  | `RUNNING` | still mid-turn when the per-turn cap fired | omnigent server |
  | `FAILED` | the omnigent session reported failed | omnigent server |
  | `TIMEOUT` | idle but silent, or the send's budget expired | `send` / `_send_once` |
  | `STALLED` | a prompt nobody can answer, or no heartbeat | `_send_once` |

  `stalled` is the driver's watchdog
  (`stall_s`, default 300 s): a `running` session waiting on a human (a pending
  elicitation or `terminal_pending` — permission, policy, trust or login prompt nobody
  can answer; NOT `pending_inputs`, which is our own queued message) ends the turn at once as `prompt`; one whose
  `updated_at` heartbeat is silent for `stall_s` ends it as `no_progress`. The
  session records `exit_status`, `stall_reason` and `pane_tail` (the terminal's
  last lines, i.e. the question it is stuck on). The watchdog never answers the
  prompt: a benchmark that resolves its own prompts measures the harness, not
  the flow. `flowbench.watch` prints `STALLED (...)` on the same signals.
- The simulator is any `user_model` with `async generate(prompt)`; the loop
  composes `simulator_system` + conversation tail per call.
- An idle main agent with a busy sub-agent (`GET /v1/sessions/{id}/child_sessions`,
  per-child `busy`) is still mid-turn: the driver keeps waiting, with the children's
  `updated_at` folded into the heartbeat, and reports `idle` only once no child is busy
  and, once children have cleared, only after the task-notification wake-up turn has run
  (or `child_wake_s`, 20 s, has passed) so the inject never queues behind it.
  The loop therefore never nudges; every idle turn is a real hand-over to the simulator.
  (#67 — the old "Continue." nudge burned turns and items, and its sentinel collided
  with a simulator that itself answered "Continue.", freezing the relay cursor.)
- `_list_items` pages past the server's 200-item cap (#4/#67): an unpaginated read
  froze the settle check once a session outgrew one page, and every later turn burned
  the whole turn cap.
- **The loop closes the driver itself** (finally). Callers close only their
  simulator.

## run.py — the `run_case` orchestrator (since S01.1)

`run_case(case_dir, *, run_id, runs_root, scenario, make_flow_driver, make_simulator,
run_judge, done_token=DONE_TOKEN, score_flow=None, ...)`: for each flow spawn a driver +
simulator, run the loop (against `done_token`, a per-case override — todo_app's is
`<<DONE>>`), write `<run_root>/<flow>/{plan.md,transcript.md,session.json}`, then (since
S01.3) judge all flows in one shot and write `run.json` + `report.html` — but ONLY if
`case_dir/judge.md` exists. A case with no `judge.md` (a build-shaped case like todo_app,
scored per-flow rather than comparatively) skips the judge stage entirely: no `_judge/`
dir, no `report.html`, `run.json`'s `winner`/`winner_flow` are `None`. In that shape
`score_flow(flow, flow_dir, session) -> dict`, when given, runs after each flow's own
session and its result is written to `<flow_dir>/scorecard.json`; a raised exception is
caught and recorded as `{"error": ...}` (plus `flow_stats[name].score_error`) rather than
aborting the run — `report/compare.py` reads that shape as a FAILED column with the
reason. `run_case_n` repeats `run_case` with the flow list rotated per trial (cancels
judge position bias) under `trial-XX/` and aggregates; with no judge across all trials the
aggregate is `{"counts": {}, "winner": None}` rather than tallying `None` as a flow name.
The three factories are injected so the whole pipeline runs offline against
`flowbench.testing` doubles; `omni_factories(scenario, *, artifact_name: str | None =
"plan.md", git_init=False)` returns the real ones (todo_app binds
`artifact_name=None` — no artifact, the deliverable is the running app, judged
black-box by `acceptance.py` — and `git_init=True`). `artifact_name=None` propagates
through `run_case`/`run_case_n`: no `<flow>/plan.md` is written, no
`artifact_missing`/`artifact_lines` keys appear in `run.json`, and the artifact
grace-poll is skipped. `flowbench.run.rescore_run(case_dir, run_root, *, score_flow)`
re-runs a case's `score_flow` over an existing run dir's `<flow>/session.json` files
— no new session, `session.json`/`transcript.md` untouched — for the CLI's
`--rescore`.

Supporting modules, all omnigent-free at import time:

| Module | Role |
| --- | --- |
| `model.py` | `SessionModel`: `.generate(prompt)` shim over one persistent omnigent session (simulator + judge); send, raise on a non-idle or empty result, wrap the completion |
| `flowspec.py` | `load_flows` (flows.yaml, resolves `skill_dirs`), `compose_kickoff` (prepend + task + append) |
| `runner/judge.py` | `parse_verdict`/`parse_scores` for the prose `WINNER:`/`SCORES X:` tail, `build_judge_prompt`, `aggregate_*`, `last_json_object` for JSON judges |
| `transcript.py` | message-item helpers shared by driver and reports (`item_text`, `dedup_items`, ...) + `render_transcript` |
| `report/run_report.py` | run dir → self-contained `report.html` (single run and aggregate) |
| `watch.py` | `RunWatch`: incremental anomaly scanner over a live run (omnigent log + run dir) |
| `testing.py` | `FakeDriver`, `StubSim`, `MissingPlanDriver`, `ScriptedDriver`, `n_run_factories` |

Case-shaped constants (`MISSING_PLAN`, `SIM_MODEL`, `JUDGE_MODEL`) are still module
constants of `run.py`; `DONE_TOKEN` and the flow driver's `artifact_name`/`git_init` are
now per-call overrides (S01.3), defaulting to swe_planning's values. CLI entrypoints
(`main`) stay scenario-side until S03.x.

## One execution model

Scenarios run through the engine's `run_case` orchestrator — not through Inspect
(true for both scenarios as of S01.3, todo_app's port; the Inspect-based path was
removed entirely in S01.4).
Decision record: flowbench-scenarios
`docs/superpowers/specs/2026-07-02-swe-planning-rework-design.md` (execution
model + framework strategy + reconsider-triggers).

## Seams are plain files

Run folders (`../flowbench-runs/...`) hold `run.json`, `scorecard.json`,
transcripts. Future tooling (reports, stats, even an Inspect log exporter for
`inspect view`) reads these files; it never wraps execution.
