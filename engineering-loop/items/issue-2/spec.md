# Spec — flowbench issue #2: S01.3 port todo_app to `run_case` (PR 1 of 2; S01.4 is PR 2)

Epic: `docs/roadmap/epics/E01-one-execution-model.md` §S01.3. Repo: flowbench only (the open reference scenario lives in the engine repo). Decisions: `decisions.md`.

## Problem

`flowbench.run.run_case` is planning-shaped: every flow writes a `plan.md`, the DONE token is `PLAN_COMPLETE`, and scoring is one comparative judge over all flows. `todo_app` is build-shaped: each flow is scored on its own (black-box acceptance of the built app + clarifying coverage + a per-flow JSON judge) into `<flow>/scorecard.json`, read by `flowbench compare`. Today it runs on Inspect (`eval.py`/`solver.py`, `claudesub` provider). One execution model means `run_case` runs both.

## Engine change (`src/flowbench/run.py`) — the minimum that makes todo_app fit

1. `run_case(..., done_token: str = DONE_TOKEN, score_flow=None)`.
   - `score_flow(flow, flow_dir, session) -> dict` (async). When given, called after each flow's session; the dict is written to `<flow_dir>/scorecard.json`. Absent → today's behavior.
   - `score_flow` failures never abort the run: `run_case` catches `Exception` around the call, writes `{"error": f"{type(e).__name__}: {e}"}` as that flow's `scorecard.json`, records `flow_stats[name]["score_error"]`, and continues with the next flow. `report/compare.py`: `compare_table` widens its `failed` detection so a loaded card whose top-level `error` key is set counts as failed (the dict is kept, `load_scorecards` unchanged), and its `_status_` cell reads `FAILED (<error>)` (today only a missing/unparseable file is FAILED; an error dict would render as a column of dashes). A failed *session* (driver error) keeps today's behavior (propagates).
   - The comparative judge stage runs only if `case_dir / "judge.md"` exists. Without it: no `_judge` dir, no `judge.md` output, `render_report` is NOT called (it reads `judge.md` and lowercases `winner`; `report.html` is a swe_planning artifact, todo_app has `compare`), `meta["winner"] = meta["winner_flow"] = None`, `meta["scores"] = {}`, `labels` still recorded.
   - `run_case_n` gains explicit `done_token`/`score_flow` parameters and adds them to the literal kwargs dict it builds (it does not splat; `artifact_grace_s`/`rotation` stay un-forwarded as today). When every trial's `winner_flow` is `None` it skips `aggregate_verdicts`/`aggregate_scores` and writes `counts: {}`, `winner: None`, `score_means: {}` (today `aggregate_verdicts` would tally `None` as a flow name). `render_aggregate_report` runs as today (it tolerates `winner=None`).
2. `omni_factories(scenario, *, artifact_name="plan.md", git_init=False)`; `make_flow_driver_omni` takes the same two keywords and passes them to `OmnigentDriver`. Defaults keep swe_planning byte-identical.
3. Engine files touched: `run.py`, `report/compare.py`. Nothing else in the engine moves. `flow_stats.plan_lines` keeps its name (decision 8).

## Scenario side (`scenarios/coding_workflow/`)

| Path | Change |
|---|---|
| `cases/todo_app/task.md` | `FIRST_PROMPT` verbatim |
| `cases/todo_app/simulator.md` | the `cooperative_faithful` profile + the done/continue rules from `task.simulator_system()`; `<<DONE>>` named |
| `cases/todo_app/knowledge.md` | `case/envisioned-shape.md` content (file moves; `case/acceptance.md` moves beside it as `acceptance.md`) |
| `cases/todo_app/flows.yaml` | `baseline` (`skills: none`) and `superpowers` (`skills: none` + `skill_dirs` = the 14 vendored dirs); `harness: claude-native`, `model: sonnet` both (decision 9) |
| `skills/` (new, scenario-level like swe_planning) | verbatim superpowers 6.3.0 skills (14 dirs, 472 KB) + `VERSION.md` |
| `run.py` (new) | CLI mirroring `swe_planning/run.py` (`--case --run-id --runs-root --n --deadline-s`), `SCENARIO="coding_workflow"`, `DONE_TOKEN="<<DONE>>"`, `omni_factories(SCENARIO, artifact_name="tasks.json", git_init=True)`, `score_flow=score_todo_app` |
| `cases/todo_app/scoring.py` (new) | `async score_todo_app(flow, flow_dir, session, *, make_grader)`: `shape` = `knowledge.md` text (the file is double-duty: simulator knowledge + judge's envisioned shape, as `ENVISIONED_SHAPE` was); acceptance → `skills_report` → `detect_phases` → `clarifying_coverage` → `judge_build(grader_model=make_grader(flow_dir))`; writes `acceptance.json`; returns the scorecard dict with today's exact keys. `make_grader_omni(flow_dir)` = `SessionModel(OmnigentDriver(run_dir=<run_root>/_judge_<flow>, model=JUDGE_MODEL, skills="none", turn_timeout_s=600, artifact_name="__none__", session_title/project as the engine does))` |
| `cases/todo_app/scorers.py` | drop `workflow_scorer`, `build_judge`, the `inspect_ai` imports; gain `UNDERSPECIFIED_TOPICS` (from task.py). Everything else unchanged |
| `cases/todo_app/acceptance.py` | unchanged (`resolve_invoker` bug → flowbench #46, decision 6) |
| `scenario.py` | `CASE_DIR(name)` like swe_planning's |
| delete | `eval.py`, `solver.py`, `task.py`, `flows.py`, `case/`; `src/flowbench/runner/run_dir.py` (only eval/solver used it) |
| tests | delete `test_eval_discoverable.py`, `test_run_dir.py`; `test_task.py` (7) → `test_case_files.py` keeping 5 intents against the .md files: first prompt leaks only "Python CLI"; simulator.md names `<<DONE>>` and knowledge.md carries the shape; done/continue rules present; simulator never states corrections; `UNDERSPECIFIED_TOPICS` covers the five points. Dropped: `test_unknown_profile_raises` (no profiles left); `test_no_steering_prompt_defined` becomes `test_flows.py::test_no_steering` (neither flow has `prepend`/`append`; both `skills: none`; superpowers `skill_dirs` resolve to dirs with `SKILL.md`). `test_scorers.py` keeps its 18 unchanged (no decorator tests exist). `test_live.py` → `run_case` through `coding_workflow.run.main`, still `RUN_LIVE_AGENT`-gated. New `test_run.py` (offline, AC6) |
| docs | `CLAUDE.md` (Run it block, Layout bullets), `docs/roadmap/verification.md` V5, `docs/roadmap/current-state.md` (inventory rows for eval/solver/run_dir/todo_app), `docs/design/runner.md` if it names `eval.py`; `docs/roadmap/epics/E01-one-execution-model.md` §S01.3: the `resolve_invoker` line becomes "→ #46" |

## Not in scope
- S01.4: `subscription_model.py`, `inspect_ai` entry point, `spike`→`live`, wheel packages (PR 2, same issue). After PR 1 nothing imports inspect, so PR 2 is pure deletion.
- `resolve_invoker` console-script bug (own issue). Scorer quality (debt). `flowbench run` (S03.3). Case/flow schema validation (E03). Aggregating scorecards across `--n` trials (issue #27).

## Acceptance criteria
1. Engine suite green: all existing `tests/test_run*.py`/swe_planning-shaped tests pass unchanged (fixture case has judge.md → identical path).
2. New engine tests over a fixture case WITHOUT judge.md (`tests/fixtures/feature_flag_service` minus judge.md, built in tmp): (a) `score_flow` fake → each `<flow>/scorecard.json` == the fake's dict, no `_judge/`, no `judge.md`, no `report.html`, `meta.winner is None`, `meta.labels` present; (b) `run_case_n(n=2)` on it → `counts == {}`, `winner is None`, `score_means == {}`, aggregate `report.html` exists; (c) a `score_flow` that raises on flow 1 → flow 1's scorecard is `{"error": "RuntimeError: ..."}`, flow 2 scored normally, run completes, and `compare_table` over that run shows flow 1 `FAILED (RuntimeError: ...)` and flow 2 `ok` in the `_status_` row; (d) `score_flow=None` + judge.md present → no scorecard.json, report.html rendered (today pinned); (e) `done_token` reaches `run_agent_session` (monkeypatch, as the swe_planning wiring tests do).
3. `omni_factories("x", artifact_name="tasks.json", git_init=True)` → the flow driver has `artifact_name == "tasks.json"`, `git_init is True`; default call → `"plan.md"`, `False`.
4. `grep -rn "inspect_ai\|claudesub\|subscription_model" scenarios/ src/flowbench/run.py` → empty; `uv run --exact --no-extra spike python -c "import scenarios.coding_workflow.run, scenarios.coding_workflow.cases.todo_app.scoring"` exits 0.
5. `scorecard.json` key set (top-level and `objective`) equals the frozen list from today's `solver.py` (test); `flowbench compare` over an offline fake run renders two columns without `FAILED` (test).
6. Offline `test_run.py`: `coding_workflow.run.main()` with monkeypatched `run_case_n` binds the real signature (as swe_planning's test does) and passes `done_token="<<DONE>>"`, `score_flow`, `scenario="coding_workflow"`; and `score_todo_app` over a `copytree` of `fixtures/good_app` into tmp (acceptance deletes/rewrites `tasks.json`, never run it in-place) + `fixtures.sessions.FULL_WORKFLOW` + a canned grader → `acceptance == 1.0`, `superpowers_used`, `judge_low_confidence` parsed; with a grader that always returns `""` → `{"error": "empty_grader_completion"}`.
7. `flows.yaml` superpowers `skill_dirs` all resolve to dirs with `SKILL.md` (test); `skills/VERSION.md` names 6.3.0.
8. `uv run pytest -q` green, skips unchanged (1: `test_live`); CI diff-coverage 100%.
9. Gate 5 (after merge): `uv run python -m scenarios.coding_workflow.run --case todo_app --run-id todo-app-001` on the live omnigent → both `<flow>/scorecard.json`, `run.json` with `"scenario": "coding_workflow"`, and `uv run flowbench compare --run-base ../../xebia/flowbench-runs/coding_workflow --run-id todo-app-001` renders both columns, no FAILED banner. Journal parity notes vs the last Inspect-era run (S01.5).
