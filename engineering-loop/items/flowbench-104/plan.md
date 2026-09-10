# Plan — flowbench #104 (E02 S02.4)

Engine worktree `ENG=/Users/zarz/dev/agents/flowbench--s024`, branch
`loop/issue-104-s02-4-artifact-probe`. Scenarios worktree
`SCEN=/Users/zarz/dev/xebia/flowbench-scenarios--s024`, same branch name (its venv has the
engine worktree installed editable: `uv pip install -e $ENG`). Every task: failing test →
code → `uv run pytest -q` green → `uv run ruff check . && uv run ruff format --check .`
clean → commit. Stay out of `OmnigentDriver.start`, the client import block, the
labels-only GETs and every `except Exception` site (S02.5 / S02.6 regions).

## Global constraints (from spec)

- `TurnResult` has no `artifact_exists`; `AgentDriver` has no `artifact_path`;
  `OmnigentDriver` has no `artifact_name`, no `artifact_path()`, no `artifact_*` keys in
  `capture_session()`, no filesystem call inside `send`.
- `run_agent_session(..., artifact_grace_s=60.0, artifact_probe=None)`; the DONE
  grace-poll is `to_thread(probe)` every 2 s under `asyncio.timeout(artifact_grace_s)`;
  after capture the loop sets `artifact_exists`/`artifact_path`/`artifact_text` on the
  session for every session (`False/None/None` without a probe).
- `run.py` owns `find_artifact`; `run_case` builds the probe; `artifact_name` is a
  `run_case`/`run_case_n` parameter only.
- `rg __none__` empty (AC1 scope).

## Task A — probe in the loop and `run.py`, fakes write to disk (AC3–AC8; additive, suite green)

Files: `src/flowbench/loop.py`, `src/flowbench/run.py`, `src/flowbench/testing.py`,
`src/flowbench/driver/base.py`, `scenarios/coding_workflow/run.py`, `tests/test_loop.py`,
`tests/test_run.py`, `tests/driver/test_omnigent.py` (line 23 only),
`tests/scenarios/todo_app/test_todo_run.py`. `OmnigentDriver` is NOT touched in this task
beyond the one-line default in step 5; it
keeps returning its `artifact_*` capture keys, which the loop now overwrites with the
probe's answer (identical values for the real driver).

1. Tests first, `tests/test_loop.py` (its `_FakeDriver` loses `artifact_path`):
   - AC3 `test_done_waits_for_pending_artifact`: a probe closure returning `None` on the
     first two calls, then `tmp_path / "plan.md"` (written with text "plan"); `asyncio.sleep`
     monkeypatched to a no-op as today; assert `calls >= 3`, `session["artifact_exists"] is
     True`, `session["artifact_path"] == str(tmp_path / "plan.md")`,
     `session["artifact_text"] == "plan"`.
   - AC4 `test_done_grace_poll_is_bounded_by_wall_clock`: probe = closure that on its
     first call does `time.sleep(1.0); return None` and on later calls returns `None` at
     once; `artifact_grace_s=0.1`; assert elapsed `< 1.0` and `artifact_exists is False`.
   - AC5 `test_no_probe_skips_poll_and_reports_no_artifact`: `artifact_probe` omitted,
     `asyncio.sleep` monkeypatched to record calls; assert not called, and the three keys are
     `False/None/None`.
2. `loop.py`: signature gains `artifact_probe: Callable[[], Path | None] | None = None`
   (import `Callable` from `collections.abc`, `Path` from `pathlib`). DONE branch:
   ```python
   if artifact_probe is not None:
       try:
           async with asyncio.timeout(artifact_grace_s):
               while await asyncio.to_thread(artifact_probe) is None:
                   await asyncio.sleep(2.0)
       except TimeoutError:
           pass  # grace spent (or a hung filesystem): capture what is there
   ```
   After `capture_session()`:
   ```python
   artifact = await asyncio.to_thread(artifact_probe) if artifact_probe else None
   session["artifact_exists"] = artifact is not None
   session["artifact_path"] = str(artifact) if artifact else None
   session["artifact_text"] = artifact.read_text() if artifact else None
   ```
   Module/parameter docstring: the probe is the orchestrator's "which file proves
   delivery"; the driver knows nothing about it.
3. `base.py`: remove the abstract `artifact_path` (the fakes below drop it; `OmnigentDriver`
   still defines its own until Task B). `tests/driver/test_omnigent.py:23`: drop
   `"artifact_path"` from the abstract-method list.
   `testing.py`: `FakeDriver.__init__(self, plan_text, questions, run_dir=None)`;
   `start()` writes `Path(run_dir) / "plan.md"` = `plan_text` when `run_dir` is set;
   `MissingPlanDriver.start()` is a no-op; drop `artifact_path` and the `artifact_text` key
   from both fakes' `capture_session()`; `n_run_factories.make_flow_driver` passes
   `run_dir=flow_dir`. `ScriptedDriver` unchanged.
4. Tests first, `tests/test_run.py`:
   - AC7 `test_find_artifact_missing_top_level_nested`: missing → `None`; `tmp/plan.md` →
     that path; only `tmp/sub/plan.md` → the nested path.
   - AC6 `test_run_case_offline` / `test_run_case_flags_missing_plan`: fakes built with
     `run_dir=flow_dir` (`MissingPlanDriver("unused", [], run_dir=flow_dir)` too);
     assertions unchanged.
   - `test_run_case_artifact_none_omits_artifact_keys` (901-925): stop using
     `n_run_factories`; build local fakes `FakeDriver("# p", [])` with NO `run_dir` and
     `StubSim(["PLAN_COMPLETE"])`, so nothing lands on disk and the `not (root / name /
     "plan.md").exists()` assertion stays meaningful.
   - Replace `test_run_case_artifact_none_forwards_zero_grace` (929-981) with
     `test_run_case_builds_probe_from_flow_dir`: same `rec` monkeypatch of
     `run_mod.run_agent_session`; `artifact_name=None` → every call has
     `kwargs["artifact_probe"] is None` and `kwargs["artifact_grace_s"] == 30.0`; default →
     `kwargs["artifact_probe"].func is run_mod.find_artifact` and `.args == (flow_dir,
     "plan.md")` for the flow's dir (`tmp_path / "t-default" / <flow name>`), grace 30.0.
   - AC8 `test_omni_factories_artifact_name_and_git_init` (883-898) → rename
     `test_omni_factories_git_init`: `omni_factories("x", git_init=True)[0].keywords ==
     {"scenario": "x", "git_init": True}`; default → `{"scenario": "x", "git_init":
     False}`; the built driver has `git_init` accordingly. No `artifact_name` anywhere.
   - `test_make_flow_driver_omni_maps_flow_config` (210): delete the
     `d.artifact_name == "plan.md"` line. `test_make_simulator_omni_is_bare_claude_on_a_
     session_model` (666): delete the `d.artifact_name == "__none__"` line.
   - `test_run_case_n_forwards_artifact_name`: keep (`artifact_name` is still a
     `run_case_n` kwarg).
   - `tests/scenarios/todo_app/test_todo_run.py`: keywords `{"scenario": "coding_workflow",
     "git_init": True}` (49-53); line 166 `d.artifact_name == "__none__"` → `not
     hasattr(d, "artifact_name")` (passes only after Task B — so run Task A's suite with
     that one line still as `== "__none__"`, and flip it in Task B).
5. `run.py`: add `find_artifact(run_dir: Path, name: str) -> Path | None` (top-level hit,
   else first `rglob` hit, else `None`); in `run_case` replace
   `artifact_grace_s=(artifact_grace_s if has_artifact else 0.0)` with
   `artifact_grace_s=artifact_grace_s, artifact_probe=(functools.partial(find_artifact,
   flow_dir, artifact_name) if has_artifact else None)`; drop `artifact_name` from
   `make_flow_driver_omni` and `omni_factories`. The driver field `artifact_name` has no
   default today, so Task A gives it one — `artifact_name: str = "__none__"` in
   `omnigent.py` (one line, deleted with the field in Task B) — and no factory passes it
   any more. Fix the
   `omni_factories` docstring. `make_simulator_omni`/`run_judge_omni` drop the sentinel
   kwarg (default now). `scenarios/coding_workflow/run.py`: `omni_factories(SCENARIO,
   git_init=True)`; `scenarios/coding_workflow/cases/todo_app/scoring.py` `make_grader_omni`
   drops the sentinel kwarg.
6. `uv run pytest -q` green, ruff clean, commit.

## Task B — strip the driver, ABC and `TurnResult` (AC2, part of AC1; suite green)

Files: `src/flowbench/types.py`, `src/flowbench/driver/omnigent.py`, `tests/test_types.py`,
`tests/driver/test_omnigent.py`,
`tests/driver/test_config.py`, `tests/driver/test_bundle.py`, `tests/test_model.py`,
`tests/test_loop.py`, `tests/scenarios/todo_app/test_todo_run.py`.

1. Tests first: `tests/test_types.py` — `"artifact_exists" not in {f.name for f in
   dataclasses.fields(TurnResult)}`; line 35 `TurnResult(TurnStatus.IDLE, "", False)` →
   `TurnResult(TurnStatus.IDLE, "")`. `tests/driver/test_omnigent.py` — new
   `test_driver_has_no_artifact_concern`: `not hasattr(AgentDriver, "artifact_path")`,
   `d = OmnigentDriver(run_dir=tmp_path)` constructs, `not hasattr(d, "artifact_name")`,
   `not hasattr(d, "artifact_path")`; delete `test_artifact_path_none_when_missing` (48-52)
   and `test_hard_ceiling_covers_a_slow_filesystem` (827-845); in
   `test_capture_session_returns_the_run_fields` (1566-1578) delete the three `artifact_*`
   assertions and add `assert not {"artifact_exists", "artifact_path", "artifact_text"} &
   out.keys()`; the abstract-method list at line 23 drops `"artifact_path"`.
   `tests/scenarios/todo_app/test_todo_run.py:166` → `not hasattr(d, "artifact_name")`.
2. `types.py`: remove the field. `omnigent.py`:
   remove the `artifact_name` field (and its Task-A default) + docstring line,
   `artifact_path()`, the `artifact` block in `capture_session()`, the `artifact_exists=`
   kwarg in `_send_once`'s `TurnResult`, `_timed_out()` → `TurnResult(TurnStatus.TIMEOUT,
   "")`; `run_dir` doc → "absolute cwd the agent works in".
3. Mechanical, `src/` and `tests/`: every `TurnResult(<status>, <text>, False` →
   `TurnResult(<status>, <text>` (incl. `testing.py:46-47`, `test_model.py`, `test_loop.py`,
   `test_omnigent.py`; `assert result == TurnResult(TurnStatus.TIMEOUT, "", False)` →
   `TurnResult(TurnStatus.TIMEOUT, "")`); every `OmnigentDriver(..., artifact_name="...")`
   in tests drops the kwarg (`test_config.py`, `test_bundle.py`, `test_omnigent.py`).
4. `uv run pytest -q` green, ruff clean, commit.

## Task C — docs + `rg __none__` (AC1, part of AC9)

Files: `docs/design/runner.md`, `docs/roadmap/current-state.md`,
`docs/roadmap/target-architecture.md`, `docs/roadmap/ROADMAP.md`,
`docs/roadmap/epics/E02-runtime-robustness.md`, `CLAUDE.md`,
`docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md` (ABC method list).

Edits per spec §7. Verify: `rg -n __none__ $ENG` → empty; `rg -n "artifact_path|
artifact_name" $ENG/src $ENG/docs/design` → only `run_case`/`run_case_n`/`find_artifact`
and the session-key names. `uv run pytest -q`, ruff. Commit.

## Task D — scenarios repo (AC9 V2, AC1)

Files: `scripts/agent_review.py`, `tests/test_agent_review.py`,
`tests/test_swe_planning_run.py` in `$SCEN`.

Drop the kwarg; `_result` → `TurnResult(status=status, assistant_text=text)`; keywords
expectation `{"scenario": "swe_planning", "git_init": False}`. `uv run --no-sync pytest -q`
green against the editable engine. `rg -n __none__ $SCEN --glob '!.claude/engineering-loop/LOG.md'
--glob '!docs/superpowers/**' --glob '!.workflow/**' --glob '!.claude/engineering-loop/items/**'`
→ empty. Commit (loop artifacts need `git add -f`). `uv.lock` bump is post-merge
(Task F).

## Task E — gates 3/4, ship engine PR

Gate 3 (fresh reviewer, diff `origin/master...HEAD`), gate 4 (`gates.md`: suite, ruff,
`git fetch && git rebase origin/master`, suite again). PR against `master`, `Closes #104`,
`--squash` merge, poll checks.

## Task F — scenarios PR + live gate (AC10)

`cd $SCEN && uv lock --upgrade-package flowbench` (→ merged SHA), `uv sync --extra live`,
suite green, ledger entry in `LOG.md` + `HANDOFF.md` rewrite, PR against `main`, merge.
Live (key unset, `caffeinate -i`, from `$SCEN` on the merged lock):
`coding_workflow` todo_app run (`--run-id s024-<hhmm>`) and `swe_planning --n 1`
(`--run-id s024-plan-<hhmm>`), each with the watcher. Record outcomes in `gates.md` and
the ledger; a defect reopens #104 (rule 7).

## Traceability

| AC | Task | Test |
| --- | --- | --- |
| AC1 | A, B, C, D | `rg __none__` (gate 4 command in `gates.md`) |
| AC2 | B | `test_types.py` fields test; `test_driver_has_no_artifact_concern` |
| AC3 | A | `test_done_waits_for_pending_artifact` |
| AC4 | A | `test_done_grace_poll_is_bounded_by_wall_clock` |
| AC5 | A | `test_no_probe_skips_poll_and_reports_no_artifact` |
| AC6 | A | `test_run_case_offline`, `test_run_case_flags_missing_plan` |
| AC7 | A | `test_find_artifact_missing_top_level_nested` |
| AC8 | A | `test_omni_factories_git_init`, `test_todo_run.py` keywords |
| spec §3 probe wiring | A | `test_run_case_builds_probe_from_flow_dir` |
| AC9 | C, D | `gates.md` |
| AC10 | F | live run dirs + `gates.md` |
