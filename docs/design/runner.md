# Runner design

The engine's execution core is `driver.py` + `loop.py`; `run.py` orchestrates a case
on top of them. Scenarios own content and scenario-specific scoring only.

## driver.py — the ONE module that knows omnigent exists

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

A flow's skills never load from the host `~/.claude`. `OmnigentDriver._build_bundle`
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

## loop.py — the mediated DONE-token loop

`run_agent_session(driver, user_model, *, first_prompt, simulator_system,
done_token, max_turns, deadline_s)`:

- Only an `idle` turn is a clean boundary; `failed`/`timeout`/`running`/`stalled`
  stops the loop and scores what was built. `stalled` is the driver's watchdog
  (`stall_s`, default 300 s): a `running` session waiting on a human (a pending
  elicitation, a pending input, or `terminal_pending` — permission, policy,
  trust or login prompt nobody can answer) ends the turn at once as `prompt`; one whose
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
  (plus one quiet poll, so the inject doesn't land on the task-notification wake-up).
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
| `model.py` | `SessionModel`: `.generate(prompt)` shim over one persistent omnigent session (simulator + judge); freshness-retry policy for the terminal-readiness flake |
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
