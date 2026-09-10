# E03 — Case API and `flowbench run`

Milestone M3. Depends on E01 (run_case in the engine); benefits from E02 but does not
require it.

## Goal

A case is a folder. The text files carry the task, the simulated user, and the flows; an
optional `case.py` carries the runtime shape (what proves delivery, per-flow setup and
teardown, how a flow is graded). `flowbench run <case_dir>` runs it, `flowbench watch`
follows it, and the engine ships a two-minute smoke case so it can verify itself without
the private repo. The flow schema is validated with errors that name the file and field.
Run metadata is versioned so readers can evolve safely.

Story order: S03.2 first (the API everything else hangs off), then S03.1, S03.4, S03.5.

## Stories

### S03.2 Case API: a case is a folder, `flowbench run <case_dir>`, engine smoke case

Spec: [#137](https://github.com/kzarzycki/flowbench/issues/137) (the issue body is the
spec; this section is the summary).

- `Case` class in the engine, constructed with the case folder. Fields with defaults:
  `deliverable` (file or directory under the flow dir, or none), `max_turns`,
  `deadline_s`. Methods with defaults: `setup`/`teardown` per flow (default runs
  `setup.sh`/`teardown.sh` from the case folder if present; teardown always runs),
  `score(flow, flow_dir, session)` → `scorecard.json` (default: none). Text files stay the
  only source of task/simulator/knowledge/flows/judge; the class never defines them.
- Discovery: nearest `case.py` walking up from the case folder to the scenarios root, one
  `Case` subclass; none → plain `Case`. Variants are sub-folders sharing a parent
  `case.py`. `scenario.py` is deleted; the engine carries no scenario string
  (run dirs `<runs_root>/<case>/<run_id>`).
- `run_case`/`run_case_n` take a `Case` instead of the loose kwargs. One flow is allowed;
  `judge.md` needs 2+ flows (load error otherwise); one flow with no `score` is a load
  error ("nothing grades this case"). No flow is a baseline.
- Completion: engine-owned done token, instruction injected into the simulator prompt;
  `simulator.md` files lose their token text; `session.json` gains `ended_by`
  (`done | max_turns | deadline | <agent status>`). Decision record in
  `docs/design/decisions/`.
- CLI: `flowbench run <case_dir> [--n] [--run-id] [--runs-root] [--rescore RUN_ID]`,
  `flowbench watch <run_id>`, `compare` unchanged. Settings via `pydantic-settings`
  (flag > `FLOWBENCH_*` env > `.env` > `[tool.flowbench]` > default); `python-dotenv`
  dropped.
- Smoke case `scenarios/smoke/hello` in this repo: one `haiku` flow, `hello.txt`
  deliverable, content-check `score`, about two minutes. It is the live gate for
  engine-only PRs.
- Paired scenarios PR: `run.py`/`watch.py`/`scenario.py` deleted; todo_app `scoring.py`
  → `case.py`; renames `coding_workflow → swe_e2e`, `swe_planning/todo_app →
  smoke_todo_app`; per-developer paths to `.env`; `loop.md` live gate names the smoke
  cases. GLOSSARY folder shape rewritten, naming rule added (scenario =
  `<domain>_<phase|scope>`, smoke cases `smoke_*`).
- Docs: `docs/design/case.md` (lifecycle diagram + contract), `runner.md` updated.
- Verify: V1 with a stub case (discovery, script setup/teardown, one flow, directory
  deliverable, `ended_by`, rescore); V2; live: smoke case here, `smoke_todo_app` and
  `swe_e2e/todo_app` in the scenarios repo, through the new CLI.

Follow-ups filed under this epic when S03.2 lands, not before:

- Absolute rubric judge as the default `score` for plan-shaped cases (grades one flow;
  could replace the comparative judge, which then loses its position-bias rotation).
- Stronger done signal (a file the simulator writes, or an MCP tool) only if `ended_by`
  shows the phrase misfiring.
- `dwh_migration` on `Case` (private repo): flows, simulator, normalizer as `score`,
  clearscape lifecycle as `setup`/`teardown`.

### S03.1 Flow schema v1 (`flowbench/flowspec.py`)

- One `Flow` definition covering the union of what exists today: `name`, `harness`,
  `skills`, `skill_dirs`, `mcp_files` (the engine dataclass) + `model`,
  `reasoning_effort`, `prepend`, `append`, `turn_timeout_s` (the swe_planning dict
  shape). The frozen dataclass and the yaml dict converge — downstream stops passing raw
  dicts around.
- Loader validates: unknown keys rejected, `skill_dirs` entries must contain `SKILL.md`
  (exists today), enum-ish fields checked; errors read
  `flows.yaml: flow 'superpowers': unknown key 'modle'`.
- Verify: unit tests for the error messages (V1, see `../verification.md`); both
  scenarios load through it (V1 + V2).

### S03.4 Run metadata schema v1

- `run.json` and `scorecard.json` get `"schema_version": 1`. A short schema doc
  (`docs/design/run-schema.md`) lists required/optional fields for both, plus the reader
  rule: unknown fields are ignored; a missing `schema_version` means v0 (today's files).
- `flowbench compare` and the report renderers assert the version and degrade politely
  (a v0 file still renders, with a note).
- Verify: round-trip test (write → read → validate) in V1; old fixture files still
  render.

### S03.5 Generic compare

- `report/compare.py` stops hardcoding todo_app's metric paths. Metric rows come from
  the scorecards themselves: flatten `objective.*` and top-level judge blocks into rows,
  or accept an explicit row list passed by the scenario. The FAILED-column and
  FAILED-cell semantics (whole-flow banner row, labeled judge errors) are preserved
  exactly — they are the point of the module.
- Verify: existing `test_compare.py` cases keep passing with unchanged rendered output
  for todo_app cards (V1); a swe_planning run.json/scorecard renders without a custom
  table.

## Non-goals

- Settings beyond `runs_root`, `sim_model`, `judge_model`; the precedence rule is fixed in
  S03.2, new keys are added only when a case needs one.
- Scenario plugin/entry-point discovery — a case is a path; `case.py` walk-up covers
  shared code at this scale.
- Per-turn hooks, a case-defined simulator object, multi-stage cases: wait for a case that
  needs them (the divergence-traps case is the first candidate).

## Risks

- CLI is the first engine surface users type by hand; renaming later is churn. Keep verbs
  to `run | compare | watch` and put everything else behind flags until usage proves a
  need.
