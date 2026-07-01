# Glossary

The vocabulary flowbench uses, top to bottom. A benchmark run is: for one **Case**,
execute each **Flow**, score each **Run**, and line the **Scorecards** up in a **Comparison**.

```
Scenario  — the genre: rules (acceptance + scorers), setting, eligible flows
 └─ Case  — a concrete instance: the prompt + fixtures              [≥1 per scenario]
      ├─ variant  — optional sub-challenge of a case (secondary)
      └─ Flow × Case = Run → Scorecard
                 Flows' scorecards, side by side = Comparison
```

**Scenario** — A genre of work: `dwh_migration`, `coding_workflow`, `change_proposal`.
Defines the rules — what success means (acceptance), how output is scored (scorers) — the
setting, and which flows are eligible. Reusable; nothing to run on its own. A Scenario is the
pluggable unit: `coding_workflow` ships open-source, `dwh_migration` stays private.

**Case** — A concrete instance of a Scenario: `teradata_databricks`, `todo_app`. Carries the
actual prompt the agent receives ("I want to migrate from Teradata to Databricks — help me…")
plus fixtures/seed. This is what runs. A Scenario has one or more Cases.

**variant** *(optional)* — A sub-challenge within a Case, e.g. difficulty tiers `smoke`/`core`.
Secondary: variants don't drive design, and most Cases have exactly one (implicit).

**Flow** — The thing being compared: `baseline`, `superpowers`, or a private in-house flow. A way of driving a
coding agent at a Case, expressed as an omnigent config — a harness plus a bundle of skills/MCPs.
Every flow is uniform; there is no built-in "control" category. A comparison may nominate one flow
as the reference to read the others against (call it the baseline *for that comparison*), but
that's a label chosen at read-time, not a type. A bare/vanilla flow is just a flow whose bundle is
empty (`skills="none"`).

**subprompt** — A flow's per-Case prompt overlay: the typical user moves for that flow, e.g. the
superpowers flow's "use the brainstorming skill first". The base prompt comes from the Case;
subprompts are the flow's addition.

**Harness** — The coding-agent runtime a flow drives: `claude-native`, `codex`. **omnigent** is the
meta-harness that runs every flow uniformly, so flows differ only by their bundle, never by how
they are launched.

**Run** — One Flow executed on one Case (one variant) → a workspace of artifacts + one Scorecard.

**Scorer / Scorecard** — Scorers grade a Run against the Case's acceptance criteria; the graded
result is a Scorecard, one per Run.

**Comparison** — The Scorecards of all Flows on a Case, side by side (`flowbench compare`).

## Retired terms

- **arm** → **flow**. "Arm" is clinical-trial / multi-armed-bandit jargon, off-domain for an eval tool.
- **SUT** → **flow**. Every flow is just a flow; none is privileged as "the system under test."
- **task** (as a synonym for Case) → **case**. "Task" stays reserved for Inspect's `Task` object.

## Folder shape

```
scenarios/
  coding_workflow/           # open-source
    scenario.py              # rules: scorers, acceptance, eligible flows
    cases/todo_app/
      prompt.md  fixtures/  acceptance.md  flows.py    # baseline + superpowers
  <private_scenario>/        # private — lives in a separate repo, depends on flowbench
    scenario.py              # scenario-specific scorers + infra
    cases/<case>/
      prompt.md  fixtures/  flows.py                   # baseline + private flows (+ subprompts)
```
