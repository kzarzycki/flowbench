# Plan — flowbench #59

Worktrees: engine `/Users/zarz/dev/agents/flowbench--issue-59` (branch
`loop/issue-59-artifact-vocab`, off `origin/master`); scenarios
`/Users/zarz/dev/xebia/flowbench-scenarios--issue-59` (branch `loop/issue-59-ledger`,
off `origin/main`) for this item dir + the ledger entry.

Global constraints, verbatim from spec.md:
- "No back-compat shim for `plans_missing`/`plan_lines`."
- "`artifact_name is None` → neither key appears anywhere in `run.json`, no `plan.md`
  is written, and the artifact grace-poll is skipped."
- "`--rescore` only ever writes `scorecard.json` and `run.json`'s `flow_stats` inside an
  existing run dir; it never starts a flow session and never touches transcripts or
  `session.json`."
- "`artifact_name="__none__"` as the driver-level sentinel stays."

Each task ends with `uv run pytest -q` green in the engine worktree.

## T1 — `run_case`/`run_case_n` take `artifact_name: str | None` (AC 1,2,3,4,13)

`src/flowbench/run.py`:
- `run_case(..., artifact_name: str | None = "plan.md")`, docstring line saying `None`
  means the case declares no artifact.
- In the flow loop, `has_artifact = artifact_name is not None`. Pass
  `artifact_grace_s=(artifact_grace_s if has_artifact else 0.0)` into
  `run_agent_session`.
- Write `<flow_dir>/plan.md` only when `has_artifact`.
- `flow_stats[name]` gets `"artifact_lines": len((plan_text or "").splitlines())` only
  when `has_artifact`, as one dict literal so the key keeps its old position:
  `{"exit_status": …, "turns": …, "duration_s": …,
  **({"artifact_lines": len((plan_text or "").splitlines())} if has_artifact else {}),
  "context_tokens": …}`.
- `meta`: replace `"plans_missing"` with `"artifact_missing"`, added only when
  `has_artifact`.
- Right after `has_judge` is computed, reject the unrenderable combination:
  `if artifact_name is None and has_judge: raise ValueError(...)` naming both the case
  dir and that the HTML report needs `<flow>/plan.md` — before any driver is built.
- `run_case_n(..., artifact_name: str | None = "plan.md")` → into the `kwargs` dict it
  forwards to `run_case`.
- `omni_factories(scenario, *, artifact_name: str | None = "plan.md", git_init=False)`:
  `functools.partial(make_flow_driver_omni, …, artifact_name=artifact_name or "__none__")`.
  Docstring: `None` = the case declares no artifact (driver sentinel `"__none__"`).
  `make_flow_driver_omni` keeps its `str` parameter unchanged.

Tests, `tests/test_run.py`:
- Rename the two existing assertions (`meta["plans_missing"] == []` at ~:84 and
  `== ["plain"]` at ~:122) to `meta["artifact_missing"]`, and add to the first
  `assert "plans_missing" not in meta and "plan_lines" not in json.dumps(meta)`
  → AC1 (the existing test also already asserts `flow_stats`; extend the
  `plan_lines` assertion at ~:390 to `artifact_lines`).
- New `test_run_case_artifact_none_omits_artifact_keys`: the unjudged-case helper
  (`_unjudged_case`, already in this file) + `FakeDriver`s, `artifact_name=None`, AND a
  `score_flow` returning `{"flow": flow["name"]}` (the unjudged case's only scoring
  path); assert the `run.json` TEXT contains none of the four names,
  `not (root/f/"plan.md").exists()` for both flows, and that `session.json`,
  `transcript.md` and `scorecard.json` all exist, the last parsing to the scorer's dict
  → AC2.
- New `test_run_case_artifact_none_forwards_zero_grace`: same monkeypatch shape as the
  existing `test_run_case_forwards_artifact_grace` (`tests/test_run.py:163-196`) —
  recorder over `run_mod.run_agent_session` — called with `artifact_grace_s=30.0` and
  `artifact_name=None`; assert every recorded call got `artifact_grace_s == 0.0`, and a
  companion call with the default `artifact_name` still gets `30.0` → AC3 (deterministic,
  not timing-based).
- New `test_run_case_n_forwards_artifact_name`: monkeypatch `flowbench.run.run_case`
  with a recorder coroutine returning a minimal meta
  (`{"winner_flow": None, "labels": {}, "scores": {}}`), call `run_case_n` with
  `n=1` and `n=2`, assert `artifact_name=None` appears in every recorded kwargs → AC4.
- New `test_run_case_artifact_none_with_judge_rejected`: `CASE_DIR` (has `judge.md`) +
  `artifact_name=None` → `pytest.raises(ValueError)`, and no run dir contents beyond
  what `mkdir` made (factories that raise if called) → AC13.
- `test_omni_factories_artifact_name_and_git_init` (~:880): add
  `omni_factories("x", artifact_name=None)[0](flow, dir).artifact_name == "__none__"`
  → AC5.

## T2 — readers: watch + report (AC 6,7)

- `src/flowbench/watch.py` ~:113: build the trial line as
  `f"TRIAL DONE: {trial} winner={meta.get('winner_flow')}"` plus
  `f" missing={meta['artifact_missing']}"` only when the key is present.
- `src/flowbench/report/run_report.py`: `:79` fallback key and `:94` read become
  `artifact_lines` (keep `or len(plan.splitlines())`); the card key stays `plan_lines`
  (HTML-local name, `:150`/`:158` untouched).
- Same file `:82`: guard the artifact read — `p = run_root / name / "plan.md"; plan =
  p.read_text() if p.exists() else ""`. AC13 stops `run_case` from producing an
  unrenderable run, but `render_report` is also a standalone entry point
  (`run_report.py:251`) that a human can point at an artifact-less run dir; today that
  is a bare `FileNotFoundError`.
- Test for the guard: `flow_card` over a flow dir with `session.json` but no `plan.md`
  → `card["plan_lines"] == 0` and `card["plan_html"] == ""`, no exception.
- Tests: `tests/test_watch.py:44` fixture → `artifact_missing`, assert the rendered
  event contains `missing=[]`; new case with no `artifact_missing` key asserts the
  event has no `missing=`. `tests/report/test_run_report.py:130` — feed `flow_stats`
  with `artifact_lines` and assert `card["plan_lines"]` picks it up.

## T3 — `rescore_run` in the engine (AC 8,9,10)

New in `src/flowbench/run.py`:

```python
async def rescore_run(case_dir, run_root, *, score_flow) -> dict[str, str]:
```
- `flows_by_name = {f["name"]: f for f in load_flows(Path(case_dir) / "flows.yaml")}`.
- Targets: every `p` in `[run_root, *sorted(run_root.glob("trial-*"))]` whose
  `run.json` exists and parses to a dict containing `"flow_stats"`.
- For each target, for each `name` in its `run.json["flows"]`: skip when
  `<target>/<name>/session.json` is absent (record nothing). Else load the session,
  `card = await score_flow(flows_by_name[name], flow_dir, session)` inside the same
  try/except as `run_case` (`except Exception as e` → `card = {"error": …}`), write
  `scorecard.json`, then `stats = meta["flow_stats"].setdefault(name, {})` and either
  `stats.pop("score_error", None)` or `stats["score_error"] = error`.
- Rewrite the target's `run.json` (same `json.dumps(..., indent=2, default=str)`).
- Return `{key: "ok" | error}` where `key` is `name` for the flat layout and
  `f"{target.name}/{name}"` for a `trial-*` target.
- A flow that has a `session.json` but no entry in the case's current `flows.yaml`
  (flows.yaml edited since the run) is NOT special-cased: the `flows_by_name[name]`
  lookup raises `KeyError`, caught by the same guard as any scorer failure, so the flow
  is recorded as `"KeyError: '<name>'"` in both the card and `flow_stats.score_error` and
  the run continues. Rationale: a scorecard written from a flow config that no longer
  matches the run would be worse than a recorded error. To make this deliberate, the
  lookup sits INSIDE the try.

Tests, new `tests/test_rescore.py`: build a synthetic run dir by hand (write
`run.json` with `flows`, `flow_stats` incl. a stale `score_error` on one flow, plus
`<flow>/session.json` for each) against `tests/fixtures/feature_flag_service`'s
`flows.yaml`:
- success path rewrites both scorecards, clears the stale `score_error`, returns
  `{"superpowers": "ok", "plain": "ok"}`, and leaves `session.json`/`transcript.md`
  byte-identical → AC8a.
- a `score_flow` raising for one flow only: that card is `{"error": …}`, its
  `flow_stats.score_error` is set, the sibling is still rescored → AC8b.
- `n>1` layout (`trial-01/`, `trial-02/`, aggregate `run.json` without `flow_stats`):
  every trial rescored, keys `"trial-01/plain"` etc., aggregate `run.json` untouched
  → AC9.
- a flow dir with no `session.json`: absent from the return map, its `scorecard.json`
  unchanged → AC10.
- a `run.json` naming a flow absent from `flows.yaml`: that flow's entry in the return
  map starts with `"KeyError"`, its card is `{"error": ...}`, `flow_stats.score_error` is
  set, and the sibling flow still rescores → AC8c.

## T4 — `coding_workflow` CLI: `--rescore` + `ARTIFACT_NAME = None` (AC 11,12)

`scenarios/coding_workflow/run.py`:
- Import line becomes `from flowbench.run import omni_factories, rescore_run, run_case_n`
  and the CLI calls the bare name `rescore_run(...)` — the AC11 test monkeypatches
  `scenarios.coding_workflow.run.rescore_run`, which only binds a module-level name.
- Module constant `ARTIFACT_NAME = None  # the deliverable is the running app, judged
  black-box by acceptance.py — no file artifact` and use it in both
  `omni_factories(SCENARIO, artifact_name=ARTIFACT_NAME, git_init=True)` and
  `run_case_n(..., artifact_name=ARTIFACT_NAME)`.
- `--rescore <run_id>` argument. In `main()`, when set: resolve
  `runs_root/<run_id>` (error out with `SystemExit` if it is not a directory),
  `asyncio.run(rescore_run(scenario.CASE_DIR(args.case), run_root, score_flow=<the same
  functools.partial(score_todo_app, make_grader=…) the live path builds>))`, print the
  returned map as JSON, return before building the factories.
  Factor the partial into a local `score_flow = …` used by both paths.
- `--rescore` and `--run-id` are not mutually exclusive at argparse level (a rescore
  simply ignores `--run-id`); the help text says `--rescore` takes the run id.
- Docstring gains the rescore usage line.

Tests, `tests/scenarios/todo_app/test_todo_run.py`:
- `--rescore` path: monkeypatch `scenarios.coding_workflow.run.rescore_run` with a
  recorder, `omni_factories` with a boom that raises if called, run `main()` with
  argv `["--rescore", "r1", "--runs-root", str(tmp_path)]` (create `tmp_path/r1`);
  assert the recorder saw `case_dir` ending `todo_app`, `run_root == tmp_path/"r1"`,
  `score_flow.func is score_todo_app`, and that the factories were never built → AC11.
- extend the existing wiring test (~:51) to assert the flow-driver partial's
  `artifact_name` keyword is `"__none__"` and the bound `run_case_n` kwargs carry
  `artifact_name is None` → AC12.

## T5 — docs (AC 14)

- `docs/design/runner.md:93-95`: `omni_factories(scenario, *, artifact_name: str | None
  = "plan.md", git_init=False)`; "todo_app binds `artifact_name=None` (no artifact — the
  deliverable is the app) and `git_init=True`"; one sentence on `rescore_run`.
- Engine `CLAUDE.md:47`: same signature fix; `run.py` bullet mentions `rescore_run`; the
  "Run it" block gains the `--rescore` invocation.
- Check: `grep -r 'artifact_name="tasks.json"' CLAUDE.md docs/` returns nothing.
- `scenarios/coding_workflow` docstring covered in T4.

## T6 — scenarios repo (AC 15)

In `/Users/zarz/dev/xebia/flowbench-scenarios--issue-59` on `loop/issue-59-ledger`:
`.claude/loop.md:347` `no plans_missing` → `no artifact_missing` (that clause only;
`git diff` on the file must be one line). Owner approved this edit 2026-09-09. Plus
this item dir and the ledger entry. Merged AFTER the engine PR.

## Gates

`uv run pytest -q` (expect 188 + ~11 new, 1 skipped), `uv run ruff check .`,
`grep -r 'artifact_name="tasks.json"' CLAUDE.md docs/` returns nothing (AC14),
`uv run ruff format --check .`, rebase on `origin/master`, adversarial whole-branch
review, PR + squash-merge (engine first), then the scenarios ledger PR.

## Live validation (Phase 9.5)

`--rescore` against a COPY of `todo-app-004` in the session scratchpad (never the
original): omnigent is up on 127.0.0.1:6767 and `ANTHROPIC_API_KEY` is unset, so the
superpowers flow — the one whose scorecard carries the real `score_error` from the
lid-close — is re-scored for real through the live grader. Clean = both scorecards
rewritten, `score_error` gone from `run.json`'s `flow_stats`, `session.json` untouched.
