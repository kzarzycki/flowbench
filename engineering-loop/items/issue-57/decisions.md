# decisions.md — issue #57 (S01.2)

1. **What stays in `scenarios/swe_planning/run.py`?** The entrypoint only: `default_runs_root()` (anchored off this repo), `_positive_int`, `_parse_args`, `main()`. `main` does `make_flow_driver, make_simulator, run_judge = omni_factories("swe_planning")` and calls `run_case_n(case_dir, run_id=..., n=args.n, make_flow_driver=..., make_simulator=..., run_judge=..., runs_root=Path(args.runs_root) if args.runs_root else default_runs_root(), scenario="swe_planning")` — every parameter after `case_dir` is keyword-only in the engine. Constants (`DONE_TOKEN`, `MISSING_PLAN`, …) are no longer re-exported here — nothing scenario-side reads them.
2. **`watch.py`** keeps only `main()` (argparse + loop) over `flowbench.watch.RunWatch(run_id, runs_root=Path(args.runs_root) if args.runs_root else default_runs_root(), scenario="swe_planning")`. Module docstring/usage line kept.
3. **`helpers.py`, `report.py`** deleted outright; standalone report rendering is `uv run python -m flowbench.report.run_report <run_root>` (README updated).
4. **Tests.** `tests/test_swe_planning_helpers.py` deleted (all 25 ported in S01.1). `tests/test_swe_planning_run.py` keeps only `test_default_runs_root_is_sibling_of_repo`, `test_parse_args_n_defaults_to_1`, `test_parse_args_n_accepts_3`, `test_parse_args_n_rejects_zero` (the 4 excluded in S01.1) plus one NEW `test_main_wires_engine_run_case_n` (monkeypatch `flowbench.run.run_case_n` recorder; assert `scenario="swe_planning"`, `runs_root` default, factories from `omni_factories`, n forwarded, stdout payload shape for n=1 vs n>1). `tests/test_swe_planning_flows.py:76` imports `load_flows` from `flowbench.flowspec`.
5. **`uv.lock`** re-locked (engine now requires pyyaml; inspect-ai/ruff floors moved). Committed.
6. **No behavior change on the wire**: same CLI flags, same run dir layout, same `swe_planning/<run_id>` project labels (explicit `scenario` arg); run.json and the n=1 stdout payload (which IS the trial meta) gain the engine's additive `"scenario"` key.
7. **Docs**: `scenarios/swe_planning/README.md` code-layout paragraph rewritten (run.py = CLI only; runtime in flowbench); CLAUDE.md commands unchanged (entrypoints keep their module paths).
8. **Live validation (gate 5)** is mandatory here — first run consuming the engine modules; `--n 2` per loop Phase 9.5. Engine PR already merged (517fd5c), so the ordering rule holds.

9. **Issue's `grep -rn "_item_text" .` is unsatisfiable** — historical loop artifacts and superpowers plans mention the name. Scoped to `scenarios tests` (the code); docs/journal are history, not importers.
10. **Engine alias `_item_text = item_text` in `runner/driver.py`** becomes dead once this lands. Engine change is out of scope here; tracked as flowbench https://github.com/kzarzycki/flowbench/issues/44.

reviewer policy: all-Claude this session (user, 2026-09-07).
