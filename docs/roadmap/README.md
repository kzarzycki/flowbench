# flowbench — alpha roadmap docs

This directory is the working plan for taking flowbench from alpha spike to a coherent
benchmark engine, written to be executed **autonomously by Opus-class models** through the
engineering loop. Everything in the repo may change — there are no stable APIs — but the
**locked decisions** below may not drift without a new decision record.

## What flowbench is

flowbench compares **agentic flows** on a fixed **case**. A flow is a way of driving a coding
agent at a goal — vanilla Claude Code, superpowers, a proprietary skills chain — expressed
purely as an omnigent bundle (skills/MCPs + harness). The engine spawns each flow as a real
interactive omnigent session in its own workspace, mediates a multi-turn conversation with a
simulated user, collects the artifacts, scores or judges them, and lines the results up
side by side. Vocabulary: `docs/GLOSSARY.md` (Scenario → Case → Flow → Run → Scorecard →
Comparison).

The differentiated core is the *runtime*: driving real interactive coding-agent sessions,
simulator-mediated loops, workspace artifacts, comparative judging. No eval framework
provides that; frameworks provide the *around* (orchestration at scale, storage, stats).
That is why the recorded decision is DIY with plain-file seams (see locked decisions).

## Reading order

1. `vision.md` — the long-term goal and its pillars (flow portability, reproducibility,
   sandboxing, auditing, statistics).
2. `current-state.md` — what exists today, what is duplicated downstream, and the audited
   code-quality debt list (each item verified against the code).
3. `target-architecture.md` — the module layout and contracts the epics converge on.
4. `ROADMAP.md` — milestones → epics → stories, with sizing and sequencing rules.
5. `epics/` — full specs for the scheduled epics (E00–E04), self-contained enough to
   execute without prior conversation context.
6. `proposals/` — lighter proposals for later milestones (statistics, reporting) and the
   cross-cutting evaluation-quality thread (`P03`); promote one to an epic spec before
   starting it.
7. `research/flow-requirements.md` — what the target flows (ADF chain, OpenSpec, ACE)
   demand from the engine, from reading their sources.
8. `verification.md` — the shared verification procedures (V1–V8) the epic stories cite.

## Locked decisions (restated; do not drift)

These are prior decision records, not this roadmap's inventions:

- **Every flow is vanilla Claude Code under omnigent — no harness-level steering.** Flows
  differ only by bundle (skills/MCPs) and by their per-case prompt overlay (prepend/append
  in the kickoff message, which is legitimate user input). Never a system prompt, never
  per-flow launch flags.
- **One execution model: the `run_case` orchestrator, not Inspect.** Decision record:
  flowbench-scenarios `docs/superpowers/specs/2026-07-02-swe-planning-rework-design.md`.
  Inspect, `subscription_model.py` (`claude -p`), and the eval.py/solver glue are scheduled
  for removal (epic E01).
- **Stay DIY; adopt capabilities, not frameworks.** Reconsider only at the written triggers
  in the same decision record (parallel N≥10 with retries; cross-run statistical
  aggregation; cross-month regression tracking; a second scenario-authoring team).
- **Plain-file seams.** Run folders (`../flowbench-runs/...`) hold `run.json`,
  `scorecard.json`, transcripts. Future tooling reads these files; it never wraps execution.
- **Subscription billing only.** `ANTHROPIC_API_KEY` must be unset; the driver guards on it.
- **Run outputs never live in the repo** — sibling `../flowbench-runs/`.
- **Baseline is not a privileged type** — a comparison may nominate a reference flow at
  read time; there is no built-in control category.

## Operating model for autonomous development

Every change follows the engineering loop
(`../xebia/flowbench-scenarios/.claude/loop.md`): branch → spec sized to the change →
tests green → PR → merge (standing approval) → live-run validation → journal. Rules that
keep weaker-model sessions safe:

- **One story per loop iteration.** Stories in `ROADMAP.md` are sized to a ≤~300-line diff.
  If a story grows past that mid-flight, stop and split it in the ledger.
- **Tests first, contracts explicit.** Each story's "Verify" line cites the shared
  procedures in `verification.md` (V1–V8: suites, live runs, sweeps) plus its own
  assertions. A story without a runnable check is not ready to execute.
- **Engine PRs merge before paired scenarios PRs.** flowbench-scenarios depends on this
  repo as an editable path dep; the live validation run exercises both.
- **Do not touch locked decisions.** If a story seems to require it, the story is wrong —
  escalate in the ledger instead of improvising.
- **The war-story comments in `driver.py`/`loop.py` are load-bearing.** Each encodes a live
  incident (lying idle, undelivered injection, empty grader completion). Refactors must
  carry the constraint, and ideally its regression test, not just the code.
