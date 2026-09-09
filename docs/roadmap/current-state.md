# Current state (2026-07-06)

What exists, what works, what is debt. Line counts are `wc -l` on that date.

## Inventory

**Engine** (`src/flowbench/`, ~1,060 lines on 2026-07-06; ~2,100 after S01.1 on 2026-09-07):

| Module | Lines | Role |
| --- | --- | --- |
| `runner/driver.py` | 575 | `AgentDriver` ABC, `OmnigentDriver` (session lifecycle, send/settle/retry, capture), bundle building, git-init — four concerns in one file (transcript helpers moved out in S01.1; `TurnResult`/`TurnStatus` moved to `types.py` in S02.1, re-exported here) |
| `types.py` | 57 | `TurnStatus` (`StrEnum`), `TurnResult`, `UserModel`/`Completion` protocols — the engine's turn-outcome vocabulary (S02.1) |
| `run.py` | 311 | `run_case`/`run_case_n` orchestrator + omnigent factories (S01.1, lifted from swe_planning) |
| `report/run_report.py` | 259 | run dir → report.html, single + aggregate (S01.1) |
| `testing.py` | 112 | offline doubles: FakeDriver, StubSim, ScriptedDriver, n_run_factories (S01.1) |
| `watch.py` | 100 | `RunWatch` live-run anomaly scanner (S01.1) |
| `transcript.py` | 89 | message-item helpers + `render_transcript` (S01.1) |
| `model.py` | 78 | `SessionModel` simulator/judge shim with freshness retry (S01.1) |
| `flowspec.py` | 36 | flows.yaml loading, kickoff composition (S01.1) |
| `runner/loop.py` | 134 | mediated DONE-token loop (no nudges since #67: the driver waits out busy children) |
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

1. ~~Two execution models coexist.~~ **Resolved (S01.3, S01.4):** todo_app now runs
   through `run_case`/`run_case_n` (`done_token` + an optional per-flow `score_flow`
   hook, comparative judge conditional on `judge.md`), the same orchestrator swe_planning
   uses; `subscription_model.py` and the `inspect_ai` entry point are gone, and the
   omnigent install extra is renamed to `live`. → E01
2. **The generic runtime lives downstream.** `run_case`/`run_case_n`, the session-backed
   `.generate()` model, judge prompt/verdict/scores parsing, transcript rendering, trial
   rotation, aggregation, report rendering, and the run watcher are all in
   flowbench-scenarios' swe_planning dir. The recorded extraction trigger ("a second
   scenario forces extraction") fires with the todo_app port. → E01
3. **Split retry policy.** `OmnigentDriver.send` retries label-confirmed undelivered
   injections; downstream `SessionModel.generate` separately retries failed-with-stale-
   text turns (issue #39) because sim/judge sessions don't reliably set delivery labels.
   Two policies, two repos, same underlying problem. → S02.3
4. **Driver god-module + abstraction leaks.** Bundle building, transcript utilities, and
   artifact probing (`artifact_name="__none__"` for sessions with no artifact) don't
   belong in the session driver. → S02.2, S02.4
5. **Private-API reach-ins.** `sessions._http`, `sessions._base`, hand-built
   `SessionsChat`, `omnigent.host.daemon_launch` internals. The 0.1.1 pins exist because of
   this — and the driven server runs from a far newer source checkout, so the pinned client
   and the live server are different versions on purpose
   (`docs/onboarding.md` §2). The `scripts/patch_omnigent.py` monkey-patch is gone (fixed
   upstream, 2026-09-09). → S02.5
6. **Magic strings as contracts.** Turn statuses, omnigent label keys, control-message
   prefixes. → S02.1
7. **Engine knows one case's scorecard.** `report/compare.py`'s `_METRICS` hardcodes
   todo_app paths (`judge_low_confidence`, `superpowers_used`); swe_planning doesn't use
   `compare` at all. → S03.5
8. **`Flow` diverged from reality.** The dataclass carries bundle fields only; the
   downstream flows.yaml adds `model`, `reasoning_effort`, `prepend`, `append`,
   `turn_timeout_s` and is passed around as raw dicts. → S03.1
9. ~~**Packaging.**~~ **Resolved (S01.4):** the wheel ships `src/flowbench` only (no
   top-level `scenarios` package in site-packages); the omnigent extra is renamed
   `live`; `inspect-ai` is gone. → E01
10. **No `flowbench run`.** Each scenario has its own argparse `__main__`; the engine CLI
    only compares. → S03.3
11. **Un-versioned metadata.** `run.json`/`scorecard.json` are convention, no
    `schema_version`; readers guess. → S03.4
12. **Naming/docstring drift.** "An flow" (`flow.py`), "{arm_name:" (`compare.py`,
    retired vocabulary), `OMNIGENT_PROBE_MODEL` (pre-flowbench probe era). Typical
    weak-model session residue: the code moved on, the prose didn't. → S00.1
13. **Broad exception swallowing.** `close()`, `_context_tokens()`,
    `_injection_undelivered()`, `_to_jsonable()` catch `Exception` silently. Correct for
    teardown, unjustified elsewhere. → S02.6
14. **Terminal-scraping fragility (systemic).** Idle detection via tmux pane scraping,
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
- `driver.py:455` — nested timeout budgets: `_send_once` waits up to `turn_timeout_s` in
  `_wait_idle`, then opens a *second* `turn_timeout_s` settle window whose iterations
  each call `_wait_idle` again; with send retries a single turn can consume ~8–9 minutes
  of a 30-minute run deadline. One wall-clock ceiling per send (S02.3).
- (fixed, flowbench #67) the `Continue.` nudge relay pollution and the cumulative
  `any_child_busy` fold: the driver now waits out busy children (`/child_sessions`, paged)
  and the loop never nudges; `_list_items` pages past the 200-item cap.

**Test gaps** (fold into S00.3's table)

- `OmnigentDriver.start()` is entirely untested — including the `ANTHROPIC_API_KEY`
  subscription guard, the one safety check the repo calls non-negotiable.
- `_wait_idle` (the lying-idle heuristic that killed live runs) has no direct test; the
  settle tests deliberately stub around it.
- `_injection_undelivered`'s label parsing (the magic strings gating every send retry)
  is stubbed in tests, never exercised.
- `send()` retry exhaustion and the loop's `deadline_s` backstop are never exercised.
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

**Non-findings** (plausible claims that do not hold — recorded so they aren't
re-reported or "fixed" into regressions)

- "Just use `omnigent_client`'s public `sessions.create()` instead of the private
  `_http` POST" — refuted: the public `create()` cannot express `terminal_launch_args`
  (the flags that prevent the AskUserQuestion tmux deadlock) and there is no
  post-creation setter. The reach-in is *forced* by a public-API gap; the fix is an
  upstream omnigent-client addition, then migration (S02.5).
- "Shipping `scenarios` in the wheel / keeping inspect-ai are defects" — both were
  *decided-and-scheduled* removals (E01), resolved in S01.4.
- "`run_case`/watcher belong in the engine" — true, and already the plan (E01); the
  original placement downstream was a deliberate wait-for-second-consumer decision.

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
