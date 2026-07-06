# Target architecture

The shape the epics converge on. Alpha rule applies: modules and names below are the
*target*, not a frozen API — but a PR that moves code should move it toward this layout,
and a PR that adds code should add it in the module that owns the concern.

## Design principles (carried over from what already works)

- **One module knows omnigent exists.** Everything omnigent-specific stays behind the
  `AgentDriver` seam; scenarios and tests inject fakes. This survived contact with reality
  and stays.
- **Failure is isolated, never propagated to the benchmark.** A flow with no scorecard is a
  FAILED column; a judge that can't be parsed is a labeled error, never a silent `{}`; a
  failing trial is a FAILED entry, not an aborted run.
- **Objective and subjective scores never mix.** Anything unmeasured is unscored, not a
  fake 0.
- **Plain files are the integration surface.** Orchestration writes `run.json`,
  `scorecard.json`, `transcript.md`, `session.json`; reporting and statistics are pure
  readers over those files.
- **Three roles, one runtime.** Flow (the session under test), simulator (the user side),
  and judge are all omnigent sessions driven through the same driver. No `claude -p`
  side-channel.

## Module map

```
src/flowbench/
  types.py           # TurnStatus enum, TurnResult, error taxonomy — no magic strings
  driver/
    __init__.py      # AgentDriver ABC (start/send/capture_session/close)
    omnigent.py      # OmnigentDriver: session lifecycle, send/settle, capture
    bundle.py        # agent-config rendering + skills/MCP tar bundle build
  transcript.py      # item text extraction, dedup, control-message filtering,
                     # markdown transcript rendering (shared by driver, scorers, reports)
  model.py           # SessionModel: async .generate(prompt) over any AgentDriver —
                     # how simulator and judge roles run (today: swe_planning's
                     # OmnigentModel, lifted)
  loop.py            # run_agent_session — the mediated DONE-token loop
  flowspec.py        # Flow schema: name, harness, skills, skill_dirs, mcp_files,
                     # model, reasoning_effort, prepend, append, turn_timeout_s;
                     # flows.yaml loader with validating errors
  case.py            # case-dir loader: task.md, simulator.md, knowledge.md, judge.md,
                     # flows.yaml (+ optional fixtures/, python hooks)
  judge.py           # comparative judging: prompt assembly, WINNER/SCORES tail parsing,
                     # label rotation for position bias (today: swe_planning helpers)
  run.py             # run_case / run_case_n orchestrator; run-dir layout; run.json v1
  report/
    compare.py       # side-by-side comparison; metric rows discovered from the
                     # scorecards, not hardcoded
    run_report.py    # per-run and aggregate markdown reports (today: swe_planning
                     # report.py, generalized)
  watch.py           # live-run debug watcher (today: swe_planning watch.py, lifted)
  testing.py         # FakeDriver, scripted simulator, canned judge — public test doubles
  cli.py             # flowbench run | compare | watch
```

What disappears:

- `runner/subscription_model.py` and the `inspect-ai` dependency, entry-point block, and
  todo_app's `eval.py`/`solver.py` glue (E01).
- `scripts/patch_omnigent.py`, once the prompt-scan fix is upstream (E02).
- The top-level `scenarios` package from the wheel — the engine wheel ships `flowbench`
  only; the reference scenario stays in-repo as content, imported by path/tests, not
  installed into site-packages.

## The run, end to end

```
case dir                          run dir (../flowbench-runs/<scenario>/<run-id>/)
  task.md        ─┐                 <flow>/            workspace + plan/artifacts
  simulator.md    │   run_case        transcript.md    human-readable dialog
  knowledge.md    ├────────────►      session.json     raw capture
  judge.md        │                 _sim_<flow>/       simulator session dir
  flows.yaml     ─┘                 _judge/            judge session dir
                                    judge.md           prose + WINNER/SCORES tail
                                    run.json           versioned metadata
                                    report.md          pure reader over the above
```

1. `case.py` loads the case; `flowspec.py` loads and validates the flows.
2. For each flow, `run.py` spawns the flow session (driver) and a fresh simulator session
   (`SessionModel`), composes the kickoff (`prepend + task + append`, one message), and
   runs `loop.run_agent_session` until the simulator emits the done token or a budget ends
   the run. The loop's contract: only an `idle` turn is a clean boundary; self-wait turns
   (agent parked on its own busy sub-agent) get capped free nudges.
3. Artifacts, transcript, and raw session land in the flow's subfolder as plain files.
4. The judge runs as a one-shot session over all flows' transcripts + artifacts, with
   letter labels assigned per trial rotation; the verdict tail is parsed leniently
   (missing tail → winner `unknown`, prose kept).
5. `run.json` (schema v1, versioned) records flows, labels, rotation, winner (letter and
   name), scores, and per-flow stats (`exit_status`, `turns`, `duration_s`,
   `context_tokens`).
6. Reports and comparisons are generated by readers over the run dir, never during
   execution.

## Contracts to make explicit (today they are conventions)

- **TurnStatus**: `idle | failed | timeout` as an enum; `TurnResult` fully typed. The
  driver's send contract, documented in one place: a `failed` status with fresh assistant
  text is a delivered-then-flaked turn (trust the text); an undelivered injection is
  retried after a wait; `timeout` is never retried (injecting into a busy terminal kills
  sessions). Today this policy is split between `OmnigentDriver.send` and downstream
  `OmnigentModel.generate` — it becomes ONE policy at the driver layer (E02).
- **run.json / scorecard.json schema v1** with a `schema_version` field and a written
  schema doc. Readers tolerate additive change; breaking change bumps the version.
- **The simulator seam**: any object with `async generate(prompt) -> .completion`. Kept
  duck-typed on purpose (a Protocol in `types.py` names it without freezing it).
- **The artifact concern moves out of the driver.** `artifact_name="__none__"` for
  simulator/judge sessions is the current leak. The driver owns the workspace; the
  orchestrator (loop/run) owns "which file proves delivery", passed as a probe callable.

## Scenario contract

A scenario is a directory of cases plus optional Python:

- Content: one dir per case with the plain files above. Editing behavior = editing files.
- Code: optional `scorers.py`/`acceptance.py` importing only the flowbench public API
  (`flowbench.run`, `flowbench.transcript`, `flowbench.judge`). Scenario-local code stays
  in the scenario dir until a second scenario shares it — then it moves to the engine
  (that trigger already fired once: swe_planning's orchestrator is E01's extraction).
- The open reference scenario (`scenarios/coding_workflow/`) lives in this repo;
  proprietary scenarios live in a downstream repo depending on flowbench.

## Omnigent upstream wishlist

The runtime's fragile parts are all workarounds for missing omnigent contract; each has an
epic story to push the fix upstream rather than harden the workaround:

1. **Delivery acknowledgement / turn-completion events.** The settle loop, `min_wait`,
   lying-idle detection, and freshness sentinels all exist because "idle" can be observed
   mid-turn and an injection can silently not land. A server-confirmed "message delivered /
   turn complete" signal deletes most of `_send_once`'s heuristics.
2. **Prompt-scan window** (`_PROMPT_SCAN_TAIL_LINES`): the `scripts/patch_omnigent.py`
   monkey-patch, upstreamed.
3. **Public client API for what we reach into**: `sessions._http`, `sessions._base`, and
   constructing `SessionsChat` by hand are private-API reach-ins that break on any
   omnigent-client bump (it is pinned 0.1.1 for exactly this reason).
4. **Per-session tool restriction** in the bundle config, so the simulator can be denied
   shell/file tools (today the mitigation is prompt-only).
5. **Cost fields on the session** (`last_context_tokens` exists as a label; a stable field
   with input/output token totals would feed the cost column in comparisons).
