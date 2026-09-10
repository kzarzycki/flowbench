# Spec — flowbench #104 (E02 S02.4): artifact concern out of the driver

## Problem

`OmnigentDriver` knows which file proves a task delivered: ctor field `artifact_name`,
`artifact_path()`, `TurnResult.artifact_exists`, and the `artifact_exists/artifact_path/
artifact_text` keys of `capture_session()`. Sessions with no artifact — simulator, judge,
todo_app flows, `scripts/agent_review.py` — pass the sentinel `artifact_name="__none__"`.
A driver drives a REPL in a workspace; which file proves delivery is the orchestrator's
knowledge (`docs/roadmap/target-architecture.md`, "artifact concern").

## Change

1. **Types / driver.** `flowbench.types.TurnResult` loses `artifact_exists`
   (decisions #1). `flowbench.driver.base.AgentDriver` loses `artifact_path`.
   `OmnigentDriver` loses `artifact_name`, `artifact_path()`, the `artifact_*` keys of
   `capture_session()`, and the `to_thread(self.artifact_path)` call in `_send_once`.
   `_timed_out()` returns `TurnResult(TurnStatus.TIMEOUT, "")`.
2. **Loop.** `run_agent_session(..., artifact_grace_s=60.0,
   artifact_probe: Callable[[], Path | None] | None = None)`.
   - Probe given, simulator says DONE: poll `await asyncio.to_thread(artifact_probe)`
     every 2 s until it returns a path, the whole poll under
     `asyncio.timeout(artifact_grace_s)`; `TimeoutError` ends the poll, never the run.
   - After `capture_session()`: `artifact = await asyncio.to_thread(artifact_probe)` if a
     probe is given, else `None`; the loop sets `session["artifact_exists"]`
     (`artifact is not None`), `session["artifact_path"]` (`str(artifact)` or `None`) and
     `session["artifact_text"]` (`artifact.read_text()` or `None`) — for every session.
   - No probe: no poll, the three keys are `False/None/None`.
3. **Orchestrator (`run.py`).** New `find_artifact(run_dir: Path, name: str) -> Path |
   None`: `run_dir/name` if it exists, else the first `run_dir.rglob(name)` hit, else
   `None`. `run_case` passes `artifact_probe=functools.partial(find_artifact, flow_dir,
   artifact_name)` when `artifact_name is not None`, else `None`; `artifact_grace_s`
   passes through unchanged. `make_flow_driver_omni(flow, flow_dir, *, scenario,
   git_init=False)` and `omni_factories(scenario, *, git_init=False)` lose
   `artifact_name`; `make_simulator_omni` / `run_judge_omni` construct the driver without
   an artifact argument. `run_case`/`run_case_n` keep `artifact_name: str | None =
   "plan.md"` — the one declaration.
4. **Test doubles (`testing.py`).** `FakeDriver(plan_text, questions, run_dir=None)`:
   `start()` writes `Path(run_dir) / "plan.md"` = `plan_text` when `run_dir` is given.
   `MissingPlanDriver.start()` writes nothing. Both lose `artifact_path`;
   `capture_session()` no longer returns `artifact_text`. `n_run_factories` passes
   `run_dir=flow_dir`.
5. **In-repo scenario.** `scenarios/coding_workflow/run.py` calls
   `omni_factories(SCENARIO, git_init=True)`; `make_grader_omni` in
   `scenarios/coding_workflow/cases/todo_app/scoring.py` constructs the driver without an
   artifact argument.
6. **Scenarios repo (paired PR).** `scripts/agent_review.py` drops the kwarg;
   `tests/test_agent_review.py` builds `TurnResult(status=, assistant_text=)`;
   `tests/test_swe_planning_run.py` expects `make_flow_driver.keywords ==
   {"scenario": "swe_planning", "git_init": False}`; `uv.lock` pins the merged engine SHA;
   ledger entry + HANDOFF.
7. **Docs (current truth, once).** `docs/design/runner.md`: ABC method list, capture keys,
   the budget paragraph (no filesystem inside the send), the `run_case` paragraph (probe,
   `omni_factories` signature), the constants paragraph. `docs/roadmap/current-state.md`
   debt item 2 loses the artifact clause. `docs/roadmap/target-architecture.md` states the
   ownership split as fact. `docs/roadmap/ROADMAP.md` S02.4 line loses the sentinel
   parenthetical; `docs/roadmap/epics/E02-runtime-robustness.md` §S02.4 is removed.
   `CLAUDE.md` layout entry for `run.py` updates the `omni_factories` signature.
   `docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md` lists the ABC's
   methods; `artifact_path` is dropped from that list.

Out of scope (same file, other regions, concurrent stories): S02.5 client import /
labels GETs, S02.6 `except Exception` sites.

## Why safe

Only the loop and `run.py` ever consumed the artifact: `session["artifact_text"]` in
`run.py`, `artifact_exists`/`artifact_path` in scenarios' `normalize.py` — both read the
session dict, which keeps its keys. `TurnResult.artifact_exists` has no reader. Live
sessions with no artifact behaved as `False/None/None`; they still do.

## Acceptance criteria

- AC1 `rg __none__` is empty in the engine repo and in the scenarios repo outside
  `LOG.md`, `docs/superpowers/`, `.workflow/`, `.claude/engineering-loop/items/`.
- AC2 Test: `"artifact_exists" not in {f.name for f in dataclasses.fields(TurnResult)}`;
  `not hasattr(AgentDriver, "artifact_path")`; `OmnigentDriver(run_dir=p)` constructs with
  no artifact kwarg and has no `artifact_name`/`artifact_path` attribute.
- AC3 Loop test: probe returns `None` twice then a real file; on DONE the loop polls ≥ 3
  times and the returned session has `artifact_exists is True`, `artifact_path` = the
  file, `artifact_text` = its content.
- AC4 Loop test: probe blocks 1 s (`time.sleep`) on its first call and returns `None`
  instantly on every later call; `artifact_grace_s=0.1` → `run_agent_session` returns in
  < 1 s with `artifact_exists False` (the poll is cut at 0.1 s; the post-capture probe is
  the fast second call).
- AC5 Loop test: `artifact_probe=None` → session has `artifact_exists False`,
  `artifact_path None`, `artifact_text None`, and `asyncio.sleep` is never called in the
  DONE branch.
- AC6 `tests/test_run.py`: `test_run_case_offline` and `test_run_case_flags_missing_plan`
  green with fakes constructed `run_dir=flow_dir`; `<flow>/plan.md` content and
  `artifact_missing` unchanged.
- AC7 `find_artifact` tests: missing → `None`; top-level file → that path; only a nested
  file → the nested path.
- AC8 `omni_factories("s", git_init=True)[0].keywords == {"scenario": "s", "git_init":
  True}`; `tests/scenarios/todo_app/test_todo_run.py` asserts the same shape and no
  `artifact_name` attribute on the grader driver.
- AC9 V1 (engine suite, ruff) green; V2 (scenarios suite against the branch engine)
  green.
- AC10 Live, on the merged SHA, `caffeinate -i`, key unset: (a) `coding_workflow`
  todo_app run — both flows idle, no failed sessions, `session.json` has
  `artifact_exists: false`; (b) `swe_planning --n 1` — every flow's `session.json` has
  `artifact_exists: true` with `artifact_path` under its flow dir and `<flow>/plan.md`
  non-empty; `run.json.artifact_missing == []`.
