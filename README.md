# flowbench

> [!WARNING]
> **🚧 WORK IN PROGRESS — DO NOT USE YET. 🚧**
> This project is early and unstable: APIs, vocabulary, and results will change without notice, and nothing here is validated for real use. Not ready for adoption, dependency, or citation. Watch/star if you're curious, but don't build on it.

A benchmark that compares agentic **flows** — different ways of driving a coding agent at a goal
(vanilla, superpowers, or any bundle of skills/MCPs) — on a fixed **case**, all driven through
[omnigent](https://github.com/omnigent-ai/omnigent) as the meta-harness. Every field of a flow is declared and recorded, so a comparison states
exactly which knobs differ: same task, same meta-harness, nothing steering from hiding.

Vocabulary in [`docs/GLOSSARY.md`](docs/GLOSSARY.md):
**Scenario → Case → Flow → Run → Scorecard → Comparison.**

## How it works

- A **case** poses one fixed task (a vague first prompt + fixtures + acceptance criteria).
- Each **flow** runs that case under omnigent and produces a **run** → a **scorecard**.
- Scorecards line up in a **comparison** — does a given workflow actually beat a bare agent?

## Quickstart

```bash
uv sync --extra dev --extra live       # live = the omnigent runtime for live runs
uv run pytest -q                       # offline suite

# after a run, compare flows side by side ($RUNS = your run-dir root, see docs/onboarding.md §6):
uv run flowbench compare --run-base $RUNS/coding_workflow --run-id <run_id>
```

Driving a case live needs a running [omnigent](https://github.com/omnigent-ai/omnigent) server and
`ANTHROPIC_API_KEY` unset (the runner bills against a Claude subscription, not the API):
**[`docs/onboarding.md`](docs/onboarding.md)** walks the install, the readiness check and that
rule. Why omnigent and not herdr or a CLI of our own:
[`docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md`](docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md).

## Status

Early. Reference scenario: `coding_workflow` — build a Python CLI todo app from a vague first
prompt, benchmarked baseline vs superpowers. Domain-specific scenarios can live in separate repos
that depend on this engine.
