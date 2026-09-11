# flowbench

A benchmark that compares **agentic flows** on a fixed **case**, all driven through a
**meta-harness** (omnigent today). A *flow* is one complete configuration for driving a coding
agent at a goal: harness (Claude Code today; Codex, pi/omp next), model, reasoning effort, and a
bundle of skills/MCPs. Every field is declared and recorded; nothing steers the agent from hiding,
so a comparison can state exactly which knobs differ.

Vocabulary → **`docs/GLOSSARY.md`** (Scenario → Case → Flow → Run → Scorecard → Comparison).
Authoring or changing a case (the folder format, the `Case` contract, discovery) →
**`docs/design/case.md`**.
Getting a live run working (omnigent install/topology, readiness check, the key rule) →
**`docs/onboarding.md`**. Why omnigent is the meta-harness →
`docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md`.

## Engineering loop

All changes, in this repo and in `$SCENARIOS`, follow `engineering-loop/README.md`
(interactive sessions too): claim on the board → spec/plan sized to the change →
cross-vendor review gates → PR → merge (standing approval) → live-run validation →
one ledger entry in `engineering-loop/LOG.md` (read it first when resuming work).
Epics run through `engineering-loop/coordinator.md`. The layer is harness-agnostic:
this file is `AGENTS.md`, read by any coding agent; `CLAUDE.md` only imports it.
Engine PRs here merge BEFORE the paired scenarios PR; the live run validates both.

`$SCENARIOS` is the private scenarios/cases checkout. Where it sits is per-developer,
so the path is not tracked here — record it in `CLAUDE.local.md` (untracked).

## Run it

```bash
uv sync --extra dev --extra live        # live = the omnigent runtime for live runs
uv run pytest -q                        # offline suite (live-agent tests skipped)

# the engine's own live gate — two minutes, one flow, one file (needs a live omnigent server
# + ANTHROPIC_API_KEY unset — see docs/onboarding.md):
uv run --extra live flowbench run scenarios/smoke/hello --run-id <id>

# the reference case live, watched from a second shell once the run dir exists:
uv run --extra live flowbench run scenarios/swe_e2e/cases/todo_app --run-id <id>
uv run flowbench watch <id> --pid <runner-pid>

# compare flows side by side after a run (reads <run_id>/<flow>/scorecard.json):
uv run flowbench compare --run-base $RUNS/todo_app --run-id <id>

# re-score an existing run's flows without re-driving anything (dead grader, scorer fix):
uv run flowbench run scenarios/swe_e2e/cases/todo_app --rescore <id>
```

## Layout

- `src/flowbench/types.py` — the engine's vocabulary of turn outcomes: `TurnStatus` (a `StrEnum`),
  `TurnResult`, and the `UserModel`/`Completion` protocols `run_agent_session` drives.
- `src/flowbench/driver/` — the agent-eval runtime's spawning half: `base.py` (`AgentDriver` ABC),
  `omnigent.py` (`OmnigentDriver`: session lifecycle, send/settle, capture, subscription guard),
  `bundle.py` (`render_config`/`build_bundle`/`session_metadata` — the per-flow skills/MCP bundle,
  as pure functions of a `BundleSpec`).
- `src/flowbench/loop.py` — `run_agent_session`, the DONE-token turn loop.
- `src/flowbench/runner/` — what is left: `flow.py` (`Flow` = one configuration; bundle fields
  today, full schema in S03.1), `judge.py`, plus `driver.py`/`loop.py` compat re-exports that go
  away one release after S02.2.
  Touching `src/flowbench/driver/` or `src/flowbench/loop.py`? Read `docs/design/runner.md`
  first (driver/loop contracts, one-execution-model decision).
- `src/flowbench/case.py` — `Case` (deliverable, budgets, setup/teardown, `score`), `load_case`
  (nearest `case.py` from the case folder up to the inclusive `scenarios` root, exactly one
  subclass), `check_gradable` (the two load-time errors). A case is a folder;
  `docs/design/case.md` is the format.
- `src/flowbench/settings.py` — `Settings`: `runs_root`, `sim_model`, `judge_model`, layered
  init > `FLOWBENCH_*` env > `.env` > `[tool.flowbench]` > default.
- `src/flowbench/run.py` — `run_case`/`run_case_n`: the one orchestrator, taking a `Case` (flows
  + simulator + `case.score` + optional judge → `<runs_root>/<case>/<run_id>` → `run.json`,
  `report.html`); also `rescore_run(case, run_root)`, which re-runs `case.score` over an existing
  run dir's `<flow>/session.json` files in place, with no new session. Helpers:
  `model.py` (`SessionModel`), `flowspec.py` (flows.yaml), `transcript.py`, `watch.py`
  (`RunWatch`, `locate`, `follow`), `report/run_report.py`, `testing.py` (offline doubles).
  Factories are injected; `omni_factories(case)` = the real ones. Which path proves delivery is
  `Case.deliverable`/`find_deliverable`; `run_case` turns it into an `artifact_probe` callable
  for `run_agent_session` — the driver never knows the deliverable.
- `src/flowbench/report/compare.py` — side-by-side flow comparison; a scoreless flow (missing
  scorecard, or one whose `score` raised) renders as a FAILED column, never an abort.
- `src/flowbench/cli.py` — typer: `run`, `watch`, `compare`.
- `scenarios/<scenario>/cases/<case>/` — a case folder: plain-text `task.md`/`simulator.md`/
  `knowledge.md`/`flows.yaml` (+ optional `judge.md`), plus an optional `case.py` and whatever
  scoring it needs.
  Reference: `scenarios/swe_e2e/cases/todo_app/` — the agent builds a Python CLI todo app
  from a vague first prompt; a no-leak simulated user reveals the shape only when asked; each flow
  is scored on its own (no comparative judge) by `case.py`'s `TodoAppCase.score` — objective
  black-box acceptance (`acceptance.py`) + clarifying_coverage + a low-confidence judge
  (`scorers.py`) — into `<flow>/scorecard.json`. `flows.yaml` declares the flows it benchmarks
  (baseline vs superpowers); `skills/` vendors the superpowers skill dirs the superpowers flow
  bundles (see `skills/VERSION.md`).
- `scenarios/smoke/hello/` — the engine's own live gate: one flow, one file, one simulator relay,
  a tight budget. The second scenario beside `swe_e2e`.

## Scope (locked decisions — don't drift)

- **A flow is the full configuration; nothing hidden.** Harness, model, reasoning effort, bundle,
  optional system prompt, prompt overlay, budgets — every field is declared in the flow and
  recorded in the run manifest. Reports state which fields differ between columns; a case decides
  which fields are eligible (`swe_e2e`'s todo_app rejects system prompts because its question
  is whether the flow's workflow FIRES on a plain user invite — ground truth = real `Skill` tool
  calls, not narration). Today the engine `Flow` carries bundle fields only and the driver never
  passes a system prompt; S03.1 widens it. Decision record:
  `docs/design/decisions/2026-09-03-flow-is-the-full-configuration.md`.
- **Baseline is not a privileged control** — it's just a flow whose bundle is empty
  (`skills="none"`).
- **Domain-specific flows and cases** (proprietary ones) live in a separate repo that depends on
  this one; this repo carries only the engine and the open reference scenario.

## Conventions / gotchas

- **Issues carry their hierarchy.** Every issue has a `type:epic|story|task|bug` label (issue
  types are org-only, so labels stand in on this personal repo). One `type:epic` issue per
  `docs/roadmap/epics/E*`; stories are its sub-issues (`gh issue create --parent <epic>`), bugs
  and tasks hang under the story or epic they belong to. Work state lives on the Project board
  https://github.com/users/kzarzycki/projects/1 (both repos; `Status` + loop `Phase`), written
  by the engineering loop's `board.sh` — not in issue comments or local notes.
- Live runs need a running omnigent server and `uv run --extra live`; setup is
  `docs/onboarding.md`.
- Wheel ships `src/flowbench` only; in-repo `scenarios` imports work via pytest `pythonpath`
  and cwd.
- Run-dirs (`$RUNS`) live outside the repo, beside the checkout that launches the run;
  the path is per-developer, recorded in `CLAUDE.local.md` (untracked).
- The comparison reader is pure `(<run_base>, <run_id>) -> markdown`; a missing/malformed scorecard
  is a FAILED column and the benchmark never aborts on one bad flow.

## Tooling

Python 3.12+, `uv`, `pytest`, `ruff`. Single branch.
