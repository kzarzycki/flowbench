# E03 — Case format v1 and `flowbench run`

Milestone M3. Depends on E01 (run_case in the engine); benefits from E02 but does not
require it.

## Goal

A scenario author can add a case by writing five plain files and run it with one command.
The flow schema is validated with errors that name the file and field. Run metadata is
versioned so readers can evolve safely.

## Stories

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

### S03.2 Case format v1 (`flowbench/case.py`)

- Documented case dir: `task.md` (required), `flows.yaml` (required), `simulator.md`,
  `knowledge.md`, `judge.md` (required for judged scenarios), optional `fixtures/`,
  optional scenario-local Python hooks (scorers/acceptance) discovered by the scenario's
  own `run` wiring, not by the engine.
- The loader returns a typed `Case` (paths + loaded texts); missing required files fail
  with the path in the message.
- Move the scenario-authoring guide into `docs/design/scenario-authoring.md` here in the
  engine (the downstream repo's copy points at it) — the format belongs to the engine.
- Verify: V1 + V2 (both scenarios' cases load); a fixture case with a missing file
  produces the documented error.

### S03.3 CLI: `flowbench run` and `flowbench watch`

- `flowbench run --scenario coding_workflow --case todo_app [--n N] [--run-id ID]
  [--runs-root PATH]`: resolves the scenario dir (in-repo `scenarios/` or an installed
  downstream package's path — start with a `--scenarios-root` flag, keep it dumb),
  loads case + flows, calls `run_case_n`, prints the summary JSON exactly as the
  per-scenario mains do today, then deletes those mains.
- `flowbench watch <run-id> [--pid ...]` lifts `swe_planning/watch.py` (engine module
  since E01 or moved here).
- The subscription guard, `.env` loading, and the runs-root default
  (sibling `../flowbench-runs/<scenario>/`) live in the CLI layer, once.
- Verify: V5 via the new CLI; `--help` documents every flag; scenario-local `__main__`
  blocks are gone from both repos. Update V4/V5 in `../verification.md` to the CLI
  invocations in this PR.

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

- Config layering (defaults → scenario → CLI) beyond the flags listed — the design
  record explicitly deferred it; flags stay few.
- Scenario plugin/entry-point discovery — a `--scenarios-root` path flag is enough at
  this scale.

## Risks

- CLI is the first engine surface users type by hand; renaming later is churn. Keep verbs
  to `run | compare | watch` and put everything else behind flags until usage proves a
  need.
