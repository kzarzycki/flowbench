# Spec — issue #41: S01.1 lift the generic runtime into the engine

Epic: `docs/roadmap/epics/E01-one-execution-model.md`. Behavior-preserving move: copy, adapt imports, no redesign. Source: `$SCENARIOS/scenarios/swe_planning/{run,helpers,report,watch}.py` (950 lines). Decisions: `decisions.md`.

## Module map (engine, `src/flowbench/`)

| New module | Contents | From |
|---|---|---|
| `run.py` | `run_case`, `run_case_n`, `make_flow_driver_omni`, `make_simulator_omni`, `run_judge_omni`, `omni_factories`, `_title`, `_project`, constants (`DONE_TOKEN`, `MISSING_PLAN`, `SIM_MODEL`, `JUDGE_MODEL`). No `main`. | `run.py` |
| `model.py` | `SessionModel` (= `OmnigentModel`, renamed; body byte-for-byte except stderr prefix), `GENERATE_ATTEMPTS`, `GENERATE_RETRY_WAIT_S` | `run.py` |
| `flowspec.py` | `load_flows`, `compose_kickoff` | `helpers.py` |
| `runner/judge.py` | existing `last_json_object` (string-aware) + `parse_verdict`, `parse_scores`, `build_judge_prompt`, `aggregate_verdicts`, `aggregate_scores` | `helpers.py` |
| `transcript.py` | `item_text`, `last_assistant_text`, `n_assistant_messages`, `is_control_message`, `dedup_items`, `render_transcript` | `driver.py` + `helpers.py` |
| `report/run_report.py` | `md_to_html`, `transcript_html`, `flow_card`, `render_report`, `render_aggregate_report`, `render_any` | `report.py` |
| `watch.py` | `RunWatch` (no `main`) | `watch.py` |
| `testing.py` | `FakeDriver`, `StubSim`, `MissingPlanDriver`, `ScriptedDriver`, `n_run_factories` | test doubles |
| `tests/fixtures/feature_flag_service/` | copy of the 5 case files (task/simulator/knowledge/judge .md, flows.yaml) | scenarios case |

`driver.py` loses the five helpers and imports them from `transcript.py`; keeps `_item_text = item_text` alias (decision 7). `pyproject`: `pyyaml>=6` in core deps.

Signature changes (all recorded in decisions.md, all forced by leaving the scenarios repo):
- `run_case(..., runs_root, scenario)` and `run_case_n(..., runs_root, scenario)`: required keywords. `scenario` is written into run.json (`"scenario"` key, additive) and used for the session `project` label.
- `make_flow_driver_omni(flow, flow_dir, *, scenario)`, `make_simulator_omni(flow, sim_dir, *, scenario)`, `run_judge_omni(judge_md, entries, judge_dir, *, scenario)`; `omni_factories(scenario)` returns the three as partials matching the factory contract run_case calls.
- `_project(run_dir, scenario)`.
- `RunWatch(run_id, *, runs_root, scenario, ...)`: required keywords; `project = f"{scenario}/{run_id}"`.
- Report scenario label read from run.json `scenario` (empty if absent).

Nothing else changes: run.json/session.json shapes (one additive key), report.html, `_sim_<flow>`/`_judge` dir names, session titles, project labels, rotation, retry policy, DONE token, timeouts. Ported tests change only call sites (decision 10), never assertions.

## Not in scope
- Deleting anything from the scenarios repo (S01.2). Scenarios keep working unchanged against this branch because nothing existing is removed or renamed (driver alias, decision 7).
- Inspect/`subscription_model.py` removal (S01.4). CLI (`flowbench run`, S03.x). Parameterizing case constants (S01.3/E03).
- Any retry/settle/driver-interface change (E02).

## Acceptance criteria (checkable from diff + tests)
1. `uv run pytest -q` green in the engine; no new skips.
2. `uv run --exact --no-extra spike python -c "import flowbench.run, flowbench.model, flowbench.flowspec, flowbench.transcript, flowbench.watch, flowbench.report.run_report, flowbench.testing"` exits 0 (omnigent pruned from the env; no omnigent at import time).
3. `grep -rn "omnigent" src/flowbench/{run,model,flowspec,transcript,watch,testing}.py src/flowbench/report/run_report.py | grep -E "^\S+:\s*(from|import) "` → empty (module-level imports only; lazy imports inside functions and comments allowed).
4. Engine `tests/` contain ported equivalents, same test names, of all 25 `test_swe_planning_helpers.py` tests and 33 `test_swe_planning_run.py` tests (all but `test_default_runs_root_is_sibling_of_repo`, `test_parse_args_*`); `tests/fixtures/feature_flag_service/` exists with the 5 files.
5. New test: `last_json_object('x {"a": "}"} y')` → `{"a": "}"}`; and the prose-before-object case still passes.
6. `driver.py` defines none of `_item_text`/`last_assistant_text`/`n_assistant_messages`/`is_control_message`/`dedup_items` itself; it imports them from `flowbench.transcript`.
7. `$SCENARIOS` suite still green against the branch without any scenarios change (`cd $SCENARIOS && uv run pytest -q`).
8. `ruff check` + `ruff format --check` clean.
9. `SessionModel.generate` body differs from `OmnigentModel.generate` only in the stderr prefix (diff-checkable).
10. No file under `src/flowbench/` imports `scenarios.*`.
