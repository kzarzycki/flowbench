# Spec — issue #57: S01.2 swe_planning consumes the engine runtime

Paired with flowbench #43 (S01.1, merged 517fd5c). Deletion PR: the scenario keeps content + CLI entrypoints; every runtime line now comes from `flowbench.*`. Decisions: `decisions.md`.

## Changes

| File | Action |
|---|---|
| `scenarios/swe_planning/run.py` | keep `default_runs_root`, `_positive_int`, `_parse_args`, `main`; delete `run_case`, `run_case_n`, `OmnigentModel`, `_title`, `_project`, `make_*_omni`, `run_judge_omni`, constants; import `run_case_n`, `omni_factories` from `flowbench.run` |
| `scenarios/swe_planning/watch.py` | keep `main` only; `RunWatch` from `flowbench.watch`, called with `runs_root` + `scenario="swe_planning"` |
| `scenarios/swe_planning/helpers.py`, `report.py` | delete |
| `tests/test_swe_planning_helpers.py` | delete |
| `tests/test_swe_planning_run.py` | keep the 4 scenario-side tests; add `test_main_wires_engine_run_case_n`; delete the rest (ported) |
| `tests/test_swe_planning_flows.py` | `load_flows` from `flowbench.flowspec` |
| `scenarios/swe_planning/README.md` | code-layout paragraph + standalone report command |
| `uv.lock` | re-lock |
| `.claude/engineering-loop/LOG.md`, `items/issue-41/`, `items/issue-57/` | journal + loop artifacts (force-added; `.claude/` is only locally excluded) |

## Not in scope
Any engine change (the now-dead `_item_text` alias in `flowbench/runner/driver.py` is flowbench https://github.com/kzarzycki/flowbench/issues/44, decision 10). Changing CLI flags, run-dir layout, labels. todo_app port (S01.3). Deleting `default_runs_root` (needs `flowbench run` CLI, S03.x).

## Acceptance criteria
1. `uv run pytest -q` green (expected 136 − 25 − 33 + 1 = 79 passed, 1 skipped).
2. `grep -rn "swe_planning.helpers\|swe_planning.report\|_item_text" scenarios tests` → empty (decision 9 scopes the issue's repo-wide grep to code); `grep -n "helpers.py\|report.py" scenarios/swe_planning/README.md` → empty; `ls scenarios/swe_planning/helpers.py scenarios/swe_planning/report.py tests/test_swe_planning_helpers.py` → all missing.
3. `scenarios/swe_planning/run.py` ≤ 80 lines and defines exactly `default_runs_root`, `_positive_int`, `_parse_args`, `main`; `watch.py` defines exactly `main`.
4. `grep -c "scenario=SCENARIO" scenarios/swe_planning/run.py scenarios/swe_planning/watch.py` → 1 hit each (`SCENARIO = "swe_planning"` defined once in run.py, imported by watch.py).
5. `uv run python -m scenarios.swe_planning.run --help` and `... .watch --help` exit 0.
6. `ruff check` + `ruff format --check` clean.
7. `git diff --stat origin/main` shows net deletion ≥ 900 lines under `scenarios/` + `tests/`.
8. Live (gate 5, after merge): `uv run --extra spike python -m scenarios.swe_planning.run --run-id todo-<next> --n 2` with the watcher: zero permission prompts, no failed sessions, `plans_missing == []` per trial, aggregate `run.json` + `report.html` land, `run.json["scenario"] == "swe_planning"` in each trial, web-UI project label `swe_planning/<run_id>`.
