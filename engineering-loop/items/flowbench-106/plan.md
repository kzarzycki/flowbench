# Plan — flowbench #106 (E02 S02.6): error taxonomy

Worktree `/Users/zarz/dev/agents/flowbench--s026`, branch `loop/issue-106-error-taxonomy`,
base `origin/master` 1a6a714. Constraints copied from the spec: fallback values unchanged at
every site except the transitions the spec lists; `_resend_allowed` rows 1/3 unchanged, with
row 1 requiring a string message; waived sites keep `except Exception` with
`# noqa: BLE001 -- <reason>`; every site logs the swallowed exception at DEBUG via
`logging.getLogger(__name__)`; `BLE` enabled in ruff. Region rule in `driver/omnigent.py`:
only the import block, a new module-level `_label_read_errors()`, and the bodies of
`_resend_allowed`, `_context_tokens`, `_pane_tail`, `close`.

Execution order: Task 2 is already on the branch (`88fedd4`, cherry-picked onto 1a6a714).
Then Task 1, then Task 3 last — BLE can only be enabled once every driver catch is narrowed
or waived, so the branch is lint-green and test-green after each commit. Each task: tests
first (red), then the change (green), then `uv run ruff check . && uv run ruff format
--check . && uv run pytest -q`. Task 4 runs after merge.

## Task 1 — driver label reads, probe, teardown (`src/flowbench/driver/omnigent.py`)

Substrate: both reads are `labels = (await self._client.sessions.get(sid)).labels or {}`
under `asyncio.timeout(_LABEL_READ_S)`. Test doubles already in `tests/driver/test_omnigent.py`:
`_label_client(labels=None, boom=None)` (a `sessions.get` double: returns
`SimpleNamespace(labels=labels)` or raises `boom`), `_real_sdk_client(handler)` (the
installed `SessionsNamespace` over `httpx.MockTransport`), `_FakeSessions(..., get_error=)`.
A complete Session body for the real-SDK tests: `{"id": "c", "agent_id": "a", "status":
"idle", "created_at": 0, "updated_at": 0, "title": None, "items": [], "pending_inputs": [],
"labels": <labels>}` — define it once as a module-level `_session_body(labels)` helper (omit
the `labels` key when passed the sentinel `ABSENT`).

Tests (`tests/driver/test_omnigent.py`; `import logging` at the top; caplog assertions
everywhere: `[r for r in caplog.records if r.name == "flowbench.driver.omnigent" and
r.levelno == logging.DEBUG]` has length 1 and its `getMessage()` contains the exception text):
- `test_resend_allowed_is_false_when_the_read_fails` and
  `test_context_tokens_none_when_the_read_fails`: `boom=RuntimeError(...)` → change to
  `boom=httpx.ConnectError("transport gone")` (a transport error, still the fallback).
- `test_resend_allowed_reraises_a_foreign_exception` /
  `test_context_tokens_reraises_a_foreign_exception`: `boom=RuntimeError("driver bug")` →
  `pytest.raises(RuntimeError, match="driver bug")` (AC2).
- `test_resend_allowed_false_on_each_read_error` and
  `test_context_tokens_none_on_each_read_error` (parametrized `boom`: `OmnigentError("503")`,
  `TimeoutError()`, `KeyError("agent_id")`) → fallback + one DEBUG record (AC2/AC5).
- `test_resend_allowed_false_on_a_non_string_message` (parametrized message `None`, `7`,
  `["not delivered"]`, `{"not delivered": True}`, with code `runner_error`, via
  `_label_client`) → `False`, no DEBUG record (the guard decides, nothing is swallowed) (AC2).
- `test_context_tokens_none_on_a_garbage_label` (parametrized `"lots"`, `float("inf")`,
  `[1]`): `_label_client({"omnigent.last_context_tokens": <v>})` → `None` + one DEBUG record
  (`ValueError`, `OverflowError`, `TypeError`) (AC2).
- `test_label_reads_fall_back_on_an_overflowing_session_field`: real SDK, 200 with
  `_session_body({})` but `"created_at": 1e400` → `_resend_allowed()` `False`,
  `_context_tokens()` `None` (`Session.from_dict`'s `int()` raises `OverflowError`) (AC2).
- `test_label_reads_fall_back_through_the_real_sdk` (parametrized handler: 503 `json={}`;
  200 `text="<html>"` with `content-type: text/html`; 200 `json={"labels": {}}`, no Session
  fields) → `_resend_allowed()` is `False` and `_context_tokens()` is `None` (AC2).
- `test_context_tokens_none_on_a_503_carrying_the_label`: 503 with
  `_session_body({"omnigent.last_context_tokens": "123"})` → `None` (AC3).
- `test_resend_allowed_true_when_the_sdk_coerces_labels` (parametrized `[]`, `["x"]`, `""`,
  `0`, `None`, `ABSENT`): `_session_body(labels)` through `_real_sdk_client` → `True`
  (docstring: the coercion is `Session.from_dict`'s, row 3 applies) (AC2).
- `test_resend_allowed_logs_the_swallowed_error` / `test_context_tokens_logs_the_swallowed_error`:
  `boom=httpx.ConnectError("transport gone")` → fallback + one DEBUG record containing
  `"transport gone"` (AC5).
- `test_pane_tail_logs_the_swallowed_error(caplog)`: reuse `test_pane_tail_is_best_effort`'s
  `_Http` (OSError) → `None` + one DEBUG record; `test_close_logs_the_swallowed_error`: reuse
  `test_close_swallows_a_failing_client`'s `_Boom` → one DEBUG record (AC5).
- Doubles: `_FakeSessions.__init__` keeps `labels=None` in its signature (ruff B006 forbids a
  literal `{}` default) and stores `self._labels = {} if labels is None else labels`;
  `_label_client(labels=None, ...)` likewise normalises `None` to a fresh `{}` inside. The real
  SDK always hands a dict; with `or {}` gone a `None` double would raise `AttributeError` out
  of the driver — a test-double artefact, not a contract.
- Keep unchanged: `test_resend_allowed_reads_the_error_labels`,
  `test_resend_allowed_is_false_when_the_status_read_errors`,
  `test_resend_allowed_is_false_on_a_redirect_through_the_real_sdk`,
  `test_context_tokens_read_is_bounded`, `test_close_swallows_a_failing_client`,
  `test_pane_tail_is_best_effort` (AC6).

Change:
- Import block: `import logging`, `import httpx` (a core dependency); `log =
  logging.getLogger(__name__)`; after `_LABEL_READ_S` a module-level function
  `_label_read_errors() -> tuple[type[BaseException], ...]` whose body is
  `from omnigent_client import OmnigentError` (lazy: the live extra, see `start()`) then
  `return (OmnigentError, httpx.HTTPError, TimeoutError, KeyError, ValueError, TypeError,
  OverflowError)`, with a docstring naming the failure shapes from the spec.
- `_resend_allowed`: inside the existing `try`, after the read, `labels = (...).labels`
  (drop `or {}`), then the row-3/row-1 decision moves inside the `try` unchanged:
  `code = labels.get("omnigent.last_task_error_code")`; `if not code: return True  # row 3`;
  `msg = labels.get("omnigent.last_task_error_message")`;
  `return code == "runner_error" and isinstance(msg, str) and "not delivered" in msg  # row 1`
  (a non-string message — null, number, list, dict — is not the undelivered signal); then
  `except _label_read_errors() as e: log.debug("resend check: label read failed: %r", e);
  return False`. Keep the upstream comment about `sessions.get` raising.
- `_context_tokens`: drop `or {}`; keep `raw = labels.get(...)` and `return int(raw) if raw
  else None` inside the `try`; `except _label_read_errors() as e: log.debug("context tokens:
  label read failed: %r", e); return None`.
- `_pane_tail`: `except Exception as e:  # noqa: BLE001 -- best-effort probe: HTTP, JSON
  shape, tmux and timeout all mean "could not look"; a probe must never abort the send it
  observes` + `log.debug("pane tail unavailable: %r", e)`; `return None`.
- `close`: `except Exception as e:  # noqa: BLE001 -- teardown must never mask the real
  error` + `log.debug("close: %r", e)`.
- Also land here the two scorer tests from the first branch review
  (`test_collect_code_reraises_a_foreign_exception`; the `IsADirectoryError` text assertion
  in `test_collect_code_skips_an_unreadable_path`) — `git cherry-pick db467f9`, dropping its
  `test_omnigent.py` hunk (superseded by the `ABSENT` coercion case).

## Task 2 — `transcript.to_jsonable`, `watch._run_sessions`, `scorers.collect_code`

Tests:
Every caplog assertion below has the same shape as Task 1's: exactly one record with
`r.name == <logger>` and `r.levelno == logging.DEBUG`, message containing the exception text.
- (already on the branch as `88fedd4`) `tests/test_transcript.py`: `test_to_jsonable_falls_back_on_any_model_dump_error`
  (`model_dump` raises `RuntimeError("boom")` → repr fallback, same as the existing
  ValueError test) and `test_to_jsonable_logs_the_fallback(caplog)` (logger
  `flowbench.transcript`, message contains `"boom"`) (AC4/AC5).
- `tests/test_watch.py`: extend
  `test_run_watch_sessions_filters_by_project_and_survives_server_errors` (add `caplog`):
  after the existing `OSError("down")` case assert the DEBUG record from `flowbench.watch`
  containing `"down"`; then monkeypatch `urlopen` to raise `RuntimeError` and assert
  `pytest.raises(RuntimeError)` (AC4/AC5).
- `tests/scenarios/todo_app/test_scorers.py`: `test_collect_code_skips_an_unreadable_path
  (tmp_path, caplog)`: a directory named `broken.py` beside a real source → source present,
  `"broken.py"` absent from the output, one DEBUG record from
  `scenarios.coding_workflow.cases.todo_app.scorers` containing `"broken.py"` (AC4/AC5).

Change (each module adds `import logging` to its import block and a module-level
`log = logging.getLogger(__name__)` right after the imports):
- `src/flowbench/transcript.py`: `except Exception as e:  # noqa: BLE001 --
  the capture must survive whatever the client ships; a recording failure never aborts the
  turn it records` + `log.debug("model_dump(%s) failed, recording repr: %r",
  type(ev).__name__, e)`.
- `src/flowbench/watch.py`: also `import http.client`; `except (OSError,
  http.client.HTTPException, ValueError, AttributeError) as e: log.debug("sessions read
  failed, skipping tick: %r", e); return []`.
- `scenarios/coding_workflow/cases/todo_app/scorers.py`: `except (OSError, ValueError) as e:
  log.debug("skipping
  unreadable %s: %r", p, e); continue`.

## Task 3 — enable the rule (`pyproject.toml`)

- `select` gains `"BLE"`; `[tool.coverage.run] source = ["src", "scenarios"]`.
  `uv run ruff check .` clean (AC1); `rg 'except Exception' src/ scenarios/` shows only lines
  carrying `# noqa: BLE001` + reason (the two in `run.py` as written, new ones `-- reason`)
  plus the `acceptance.py` program-text literal.
- Full suite + `diff-cover` (`uv run pytest --cov --cov-report=xml && uv run diff-cover
  coverage.xml --compare-branch=origin/master --fail-under=100`) (V1). This is the last
  commit on the branch, so the gate measures every task.

## Task 4 — live validation (after the engine merge; `ANTHROPIC_API_KEY` unset)

Per `docs/roadmap/verification.md`: V4 (`swe_planning`) is mandatory for a send-policy
change; V5 (`todo_app`) is the brief's run. Both under `caffeinate -i`, lid open, watcher
attached, launched in the background with the PID captured. Runs root:
`/Users/zarz/dev/xebia/flowbench-runs/<scenario>/<run_id>/`.

Pre-flight (both): omnigent server up (`curl -s http://127.0.0.1:6767/v1/sessions?limit=1`),
host readiness `claude-native` online (the runner's own check), `env | grep -c ANTHROPIC_API_KEY`
= 0.

- **V5 — from the engine worktree** `/Users/zarz/dev/agents/flowbench--s026`, detached at
  the merge SHA (`git checkout <merge-sha> && uv sync --extra dev --extra live`; verify
  `uv run python -c "import flowbench.driver.omnigent as m; print(m.__file__)"` resolves
  into that worktree and `git rev-parse HEAD` equals the merge SHA). Runs root: pass it
  explicitly so launch, watcher, assertions and `compare` agree —
  `RUNS=/Users/zarz/dev/xebia/flowbench-runs/coding_workflow`, `--runs-root $RUNS` (the
  engine's `default_runs_root()` would otherwise be `/Users/zarz/dev/agents/flowbench-runs/`).
  Launch: `caffeinate -i uv run python -m scenarios.coding_workflow.run --case todo_app
  --run-id s026-<hhmm> --runs-root "$RUNS" > "$RUNS/s026-<hhmm>.log" 2>&1 &
  runner_pid=$!` (assign immediately, before any other background job). Watcher, same cwd,
  the engine's `RunWatch` (the class the swe_planning watcher wraps; there is no
  coding_workflow CLI for it) as a script taking run id, runs root and runner pid on argv —
  nothing is interpolated into the heredoc:
  ```
  cat > "$RUNS/watch_s026.py" <<'PY'
  import os, sys, time
  from pathlib import Path
  from flowbench.watch import RunWatch
  run_id, runs_root, pid = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
  w = RunWatch(run_id, runs_root=runs_root, scenario="coding_workflow")
  while True:
      for e in w.tick(): print(time.strftime("%H:%M:%S"), e, flush=True)
      if w.run_complete() is not None: print("RUN COMPLETE", flush=True); break
      try: os.kill(pid, 0)
      except ProcessLookupError: print("RUNNER EXITED without run.json", flush=True); break
      time.sleep(15)
  PY
  uv run python "$RUNS/watch_s026.py" s026-<hhmm> "$RUNS" "$runner_pid" \
      > "$RUNS/s026-<hhmm>.watch.log" 2>&1 &
  watcher_pid=$!
  wait "$runner_pid"; runner_rc=$?
  ```
  Success: `runner_rc` is 0; `$RUNS/s026-<hhmm>/run.json` present;
  `run.json["flow_stats"][f]["exit_status"] == "idle"` for `baseline` and `superpowers`;
  both `<flow>/scorecard.json` present without an `error` key;
  `<flow>/session.json["flaked_turns"]` read and recorded per flow — a positive count is
  accepted (policy row 2: FAILED after the reply landed) and noted in the ledger as the
  first live evidence, not a failure; `uv run flowbench compare --run-base $RUNS --run-id
  s026-<hhmm>` exits 0 with both columns and no FAILED banner; the watch log holds 0 anomaly
  lines (`PERMISSION PROMPT`, `SERVER`, `SESSION FAILED`, `STALLED`); 0 `Traceback` lines
  in the run log.
- **V4 — from the scenarios worktree** `/Users/zarz/dev/xebia/flowbench-scenarios--s026`,
  engine pinned to the merge: `uv lock --upgrade-package flowbench` (the lock must show
  `#<merge-sha>`), `uv sync --extra live`, verify `uv run --extra live python -c "import
  flowbench, subprocess; print(flowbench.__file__)"` imports from the uv cache checkout of
  that SHA (not `--s026`, not the shared checkout). Then:
  `PRUNS=/Users/zarz/dev/xebia/flowbench-runs/swe_planning`; `caffeinate -i uv run --extra
  live python -m scenarios.swe_planning.run --run-id s026-plan-<hhmm> --n 1 >
  "$PRUNS/s026-plan-<hhmm>.log" 2>&1 & plan_pid=$!`; then `uv run --extra live python -m
  scenarios.swe_planning.watch s026-plan-<hhmm> --pid "$plan_pid" >
  "$PRUNS/s026-plan-<hhmm>.watch.log" 2>&1 & plan_watch_pid=$!`; `wait "$plan_pid";
  plan_rc=$?`. Success: `plan_rc` is 0 (the watcher exiting is not proof — it also exits
  when the runner dies without `run.json`); `run.json` present with `winner` parsed (not `unknown`/None); every flow dir
  holds `plan.md` + `transcript.md` + `session.json`; all flows `exit_status == idle`; 0
  watcher anomaly lines; 0 `Traceback` lines in the run log.
- The uv.lock bump is the paired scenarios PR's content, with the ledger + HANDOFF.
- Anomaly → `loop:regression` issue with watcher output and run dir; the fix is part of
  this item (rule 7). Environmental failures (host flap, quota, sleep) are re-run, not
  reverted.

Criterion → task → test: AC1→T3 (ruff, last commit); AC2→T1 (reraise, read-error,
non-string-message, garbage-label, real-SDK body/overflow, coercion tests); AC3→T1 (real-SDK
503 test); AC4→T2 (transcript/watch/scorers tests); AC5→T1 (caplog on the four driver sites)
+ T2 (three caplog tests); AC6→T1 (kept tests); V1→T3 (coverage over src + scenarios,
measured after every task); V4/V5→T4.
