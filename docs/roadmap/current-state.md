# Current state (2026-07-06)

What exists, what works, what is debt. Line counts are `wc -l` on that date.

## Inventory

**Engine** (`src/flowbench/`, ~1,060 lines on 2026-07-06; ~2,100 after S01.1 on 2026-09-07):

| Module | Lines | Role |
| --- | --- | --- |
| `driver/omnigent.py` | 484 | `OmnigentDriver`: session lifecycle, send/settle/retry, capture, URLs, `git_init_repo` (S02.2). Above the epic's ~350 target: #68/#76 grew the settle machinery after the epic was written, and S02.3 is where the rest goes — see E02 S02.2 |
| `driver/bundle.py` | 142 | `render_config` / `build_bundle` / `session_metadata` as pure functions of a `BundleSpec` protocol (S02.2) |
| `driver/base.py` | 34 | `AgentDriver` ABC (S02.2) |
| `driver/__init__.py` | 29 | the package's public surface |
| `runner/driver.py` | 24 | compat re-export, one release (S02.2) |
| `runner/loop.py` | 22 | compat re-export, one release (S02.2) |
| `types.py` | 57 | `TurnStatus` (`StrEnum`), `TurnResult`, `UserModel`/`Completion` protocols — the engine's turn-outcome vocabulary (S02.1) |
| `run.py` | 311 | `run_case`/`run_case_n` orchestrator + omnigent factories (S01.1, lifted from swe_planning) |
| `report/run_report.py` | 259 | run dir → report.html, single + aggregate (S01.1) |
| `testing.py` | 112 | offline doubles: FakeDriver, StubSim, ScriptedDriver, n_run_factories (S01.1) |
| `watch.py` | 100 | `RunWatch` live-run anomaly scanner (S01.1) |
| `transcript.py` | 106 | message-item helpers + `render_transcript` (S01.1) |
| `model.py` | 52 | `SessionModel` simulator/judge shim: one `send`, raise on a non-idle or empty turn, wrap |
| `flowspec.py` | 36 | flows.yaml loading, kickoff composition (S01.1) |
| `loop.py` | 110 | mediated DONE-token loop (no nudges since #67: the driver waits out busy children); moved out of `runner/` in S02.2 |
| `report/compare.py` | 91 | side-by-side scorecard table; metric paths hardcoded to todo_app's schema |
| `cli.py` | 36 | typer app; `compare` is the only command |
| `runner/judge.py` | 142 | `last_json_object` (string-aware) + prose verdict/scores parsing, aggregation (S01.1) |
| `runner/flow.py` | 34 | frozen `Flow` dataclass (bundle fields only) |

`runner/run_dir.py` (47 lines, run-dir prep + JSON output writers) is gone as of S01.3 — it
served only the Inspect solver; `run_case` writes the run dir directly.

**Reference scenario** (`scenarios/coding_workflow/cases/todo_app/`, S01.3): runs through
`run_case`/`run_case_n` like every other scenario (no more Inspect `@task`/solver glue,
no `claudesub`). Plain-text `task.md`/`simulator.md`/`knowledge.md`/`flows.yaml`; each flow
is scored on its own (no comparative judge) via `scoring.py`'s `score_flow` hook —
keyword-based clarifying-coverage scoring, subprocess black-box acceptance, JSON judge —
into `<flow>/scorecard.json`.

**Tests** (~1,360 lines): driver config/bundle/send-retry units, loop behavior, scorer
units against canned sessions, acceptance checks against fixture apps, compare rendering.
Live tests are opt-in (`RUN_LIVE_AGENT=1`).

**Downstream** (`flowbench-scenarios`, private): the migration-scoring harness
(`dwh_migration`) and the `swe_planning` scenario, which built its own generic
orchestration on top of the engine — see "Downstream duplication".

## What already works well (keep, don't churn)

- **The driver seam.** "One module knows omnigent exists" held up: scenarios and tests
  inject fakes; swapping the meta-harness later would touch one module.
- **Failure isolation.** Missing scorecard → FAILED column; unparseable judge → labeled
  error; the benchmark never aborts on one bad flow.
- **The war-story comments.** `driver.py`/`loop.py` encode ~10 live incidents (lying
  idle, undelivered injection, double-capture, subagent self-wait, empty grader
  completion, late artifact flush). This is real operational knowledge; treat it as
  load-bearing (E00 pins each with a regression test).
- **Plain-file seams.** Run dirs already hold everything reporting needs; `compare` and
  the downstream reports are pure readers.
- **Comparability discipline.** Identical launch flags for every flow, no per-flow
  steering, bundle-only variation — the scientific core of the tool.

## Structural debt (each has a home in the roadmap)

1. **The generic runtime lives downstream.** `run_case`/`run_case_n`, the session-backed
   `.generate()` model, judge prompt/verdict/scores parsing, transcript rendering, trial
   rotation, aggregation, report rendering, and the run watcher are all in
   flowbench-scenarios' swe_planning dir. The recorded extraction trigger ("a second
   scenario forces extraction") fires with the todo_app port. → E01
2. **Driver god-module + abstraction leaks.** Bundle building and transcript utilities
   don't belong in the session driver. → S02.2
3. **Private-API reach-ins.** `sessions._http`, `sessions._base`, hand-built
   `SessionsChat`, `omnigent.host.daemon_launch` internals. The 0.1.1 pins exist because of
   this — and the driven server runs from a far newer source checkout, so the pinned client
   and the live server are different versions on purpose
   (`docs/onboarding.md` §2). → S02.5
4. **Magic strings as contracts.** Turn statuses, omnigent label keys, control-message
   prefixes. → S02.1
5. **Engine knows one case's scorecard.** `report/compare.py`'s `_METRICS` hardcodes
   todo_app paths (`judge_low_confidence`, `superpowers_used`); swe_planning doesn't use
   `compare` at all. → S03.5
6. **`Flow` diverged from reality.** The dataclass carries bundle fields only; the
   downstream flows.yaml adds `model`, `reasoning_effort`, `prepend`, `append`,
   `turn_timeout_s` and is passed around as raw dicts. → S03.1
7. **No `flowbench run`.** Each scenario has its own argparse `__main__`; the engine CLI
    only compares. → S03.2 (#137)
8. **Un-versioned metadata.** `run.json`/`scorecard.json` are convention, no
    `schema_version`; readers guess. → S03.4
9. **Naming/docstring drift.** "An flow" (`flow.py`), "{arm_name:" (`compare.py`,
    retired vocabulary), `OMNIGENT_PROBE_MODEL` (pre-flowbench probe era). Typical
    weak-model session residue: the code moved on, the prose didn't. → S00.1
10. **Broad exception swallowing.** `close()`, `_context_tokens()`,
    `_resend_allowed()`, `transcript.to_jsonable()` catch `Exception` silently. Correct for
    teardown, unjustified elsewhere. → S02.6
11. **Terminal-scraping fragility (systemic).** Idle detection via tmux pane scraping,
    settle loops, `min_wait=4.0`, poll intervals — all downstream of omnigent lacking
    delivery acks/turn events. Hardening has diminishing returns; the fix is upstream
    (wishlist in `target-architecture.md`). → S02.5 + upstream

## Audited findings

Code-review findings verified against the code (2026-07-06), beyond the structural debt
list above:

**Bugs**

- `acceptance.py:111` — `resolve_invoker` gates its console-script fallback on the exact
  CPython error string `"No module named todo.__main__"`. An app shipping *only* a
  console script (no `todo` module at all) produces `"No module named todo"`, misses the
  gate, and fails every acceptance check despite being a faithful build. Split out of
  S01.3 into its own issue (flowbench #46) — unrelated to the port, needs its own fixture
  app.
- `runner/judge.py:18` — `last_json_object` counts braces without string-awareness; a
  judge rationale containing `{` or `}` inside a JSON string mis-slices the object. Fix
  when the parser moves in S01.1.
- (fixed, flowbench #67) the `Continue.` nudge relay pollution and the cumulative
  `any_child_busy` fold: the driver now waits out busy children (`/child_sessions`, paged)
  and the loop never nudges; `_list_items` pages past the 200-item cap.

**Test gaps** (fold into S00.3's table)

- `OmnigentDriver.start()` is entirely untested — including the `ANTHROPIC_API_KEY`
  subscription guard, the one safety check the repo calls non-negotiable.
- `_wait_idle` (the lying-idle heuristic that killed live runs) has no direct test; the
  settle tests deliberately stub around it.
- The loop's `deadline_s` backstop is never exercised.
- The scorecard key set is pinned offline (`tests/scenarios/todo_app/test_todo_run.py`) and
  `compare` renders a `run_case`-written run in `tests/test_run.py`; values themselves are
  only exercised live.

**Scoring credibility** (scenario-side; matters because scores are the product)

- `detect_phases` marks `brainstormed` true on *any* question mark anywhere in assistant
  text; phase markers are substring-matched across the full transcript, so simulator
  prose and skill *names* count as agent behavior.
- Several `clarifying_coverage` keywords are generic enough to inflate coverage
  (`"format"`, `"location"`, `"path"`).
- Scoring quality gets no dedicated epic — it is scenario content, revisited per-scenario
  when porting (S01.3) — but reviewers of results should know today's numbers lean on
  keyword heuristics; the objective anchors are `acceptance` and `skills_invoked` (real
  tool calls), which are sound.

## Capability gaps against the long-term goal

Beyond code debt — things the engine simply does not have yet, driving the later
milestones: flow portability (a flow definition you can pin, version, and share across
scenario repos), multi-stage flows (the ADF X-Lens → X-Port chain), sandboxing (runs
execute with `bypassPermissions`, `sandbox: none`, caller-process env — the benchmarked
agent can touch the host), audit trail (tool calls are captured in `session.json`, but
there is no first-class "what did the agent DO" record: commands run, files touched,
network egress), reproducibility manifest (model/harness/skills/omnigent versions are
partially captured, not as a re-runnable pin set), and statistics (single trial per
flow-case is the norm today).
