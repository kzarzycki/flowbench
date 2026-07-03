# flowbench

A benchmark that compares **agentic flows** on a fixed **case**, all driven through **omnigent**
as the meta-harness. A *flow* is a way of driving a coding agent at a goal — vanilla Claude Code,
superpowers, or any bundle of skills/MCPs. Every flow is vanilla Claude Code under omnigent; flows
differ only by their bundle, never by harness-level steering, so a comparison is apples-to-apples.

Vocabulary → **`docs/GLOSSARY.md`** (Scenario → Case → Flow → Run → Scorecard → Comparison).

## Engineering loop

All changes follow `../xebia/flowbench-scenarios/.claude/loop.md` (interactive
sessions too): branch → spec/plan sized to the change → tests green → PR → merge
(standing approval) → live-run validation via `scenarios.swe_planning.watch` →
journal. Cross-session knowledge: the ledger at
`../xebia/flowbench-scenarios/.claude/engineering-loop/LOG.md` — read it first
when resuming work. Engine PRs here merge BEFORE the paired
scenarios PR; the live run validates both.

## Run it

```bash
uv sync --extra dev --extra spike      # spike = the agent-eval runner (inspect + omnigent)
uv run pytest -q                        # offline suite (live-agent tests skipped)

# compare flows side by side after a run (reads <run_id>/<flow>/scorecard.json):
uv run flowbench compare --run-base ../flowbench-runs/todo-app-eval --run-id <run_id>

# drive the reference case live (needs omnigent patched + ANTHROPIC_API_KEY unset):
RUN_LIVE_AGENT=1 TODO_RUN_ID=first uv run inspect eval \
  scenarios/coding_workflow/cases/todo_app/eval.py --model claudesub/sonnet \
  --model-role user=claudesub/sonnet --model-role grader=claudesub/sonnet
```

## Layout

- `src/flowbench/runner/` — the agent-eval runtime: `driver.py` (`OmnigentDriver`, per-flow bundle
  skills/MCP, subscription guard), `flow.py` (`Flow` = one approach as omnigent-bundle data),
  `loop.py` (`run_agent_session` DONE-token loop), `judge.py`, `run_dir.py`,
  `subscription_model.py` (the `claudesub` Inspect provider).
  Touching `src/flowbench/runner/`? Read `docs/design/runner.md` first (driver/loop
  contracts, one-execution-model decision).
- `src/flowbench/report/compare.py` — side-by-side flow comparison; a scoreless flow renders as a
  FAILED column, never an abort.
- `src/flowbench/cli.py` — typer: `compare`.
- `scenarios/<scenario>/cases/<case>/` — a case is `prompt` + fixtures + acceptance + `flows.py`.
  Reference: `scenarios/coding_workflow/cases/todo_app/` — the agent builds a Python CLI todo app
  from a vague first prompt; a no-leak simulated user reveals the shape only when asked; objective
  black-box acceptance + clarifying_coverage + a low-confidence judge. `flows.py` declares the flows
  it benchmarks (baseline vs superpowers); `eval.py` runs one Sample per flow.
- `scenarios/<scenario>/scenario.py` — the scenario's rules (scorers/acceptance/eligible flows).

## Scope (locked decisions — don't drift)

- **Every flow is VANILLA Claude Code under omnigent — no harness-level steering; flows differ only
  by bundle.** For the claude-native harness omnigent never passes the bundle `prompt:` to the
  `claude` CLI (no `--system-prompt`, no initial-prompt injection). The ONLY per-flow variation is
  the bundle's skills/MCPs + the host-skill filter (`skills:`), never a prompt — so results stay
  comparable. "Steering" means that harness layer, NOT the case: the first user message is the
  user's own request and MAY ask the agent to brainstorm/interview first — legitimate user input,
  the way this user opens a build. What we measure is whether a flow's workflow FIRES on that invite
  and how well it covers the underspecified points (ground truth = the flow's real `Skill` tool
  calls, not its narration).
- **Baseline is not a privileged control** — it's just a flow whose bundle is empty
  (`skills="none"`). A comparison may nominate one flow as the reference to read others against, but
  that's a read-time label, not a type.
- **Domain-specific flows and cases** (proprietary ones) live in a separate repo that depends on
  this one; this repo carries only the engine and the open reference scenario.

## Conventions / gotchas

- The agent-eval runner requires `ANTHROPIC_API_KEY` UNSET (subscription billing — the driver
  guards on it) and omnigent patched.
- `pyproject` registers the `claudesub` Inspect provider via `[project.entry-points.inspect_ai]`
  and ships `src/flowbench` + `scenarios` in the wheel, so `--model claudesub/sonnet` resolves.
- Run-dirs live under a sibling `../flowbench-runs/`, never inside the repo.
- The comparison reader is pure `(<run_base>, <run_id>) -> markdown`; a missing/malformed scorecard
  is a FAILED column and the benchmark never aborts on one bad flow.

## Tooling

Python 3.12+, `uv`, `pytest`, `ruff`. Single branch.
