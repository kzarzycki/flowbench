# flowbench

A benchmark that compares agentic **flows** — different ways of driving a coding agent at a goal
(vanilla, superpowers, or any bundle of skills/MCPs) — on a fixed **case**, all driven through
[omnigent](https://github.com/) as the meta-harness. Flows differ only by their bundle, so a
comparison is apples-to-apples: same task, same harness, only the workflow changes.

Vocabulary in [`docs/GLOSSARY.md`](docs/GLOSSARY.md):
**Scenario → Case → Flow → Run → Scorecard → Comparison.**

## How it works

- A **case** poses one fixed task (a vague first prompt + fixtures + acceptance criteria).
- Each **flow** runs that case under omnigent and produces a **run** → a **scorecard**.
- Scorecards line up in a **comparison** — does a given workflow actually beat a bare agent?

## Quickstart

```bash
uv sync --extra dev --extra spike     # spike = the agent-eval runner (inspect + omnigent)
uv run pytest -q                       # offline suite

# after a run, compare flows side by side:
uv run flowbench compare --run-base ../flowbench-runs/todo-app-eval --run-id <run_id>
```

Driving a case live needs [omnigent](https://github.com/) patched in and `ANTHROPIC_API_KEY`
unset (the runner bills against a Claude subscription, not the API). See `CLAUDE.md`.

## Status

Early. Reference scenario: `coding_workflow` — build a Python CLI todo app from a vague first
prompt, benchmarked baseline vs superpowers. Domain-specific scenarios can live in separate repos
that depend on this engine.
