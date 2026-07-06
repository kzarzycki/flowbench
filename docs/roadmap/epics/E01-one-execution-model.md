# E01 — One execution model: extract `run_case`, port todo_app, remove Inspect

Milestone M1. This epic *executes an already-recorded decision* (flowbench-scenarios
`docs/superpowers/specs/2026-07-02-swe-planning-rework-design.md`): one execution model
(`run_case`), everything omnigent, `claude -p` and Inspect removed. It also fires that
design's extraction trigger: the primitives were to stay in the swe_planning scenario
"until a second scenario forces extraction" — porting todo_app is that second scenario.

## Goal

After this epic there is exactly one way to run a benchmark: the engine's `run_case`
orchestrator. The engine owns the generic runtime (orchestration, session-backed models,
judge parsing, transcript rendering, flow loading); scenarios own only content and
scenario-specific scoring. `inspect-ai`, `subscription_model.py`, and the todo_app
Inspect glue are gone.

## What moves where

Source of truth today: `flowbench-scenarios/scenarios/swe_planning/`. Mapping:

| From (scenarios repo) | To (engine) | Notes |
| --- | --- | --- |
| `run.py:run_case`, `run_case_n` | `flowbench/run.py` | factories stay injectable (`make_flow_driver`, `make_simulator`, `run_judge`); the omnigent-backed factory defaults move too |
| `run.py:OmnigentModel` | `flowbench/model.py` as `SessionModel` | keep the issue-#39 freshness retry EXACTLY as-is for now; unifying it into the driver is S02.3, not this epic |
| `helpers.py:compose_kickoff, load_flows` | `flowbench/flowspec.py` | flows.yaml loading + kickoff composition |
| `helpers.py:parse_verdict, parse_scores, build_judge_prompt, aggregate_verdicts, aggregate_scores` | `flowbench/judge.py` | merge with the existing `last_json_object` (todo_app's JSON judge still uses it until S01.3 rewrites it); fix `last_json_object`'s brace counting to be string-aware while moving it (audited bug: braces inside JSON strings mis-slice the object) |
| `helpers.py:render_transcript` + `driver.py:_item_text, dedup_items, is_control_message, last_assistant_text, n_assistant_messages` | `flowbench/transcript.py` | ends the current situation where helpers imports a private `_item_text` from the driver |
| `report.py` | `flowbench/report/run_report.py` | generalize names only as far as the move requires |
| `watch.py` | `flowbench/watch.py` | S03.3 wires it into the CLI; the move can come earlier if cheap |
| (new) | `flowbench/testing.py` | `FakeDriver` + scripted simulator + canned judge, extracted from the scenarios repo's offline tests so both repos test against the same doubles |

## Stories

### S01.1 Lift the generic modules into the engine

- Create the engine modules per the table. Copy, then adapt imports — do not redesign
  while moving (behavior-preserving; redesign is E02/E03).
- `flowbench/testing.py` gets the fake driver/simulator/judge used by run_case tests.
- Port the relevant offline tests from the scenarios repo into `tests/` here (run_case
  wiring, verdict parsing, aggregation, transcript rendering).
- Verify: V1 (see `../verification.md`); plus the new modules import without the
  `spike` extra (they must not import omnigent at module top level — the omnigent
  factories import lazily, same pattern as `OmnigentDriver.start`):
  `uv run --no-extra spike python -c "import flowbench.run, flowbench.model"`.

### S01.2 Paired scenarios PR: swe_planning consumes the engine

- swe_planning's `run.py`/`helpers.py` shrink to: scenario constants (done token, models),
  its report specifics, and re-exports/imports from `flowbench.*`. Local copies deleted.
- Its offline tests keep passing **unchanged** except for import paths — that is the
  behavior-preservation check.
- Engine PR merges first (editable path dep), then this one; one live `swe_planning`
  3-flow run validates both.
- Verify: V2; V4 — the live run's `run.json` has the same shape as the previous run's.

### S01.3 Port todo_app to `run_case`

- Build `scenarios/coding_workflow/cases/todo_app/` in the plain-file case format:
  `task.md` (FIRST_PROMPT), `simulator.md` (profile + reply rules), `knowledge.md`
  (envisioned-shape.md content), `flows.yaml` (baseline + superpowers, `skills: none`,
  superpowers `skill_dirs` resolved as today).
- Scenario-local Python keeps: `acceptance.py` (black-box subprocess checks; fix the
  audited `resolve_invoker` bug — the console-script fallback is gated on the exact
  CPython string `"No module named todo.__main__"`, so a console-script-only app fails
  every check), `scorers.py` reworked to consume the captured session dict from `run_case`
  instead of Inspect state (`clarifying_coverage`, `skills_report`, `detect_phases`,
  the JSON judge). The scorecard schema stays as-is so `flowbench compare` output is
  comparable with historical runs.
- Delete `eval.py`, `solver.py`, and the Inspect scorer decorators; add a
  `python -m scenarios.coding_workflow.run --case todo_app` entrypoint mirroring
  swe_planning's (replaced by `flowbench run` in S03.3).
- Keep `task.py`'s simulator-profile and UNDERSPECIFIED_TOPICS content — move the prose
  into the case files, keep the keyword dict in scorers.
- Verify: V1 (scorer tests run against the canned sessions in `fixtures/sessions.py`);
  V5 through the new entrypoint.

### S01.4 Remove Inspect and `claude -p`

- Delete `src/flowbench/runner/subscription_model.py`, the
  `[project.entry-points.inspect_ai]` block, `inspect-ai` from the `spike` extra.
- Rename extra `spike` → `live` (README, CLAUDE.md, CI, and the scenarios repo's
  `--extra spike` invocations — grep both repos).
- Wheel ships `src/flowbench` only: drop `scenarios` from
  `[tool.hatch.build.targets.wheel].packages` (the top-level `scenarios` package would
  collide in site-packages; in-repo imports keep working via `pythonpath = ["."]`).
- Verify: `uv sync --extra dev --extra live` then V1; `rg -l inspect_ai src scenarios
  tests` → empty; V7 (wheel carries no `scenarios/`). Update V4/V5 in
  `../verification.md` for the extra rename in this PR.

### S01.5 Milestone live validation

- V5 (baseline vs superpowers) and V4 (`--n 1`) through the post-epic code. Compare
  todo_app's scorecard values with the last Inspect-era run for plausibility (not
  equality — the agent is stochastic).
- Journal the parity notes in the ledger.

## Non-goals

- Changing the retry/settle policy or the driver interface (E02).
- New CLI (`flowbench run`) or case/flow schema validation (E03) — S01.3's entrypoint is
  a copy of the existing pattern, deliberately boring.
- Improving todo_app's keyword-based scoring (tracked as debt in `current-state.md`).

## Risks

- **Hidden Inspect dependencies in scoring semantics** — `Score`/`accuracy`/`mean` wrap
  values; the ported scorers must reproduce the *scorecard.json* values, which are computed
  before Inspect wrapping (solver writes them directly), so the blast radius is the
  deleted decorators only. Check `write_outputs` call sites when porting.
- **Two repos in flight** — always merge engine first; scenarios PR pins nothing (editable
  path dep) so a stale sync is the failure mode: re-run `uv sync --extra spike` (pre-
  rename) after every engine merge, as CLAUDE.md already warns.
- **The `_sim_<flow>` / `_judge` run-dir conventions** become engine behavior; the watcher
  and web-UI grouping (`session_title`, `project`) rely on them — port their tests.
