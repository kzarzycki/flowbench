# Plan — issue #41 (S01.1). One task = one commit on `loop/issue-41-lift-runtime`. TDD: port the tests first (red on import), then move the code (green).

Engine root: `$FLOWBENCH` (= /Users/zarz/dev/agents/flowbench). Source: `$SCENARIOS/scenarios/swe_planning/`, tests `$SCENARIOS/tests/test_swe_planning_{helpers,run}.py`.

## T1 — transcript.py (closes #3)
- New `src/flowbench/transcript.py`: move `_item_text`→`item_text`, `last_assistant_text`, `n_assistant_messages`, `is_control_message`, `dedup_items` out of `runner/driver.py` verbatim; add `render_transcript` from helpers (uses `item_text`).
- `driver.py`: `from flowbench.transcript import (  # noqa: F401 — re-exported until S01.2 repoints the scenarios imports\n    dedup_items, is_control_message, item_text, last_assistant_text, n_assistant_messages)`; `_item_text = item_text  # alias until S01.2`. Delete the five bodies. `tests/runner/test_driver.py` keeps importing `dedup_items`/`is_control_message` from the driver and stays untouched.
- Tests: `tests/test_transcript.py` ← `test_render_transcript*` from helpers tests; existing driver tests must stay green untouched.

## T2 — judge.py
- Append `parse_scores`, `parse_verdict`, `build_judge_prompt`, `aggregate_verdicts`, `aggregate_scores`, `_line_after` + regexes to `runner/judge.py`.
- Rewrite `last_json_object` scanning to skip `{`/`}` inside JSON strings (track in-string + backslash escape). Same public signature/semantics.
- Tests: `tests/runner/test_judge.py` ← helpers tests for parse_*/build_judge_prompt/aggregate_*; `test_parse_scores_and_aggregate` from run tests; new `test_last_json_object_braces_in_strings` (`'x {"a": "}"} y'` → `{"a": "}"}`) + keep prose-before-object case.

## T3 — flowspec.py + pyyaml dep
- New `src/flowbench/flowspec.py`: `load_flows`, `compose_kickoff` verbatim.
- `pyproject.toml`: `pyyaml>=6` in `dependencies`; `uv lock`.
- Tests: `tests/test_flowspec.py` ← `test_compose_kickoff*`, `test_load_flows*`.

## T4 — model.py
- New `src/flowbench/model.py`: `SessionModel` = `OmnigentModel` body, stderr prefix `[flowbench]`, constants `GENERATE_ATTEMPTS`, `GENERATE_RETRY_WAIT_S` live here (ported tests monkeypatch `flowbench.model.GENERATE_RETRY_WAIT_S`). Imports `OmnigentDriver` under `TYPE_CHECKING` only (driver.py already imports omnigent lazily, but keep model.py free of it anyway).
- `src/flowbench/testing.py` (first half): `ScriptedDriver` from run tests.
- Tests: `tests/test_model.py` ← the six `test_generate_*` tests.

## T5 — report/run_report.py
- New `src/flowbench/report/run_report.py` = `report.py`; scenario label = `meta.get("scenario", "")` in both renderers. `render_any` kept; `__main__` block kept.
- Tests: `tests/report/test_run_report.py` ← `_aggregate_dir` + the four `test_aggregate_report_*` (self-contained). `test_render_any_dispatches_on_shape` needs `run_case` → ported in T6.

## T6 — run.py + testing.py
- New `src/flowbench/run.py`: `run_case(..., runs_root, scenario)`, `run_case_n(..., runs_root, scenario)` (both required keywords; `scenario` written to run.json incl. aggregate), `_title`, `_project(run_dir, scenario)`, `make_*_omni(..., *, scenario)`, `run_judge_omni(..., *, scenario)`, `omni_factories(scenario)` → three `functools.partial`s. Constants `DONE_TOKEN`, `MISSING_PLAN`, `SIM_MODEL`, `JUDGE_MODEL`. No `main`/argparse.
- Copy `$SCENARIOS/scenarios/swe_planning/cases/feature_flag_service/{task,simulator,knowledge,judge}.md,flows.yaml` → `tests/fixtures/feature_flag_service/`; tests use it via a `CASE_DIR` constant in `tests/test_run.py`.
- `testing.py` (rest): `FakeDriver`, `StubSim`, `MissingPlanDriver`, `n_run_factories` from run tests — exactly the five publics of the spec. `_three_flow_case`/`_three_flow_factories` stay test-local in `tests/test_run.py` (like `_aggregate_dir` in T5).
- Tests: `tests/test_run.py` ← all remaining `test_run_case*`, `test_make_flow_driver_*`, `test_project_*`, `test_title_*`, and `test_render_any_dispatches_on_shape` (imports `_aggregate_dir` from `tests/report/test_run_report.py`); call sites pass `runs_root=tmp_path, scenario="swe_planning"`; assertions unchanged. Excluded (stay scenario-side): `test_default_runs_root_is_sibling_of_repo`, `test_parse_args_*`.

## T7 — watch.py
- New `src/flowbench/watch.py` = `watch.py` minus `main`; `RunWatch(run_id, *, runs_root, scenario, server_log=..., server=...)`; `project = f"{scenario}/{run_id}"`.
- Tests: `tests/test_watch.py` ← `test_run_watch_tick_events`.

## T8 — gates
- All ten acceptance criteria, recorded in `gates.md`: AC1 `uv run pytest -q`; AC2 `uv run --exact --no-extra spike python -c "import ..."` (then `uv sync --extra dev --extra spike` to restore the env); AC3 grep over the seven new modules; AC4 name-pairing of ported tests (58) + fixture dir present; AC5 covered by T2 tests; AC6 `grep -n "^def \(_item_text\|last_assistant_text\|n_assistant_messages\|is_control_message\|dedup_items\)" src/flowbench/runner/driver.py` → empty; AC7 `cd $SCENARIOS && uv run pytest -q`; AC8 `ruff check` + `ruff format --check`; AC9 `diff <(sed -n '/def generate/,/return _Out()/p' $SCENARIOS/scenarios/swe_planning/run.py) <(same range from src/flowbench/model.py)` → only the `[swe_planning]`→`[flowbench]` line; AC10 `grep -rn "scenarios\." src/flowbench/ | grep -E "(from|import) scenarios"` → empty.
- `docs/design/runner.md`: one paragraph "module map after S01.1" + CLAUDE.md Layout bullet listing the new modules. `docs/roadmap/current-state.md` inventory rows for the new modules.

Order: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8. T1–T5 are mutually independent; T6 depends on T1–T5; T7 depends on nothing but is committed after T6 to keep the order linear. Every task's commit is green on its own. Each task ≤ ~150 lines of engine diff excluding ported tests.
