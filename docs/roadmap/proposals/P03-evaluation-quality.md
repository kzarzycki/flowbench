# P03 — Evaluation quality (proposal, cross-cutting)

Not yet an epic spec. Promote to `epics/E08-evaluation-quality.md` (with stories and
verification) before starting Phase 2+. Phase 1 is already more than one ≤300-line story —
it splits into an engine/scorer story and a paired scenarios story (see "Phase 1 stories"),
executable off this proposal without promoting the epic first.

Unlike P01/P02 this is not one milestone — it is a scoring-*content* thread whose stories
attach to already-scheduled infrastructure: M1 (the engine judge), M3 (scorecard/compare
schema), M7 (said-vs-did), M8 (statistics). It supplies the one thing the rest of the
roadmap deliberately leaves scenario-side: **what quality to measure, and how.**

## Problem

The roadmap builds the runtime *around* scoring — portability, reproducibility, sandboxing,
auditing, statistics — but has no design for the judgement itself. Today a single comparative
LLM-judge reads all flows' transcripts + plans and emits a prose verdict (`swe_planning`
`feature_flag_service/judge.md`) or a bare per-dimension 0–5 with no anchors
(`todo_app/judge.md`). Consequences:

- **No anchors → low reproducibility.** A 0–5 with no descriptive levels drifts between
  judge runs and can't be calibrated against a human.
- **One source only.** Everything routes through the LLM-judge; there are zero cheap,
  deterministic metrics to run every trial or to cross-check the judge.
- **Aggregation hides weakness.** A single winner (or a mean) masks *where* a flow is weak.
- **No calibration path.** Nothing measures whether the judge agrees with a human, or with
  itself across runs.

A colleague proposed a grading framework for exactly this (deck: *ewaluacja-silnika*) and
prototyped it as a standalone Claude skill (`requirements-eval.skill`): five quality
dimensions, fifteen sub-metrics, each tagged **numeric (script-computed)** or **descriptive
(LLM-judged on anchored 1–5)**, three measurement sources, and honesty rules. It is a strong
starting point but assumes a *static* `input documents → generated requirements/architecture`
pipeline. flowbench's input is an **interactive simulated dialogue** and its artifact is a
**plan**, not a formal requirements+architecture deliverable. This proposal adapts the
framework to that reality and lands it as reusable engine machinery.

## Proposal

### The grading skill (generic) + harness-side scorers + scenario rubric data

Three parts with a clean tool boundary:

- A generic **grading skill** owns the *discipline the judge reads*: the five dimensions, the
  shared 1–5 anchor scale, the groundedness/claim-classification procedure, and the
  `judged.json` output contract. It carries no domain content and **runs no code** — it is
  rubric text the judge session reads, replacing today's bespoke `judge.md` prose. The judge
  session stays tool-less (no shell/file access), which keeps it compatible with the
  judge/simulator confinement M6 S06.5 restricts to first.
- The **numeric scorers** are deterministic scripts that run **harness-side** — in the
  runner's scorer layer, alongside flowbench's existing pure `(manifest, output) → scorecard`
  scorers, never inside the judge session. Their outputs are injected into the judge prompt as
  text (so the judge sees the cheap signals) and written to the scorecard. Adapted from the
  prototype's `compute_metrics.py`, minus its static-doc extraction path (the input is the
  already-captured transcript + `plan.md`).
- Each case supplies a **`grading.yaml`**: which dimensions/sub-metrics apply, their weights,
  the expected plan sections, any declared design principles, and domain notes.

This honors the locked decision (scoring *content* stays scenario-side) while making the
*method* reusable across `swe_planning`, the migration scenario, and future ADF/ACE/OpenSpec
flows.

**Placement & sequencing.** The judge lives scenario-side today (`swe_planning/run.py`); the
engine has no `judge.py` yet. So Phase 1 lands the grading skill + harness scorers in the
**scenarios repo**, where the judge runs now. The generic *engine-side* home is the target
realized when M1 S01.1/S01.2 lift the runtime (judge, `SessionModel`, transcript) into the
engine and swe_planning consumes it — at which point the skill + scorer layer move with the
judge. Phase 1 therefore executes with or after S01.1, or ships scenario-local and is lifted
by S01.2; it must not assume an engine judge that does not exist.

### Five dimensions, adapted (dialogue → plan)

Input = `task.md` + what the simulator revealed from `knowledge.md`. Artifact = `plan.md` +
the transcript (discovery behaviour is invisible in the plan alone — the judge reads both,
as it does today).

1. **Completeness** — coverage of the task and the facts the simulator revealed; structural
   completeness (expected plan sections present); weighted gap detection (expected-but-absent
   elements, tagged criticality). *Absorbs `swe_planning`'s "surfaces corner cases".*
2. **Correctness & faithfulness** — groundedness (plan claims supported by task+dialogue, not
   hallucinated or contradicting `knowledge.md` — **the planted-contradiction test lives
   here**); design-principle adherence (only if the case declares principles, else "not
   measured"); domain correctness.
3. **Consistency** — internal (plan does not contradict its own decisions/constraints);
   traceability (requirement↔plan-step; orphan steps flagged); run-to-run stability
   *(scheduled to M8, needs ≥2 trials)*.
4. **Architectural quality** — decision adequacy (choices fit the stated constraints —
   *absorbs "decides where a senior would"*); feasibility + red-flag count; NFR coverage.
5. **Description quality** — clarity/testability (weak-word density proxy + SMART rubric);
   level of detail (right granularity); conciseness/redundancy (near-duplicate fraction).

**Reconciliation with today's dimensions.** The existing sets fold in without loss:

| today | folds into |
|---|---|
| complete (surfaces corner cases) | Completeness (coverage + gap detection) |
| decisive (senior-level choices) | Architectural quality (decision adequacy) |
| inquisitive (asks only genuine product Qs) | Completeness (gap-driven questioning), graded from the transcript — not a `plan.md` metric |
| todo_app: fulfillment | Completeness + Correctness |
| todo_app: discovery | Completeness (gap detection) |
| todo_app: design | Architectural quality |
| todo_app: scope | Description quality (detail) + Architectural quality (feasibility) |
| todo_app: conflict | Correctness (groundedness vs. the planted contradiction) |

### Three measurement sources

1. **Numeric scorers** — deterministic scripts, run **harness-side** every trial (never in
   the judge session): context-coverage proxy, structural-section checklist, traceability
   proxy (orphans), redundancy, weak-word density, detail proxies (count/length/
   concrete-ratio). Embeddings when available, TF-IDF+fuzzy fallback so they always run. Their
   outputs are fed to the judge as text and written to the scorecard.
2. **LLM-judge via the grading skill** — anchored 1–5 for the descriptive sub-metrics, plus
   groundedness claim-classification (atomize → supported/unsupported/contradicting).
3. **Expert calibration** — a human-labelled sample; judge-vs-human and judge-vs-judge
   agreement (Cohen's/Fleiss' κ). New — no calibration concept exists in the roadmap today.

**Honesty rules (carried verbatim from the prototype):** label every metric numeric-vs-judged
so its epistemic status is visible; proxies are estimates, never presented as ground truth;
report the per-dimension breakdown, not just an aggregate; a single comparison is not evidence
(a real verdict needs many cases and a paired significance test).

### Seam into existing infrastructure — do not reinvent

- **`scorecard.json` schema + generic dimensional compare** → M3 S03.4 / S03.5. The skill's
  `judged.json` + `metrics.json` normalize into the engine scorecard; comparison is a
  read-time table over per-flow scorecards (matches "baseline is not privileged — nominate a
  reference at read time").
- **Said-vs-did / claims-vs-evidence** → M7 S07.4. Groundedness generalizes into the
  claims-vs-action-log metric that milestone already scopes.
- **Spread, position-bias, cost** → already scoped by M8 / P01. The
  decomposition-not-aggregation rule is this proposal's; that spread/position-bias reporting
  is P01's.
- **Paired significance tests and run-to-run stability** → *new* stories to attach to M8. P01
  does not scope significance or per-dimension stability today; P03 adds them (Phase 4)
  alongside the calibration work.
- **Human calibration (judge-vs-human/judge-vs-judge κ)** → new stories here (Phase 5), the
  only genuinely unhomed piece in the roadmap.

## Phasing — design all now, schedule the build

- **Phase 1 (near-term, two stories).** Grading skill v1 used *inside the existing
  comparative judge* — keep the single judge session; it emits per-flow dimensional 0–5 with
  anchors, fed by the cheap numeric scorers (weak-word, redundancy, structural checklist,
  coverage, traceability). `swe_planning`'s `judge.md` reads the skill; add `grading.yaml`
  per case. Minimal orchestration change; no new schema. See the stories below.
- **Phase 2.** Absolute per-flow scorecards + derived comparison table (bridge to M3
  scorecard/compare); comparative pass becomes a read over absolute scores.
- **Phase 3.** Groundedness-via-atomic-claims and the traceability matrix as first-class
  metrics (ties M7 said-vs-did).
- **Phase 4.** Run-to-run stability across N trials, paired significance tests, position-bias
  reporting (M8/P01).
- **Phase 5.** Expert-labelled calibration sample; judge-vs-human and judge-vs-judge κ.

## Phase 1 stories (executable off this proposal)

Two stories; the scorer/skill story lands first, the judge-rewrite story consumes it. Both
sit in the scenarios repo (that is where the judge runs today — see "Placement & sequencing").

**Story A — grading skill + harness scorers (scenario-local, no judge change yet).**
- Add the generic grading skill (five dimensions, shared 1–5 anchors, `judged.json` contract),
  adapted from `requirements-eval.skill` — drop the static-doc extraction path; input is the
  captured transcript + `plan.md`.
- Add the harness-side numeric scorer module (coverage proxy, structural-section checklist,
  traceability proxy, redundancy, weak-word density, detail proxies), embeddings-optional with
  a TF-IDF+fuzzy fallback so CI needs no heavy model.
- *Verify (V1, offline):* scorer unit tests on fixtures (known-good / known-bad plans);
  a **contract fixture test** — a hand-written `judged.json` with a contradicting claim renders
  a low Correctness score and lists the finding (this tests the *contract*, not an LLM
  judgement); the TF-IDF fallback path exercised with no embeddings installed.

**Story B — judge reads the skill; per-case `grading.yaml`; reporting (paired, merges after A).**
- `feature_flag_service/grading.yaml` and `todo_app/grading.yaml` (applicable dims, weights,
  expected plan sections, domain notes; `todo_app`'s five dims map into the taxonomy per the
  reconciliation table). Both cases are in Phase 1 scope.
- `judge.md` rewritten to read the skill and emit anchored per-flow `SCORES` lines for all five
  dimensions, keeping the `WINNER:` tail. The rewrite must instruct the judge to grade from the
  **transcript** as well as the plan (today `feature_flag_service/judge.md` says "Read both
  plans" only) — the Completeness "gap-driven questioning" sub-metric is invisible in the plan
  alone.
- Reporting: the existing score-means table renders the five dimensions; harness-scorer outputs
  appear alongside, labelled numeric-vs-judged.
- *Verify:* V1 offline (parser accepts the five anchored `SCORES` dimensions; `grading.yaml`
  loads/validates). V4 — a live `swe_planning` `feature_flag_service` run whose `run.json`
  carries five anchored dimensions per flow plus the numeric-scorer block. The
  planted-contradiction assertion belongs to a live **`todo_app`** run (only `todo_app` plants
  a contradiction — `feature_flag_service` has none): that run's Correctness dimension scores
  the contradiction-catching flow higher. (`todo_app`'s live validation corresponds to
  `verification.md` V5, currently Inspect-era — treat as best-effort until M1 ports it.)

**Non-goals (Phase 1).** No absolute per-flow scorecard, no schema change, no significance
tests, no expert calibration — all scheduled above.

## Open questions

- Skill packaging: does the judge session receive the grading skill (rubric text it reads) via
  the same bundle mechanism as flow skills, or a dedicated judge-bundle path? (Resolve in the
  E08 spec; Phase 1 vendors it into the judge prompt, which is enough since the judge only
  reads it.)
- Weighting: per-case weights in `grading.yaml` vs. a fixed default (deck suggests
  faithfulness > conciseness). Start unweighted + per-dimension reporting; add weights only
  when a composite is actually needed.
- Numeric-scorer dependency budget: `sentence-transformers` is heavy; confirm the TF-IDF
  fallback is good enough to make embeddings optional in CI.
