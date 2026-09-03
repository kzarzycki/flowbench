# Decision: a flow is the full configuration; comparability is declared, not typed

**Date:** 2026-09-03. **Status:** accepted. Supersedes the "flows differ only by bundle" wording
in CLAUDE.md / roadmap README (the intent behind it is kept, see "What stays locked").

## Decision

1. **A flow is one complete configuration** of what the meta-harness launches: harness (which
   coding agent), model, reasoning effort, bundle (skills / MCPs / agent configs), optional system
   prompt, per-case prompt overlay (prepend/append), budgets. Change one knob and you have a
   different flow. Anything omnigent or herdr can start is a valid flow.
2. **Every field is declared in the flow and recorded in the run manifest.** Nothing hidden. The
   engine's job is to make the launch identical *given the declaration*, not to forbid fields.
3. **Comparability is a read-time fact the report states.** A comparison lists which flow fields
   differ between its columns ("differ in: bundle" / "differ in: bundle, model"). One knob at a
   time is the recommended design, not a type constraint.
4. **Scenarios police eligibility.** A scenario's rules may exclude flows (e.g. `coding_workflow`
   rejects flows with a system prompt, because its question is "does the flow's workflow *fire* on
   a plain user invite" and a system prompt makes that trivially true). `swe_planning` may allow
   them. The engine does not hard-code either.
5. **Flows are flat.** No flow × config two-level type. A `matrix:` block in `flows.yaml` expands
   to flat flows (`superpowers-{model}-{effort}`); reports group by any field.
6. **Harness is a flow field.** Claude Code today; Codex and pi/omp next. The meta-harness
   (omnigent today, herdr under consideration) is a separate decision to be recorded in M2.

## Why

The original lock existed for one measurement (todo_app's "did the skills fire"). It got
over-stated as a type rule and blocked things we already do downstream: the scenarios'
`flows.yaml` carries `model`, `reasoning_effort`, `prepend`, `append`, `turn_timeout_s` as raw
dicts. Model and effort are launch parameters, not steering, and comparing them is a stated goal.

## What stays locked

- No *hidden* steering: whatever shapes the agent is in the flow declaration and the manifest.
- Baseline is not a type; it is a flow with an empty bundle.
- Prepend/append are user-message text, on the user side of the line.

## Consequences

- S03.1 (Flow schema v1) implements the flat schema + matrix expansion + validating loader.
- S03.5 (generic compare) renders the "differs in" row.
- Scenario eligibility rules become a scenario.py contract (S03.2).
- Priority: solidify the run framework (M0–M3: one runner, generic runtime in the engine,
  reliable runs, declarative flows) before adding flows or scenarios.
