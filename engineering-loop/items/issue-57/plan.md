# Plan — issue #57 (S01.2). Worktree: /Users/zarz/dev/xebia/flowbench-scenarios--issue-57, branch loop/issue-57-s01-2 off origin/main. One commit per task.

## T1 — tests first
- `tests/test_swe_planning_run.py`: delete everything except the 4 kept tests; import block becomes: `from pathlib import Path` / `import pytest` / `import flowbench.run as engine_run` / `from scenarios.swe_planning import scenario` / `from scenarios.swe_planning.run import _parse_args, default_runs_root, main` (the kept tests use `Path`, `scenario.__file__`, `pytest.raises`); drop `asyncio, json, shutil, yaml, AgentDriver, TurnResult, run_mod` and the old helpers/run imports; add `test_main_wires_engine_run_case_n(monkeypatch, capsys, tmp_path)`: monkeypatch `scenarios.swe_planning.run.run_case_n` with an async recorder returning `{"run_root": str(tmp_path), "trials": [{"x": 1}], "aggregate": {"n": 1}}`; monkeypatch `sys.argv` to `["run", "--case", "feature_flag_service", "--run-id", "r1"]`; call `main()`; assert kwargs `scenario == "swe_planning"`, `runs_root == default_runs_root()`, `n == 1`, `make_flow_driver.func is flowbench.run.make_flow_driver_omni` (partial), stdout contains `"x": 1` and `Run written to:`. Second call with `--n 2 --runs-root <str(tmp_path)>` → recorded `runs_root == tmp_path` (main wraps the CLI string in `Path`), stdout prints the aggregate.
- `tests/test_swe_planning_flows.py:76`: `from flowbench.flowspec import load_flows`.
- `git rm tests/test_swe_planning_helpers.py`.
- Suite is RED (run.py still imports the old helpers; fine) — commit anyway as `test(S01-2): T1 …`? NO: keep one-commit-green — fold T1 + T2 into ONE commit.

## T2 — the deletion (same commit as T1)
- `scenarios/swe_planning/run.py` → entrypoint only (decision 1). Docstring: keep the usage line; add "runtime lives in flowbench.run".
- `scenarios/swe_planning/watch.py` → `main` only (decision 2).
- `git rm scenarios/swe_planning/helpers.py scenarios/swe_planning/report.py`.
- Green: `uv run pytest -q`, `ruff check`, `ruff format --check`, both `--help`s.
- Commit `refactor(S01-2): swe_planning consumes the engine runtime; delete local copies` + `Closes #57`.

## T3 — docs + lock + loop artifacts
- `scenarios/swe_planning/README.md` per decision 7. `uv lock` (already dirty from sync) — commit `uv.lock`.
- `git add -f .claude/engineering-loop/LOG.md .claude/engineering-loop/items/issue-41 .claude/engineering-loop/items/issue-57` (spec, decisions, plan, reviews, gates, state).
- Commit `docs(S01-2): README code layout, re-lock, loop journal for S01.1/S01.2`.

## T4 — gates → gates.md (AC1–AC7), PR against main, CI, squash-merge.
## T5 — live validation (AC8): from the MAIN checkout after `git pull` + `uv sync --extra spike`: `uv run --extra spike python -m scenarios.swe_planning.run --run-id todo-<next> --n 2` in the background; `uv run python -m scenarios.swe_planning.watch todo-<next> --pid <pid>`; record outcome in gates.md + LOG.md (parity notes vs the last pre-S01.1 run).
