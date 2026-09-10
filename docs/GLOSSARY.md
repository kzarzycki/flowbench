# Glossary

The vocabulary flowbench uses, top to bottom. A benchmark run is: for one **Case**,
execute each **Flow**, score each **Run**, and line the **Scorecards** up in a **Comparison**.

```
Scenario  — the genre: a folder of cases, plus whatever they share
 └─ Case  — a folder: the text files + an optional case.py          [≥1 per scenario]
      ├─ variant  — optional sub-challenge of a case (secondary)
      └─ Flow × Case = Run → Scorecard
                 Flows' scorecards, side by side = Comparison
```

**Scenario** — A genre of work: `dwh_migration`, `swe_e2e`, `change_proposal`. A folder of Cases
plus whatever they share — one `case.py` for a family of them, vendored skill dirs. Nothing to run
on its own; the rules live in the Case. A Scenario is the pluggable unit: `swe_e2e` ships
open-source, `dwh_migration` stays private.

**Case** — What runs: a **folder**. `task.md` (the prompt the agent receives — "I want to migrate
from Teradata to Databricks — help me…"), `simulator.md` + `knowledge.md` (the simulated user),
`flows.yaml`, an optional `judge.md`, plus fixtures/seed — and an optional `case.py` declaring one
`Case` subclass: what proves delivery, the budgets, setup/teardown, how a flow is scored. Text-only
is already runnable; `flowbench run <case_dir>` is the whole address. Format:
[`design/case.md`](design/case.md). A Scenario has one or more Cases.

**variant** *(optional)* — A sub-challenge within a Case, e.g. difficulty tiers `smoke`/`core`.
Secondary: variants don't drive design, and most Cases have exactly one (implicit). Variants of one
case are sibling folders sharing their parent's `case.py`.

**Flow** — The thing being compared: `baseline`, `superpowers`, or a private in-house flow. One
complete configuration for driving a coding agent at a Case: the **harness** (which agent:
`claude-native`, `codex`, pi/omp next), the **model**, the **reasoning effort**, the **bundle** of
skills/MCPs/agent configs, and optionally a system prompt, a prompt overlay and budgets. Every
field is declared and recorded; a report states which fields differ between the flows it compares,
and a case may declare some fields ineligible. Change one knob and you have a different flow.
Flows are flat; a `matrix:` in `flows.yaml` expands to many. Every flow is uniform;
there is no built-in "control" category. A bare/vanilla flow is just a flow whose bundle is empty
(`skills="none"`).
Today the engine's `Flow` dataclass carries only the bundle fields; the rest lives in the
scenarios' `flows.yaml` until S03.1 (Flow schema v1). Decision record:
`docs/design/decisions/2026-09-03-flow-is-the-full-configuration.md`.

**subprompt** — A flow's per-Case prompt overlay: the typical user moves for that flow, e.g. the
superpowers flow's "use the brainstorming skill first". The base prompt comes from the Case;
subprompts are the flow's addition.

**Harness** — The coding-agent runtime a flow drives: `claude-native`, `codex`. **omnigent** is the
meta-harness that runs every flow uniformly, so flows differ only by their declared fields, never
by how they are launched.

**Run** — One Flow executed on one Case (one variant) → a workspace of artifacts + one Scorecard.

**Scorer / Scorecard** — Scorers grade a Run against the Case's acceptance criteria; the graded
result is a Scorecard, one per Run.

**Comparison** — The Scorecards of all Flows on a Case, side by side (`flowbench compare`).

## Retired terms

- **arm** → **flow**. "Arm" is clinical-trial / multi-armed-bandit jargon, off-domain for an eval tool.
- **SUT** → **flow**. Every flow is just a flow; none is privileged as "the system under test."
- **task** (as a synonym for Case) → **case**. "Task" stays reserved for Inspect's `Task` object.

## Naming

A scenario is `<domain>_<phase|scope>`: `swe_e2e` (software engineering, end to end),
`swe_planning`, `dwh_migration`. A case is named for what it poses (`todo_app`,
`teradata_databricks`); a case whose job is a cheap gate rather than a comparison is `smoke_*` —
or lives under the `smoke` scenario, as the engine's own `smoke/hello` does.

## Folder shape

```
scenarios/
  smoke/hello/               # the engine's own live gate: one flow, one file, one relay
    task.md  simulator.md  knowledge.md  flows.yaml
    case.py                  # HelloCase: deliverable = hello.txt, tight budget, score()
  swe_e2e/                   # open-source reference scenario
    cases/todo_app/
      task.md  simulator.md  knowledge.md  flows.yaml  # baseline + superpowers
      acceptance.md  fixtures/
      case.py                # TodoAppCase: no file deliverable, black-box acceptance + score()
    skills/                  # the skill dirs the superpowers flow bundles
  <private_scenario>/        # private — separate repo, depends on flowbench
    case.py                  # one runtime shape shared by every case below
    cases/<case>/
      task.md  simulator.md  knowledge.md  flows.yaml  judge.md
      seed/  manifest.yaml
```
