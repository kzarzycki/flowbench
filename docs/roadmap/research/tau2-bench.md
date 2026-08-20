# τ²-bench research — what transfers to flowbench

What Sierra's τ²-bench does and which of its ideas flowbench should adopt, from reading its
source (`github.com/sierra-research/tau2-bench`, evaluator/metrics/task-schema code) and the
papers (τ: arXiv:2406.12045, τ²: arXiv:2506.07982), 2026-07-07. It benchmarks *LLMs* on
conversational tool-use under a fixed harness; flowbench benchmarks *flows* on coding work
under fixed models — different subject, near-identical mechanics (simulated user, multi-turn
sessions, outcome grading). This feeds P01 (statistics), P03 (evaluation quality), and the
M3 case-format spec, the way `flow-requirements.md` feeds E04/E06.

## What τ²-bench is

An LLM agent does multi-turn customer-service work in a domain (airline/retail/telecom):
talk to a simulated user, call domain tools against a database, obey a written `policy.md`,
reach the correct end state. A task = a user scenario (persona + `known_info`/`unknown_info`
+ instructions), initial DB state, and `evaluation_criteria` (the oracle). Telecom adds
**dual-control**: the user holds phone-side tools the agent can't touch
(`toggle_airplane_mode`, `run_speed_test`), so the agent must diagnose by instructing the
user; user tool-call turns are hidden from the agent. Grading is deterministic: replay the
task's reference actions on a fresh environment to derive a gold DB state, compare DB
hashes — any trajectory reaching an equivalent state passes. Reward = product of components
declared in `reward_basis` (default `[DB, COMMUNICATE]`); the LLM-judge path (NL assertions)
is explicitly diagnostic-only, kept out of official scores. Headline metric **pass^k** =
`comb(successes, k) / comb(trials, k)` per task, averaged — the probability that *all k* of
a random k-subset of trials succeed; reliability, decreasing in k (not pass@k).

## Adopt (scheduled)

1. **pass^k reliability metric.** flowbench today runs one trial per (case, flow) and P01
   only scopes spread/position-bias; nothing measures whether a flow succeeds *every* time.
   pass^k is cheap (a formula over per-trial outcomes), unbiased, and exposes flakiness a
   mean hides — τ² found models losing most of their pass^1 by k=4. Prerequisite: a binary
   per-trial success gate per case (see next item); for the migration scenario the golden
   diff already is one. → P01 (M8).
2. **Outcome gate × quality layers.** τ² gates pass/fail on deterministic checks and keeps
   the LLM-judge out of the official number. flowbench can't fully escape the judge (a plan
   has no DB state to hash) but should adopt the layering: each case declares a
   `success_basis` of deterministic components (artifact exists, structural checklist,
   scenario assertions — migration: golden diff) whose product is the binary trial outcome
   feeding pass^k; judged dimensional scores grade quality *above* that gate and never leak
   into it. This hardens P03's numeric-vs-judged split into a scoring architecture and slots
   into the M3 `scorecard.json` schema as a component verdict list. → P03 + M3 S03.4.
3. **Structured simulator scenario + oracle separation.** τ²'s user simulator receives
   *only* the scenario object — persona, `known_info`, `unknown_info`, instructions — never
   the `evaluation_criteria`; its guidelines enforce progressive disclosure ("wait for the
   agent to ask"), no hallucinated facts ("information not provided … is unknown"), and no
   verbatim recitation. swe_planning's `simulator.md` + `knowledge.md` have the spirit but
   no contract: nothing structurally prevents a case author from leaking judge criteria into
   simulator context, and known-vs-unknown is implicit prose. Case format v1 should make the
   scenario a structured object (persona / known / unknown / disclosure policy) and state
   the invariant *the simulator never sees the oracle* (`judge.md`, `grading.yaml`,
   golden outputs). → M3 S03.2.
4. **Solo mode (discovery ablation).** τ² reruns each task from a self-contained `ticket`
   with no user; the dual-vs-solo gap isolates coordination from reasoning (GPT-4.1 lost
   ~18 pts pass^1, o4-mini ~25). flowbench analog: run a case with `knowledge.md` folded
   into the kickoff and no simulator — the score gap between solo and simulated runs
   isolates *requirement discovery* (inquisitive) from *planning ability*
   (complete/decisive), per-flow. Cheap: a case-level mode, no new machinery. → P03
   (Phase 2+ story), engine support in the M3 case format (a case declares it supports solo).
5. **Simulator quality as a measured number.** τ² reports its simulator's own error rate
   (16%, vs 40–47% for naive prompts) — the simulator is part of the instrument and gets
   calibrated like one. flowbench treats simulator fidelity as vibes. Adopt: an audit pass
   over sampled transcripts (did the sim leak unprompted? contradict `knowledge.md`?
   hallucinate facts?) producing a sim-error rate per run. → P01 (M8), alongside judge
   calibration in P03 Phase 5.

## Adopt (small, fold into existing stories)

- **Trial isolation by reconstruction**: each τ² trial rebuilds the environment from
  declared initial state rather than resetting — flowbench's fresh-workspace-per-session
  already matches; keep it stated as an invariant in P01's parallel-trials story.
- **Seeded runs + checkpoint/resume**: `run_tasks(seed=…)` and a checkpoint runner that
  resumes a partially-failed sweep. P01's failure-isolated trials should include resume
  ("re-run only failed/missing trials into the same run dir") — cheaper than re-running a
  sweep after one crash. → P01.
- **Termination-reason taxonomy**: every τ² trial records *why* it ended (agent stop, user
  stop, max steps, error); reward is zeroed on abnormal termination. flowbench's
  `PLAN_COMPLETE`/failed-session handling is close; make the reason a first-class scorecard
  field so aggregate tables can split quality-failures from infrastructure-failures. → M3
  S03.4 (schema) + P01 (aggregation).

## Considered and parked (with reasons)

- **Dual-control.** Powerful for diagnose-through-the-user domains; inapplicable while our
  simulated user holds no tools and shares no mutable state with the agent. Revisit only if
  a scenario appears where the "user" must execute actions the flow cannot (e.g. operating
  a console the agent can't reach). Not scheduled.
- **Compositional task generation** (atomic `f^init`/`f^sol`/`f^assert` units, Cartesian
  product, keep only deterministically-verified combinations; 15 subtask groups → 2,285
  telecom tasks). Needs a deterministic per-task verifier, which plans don't have; the
  migration scenario's tier variants (`tier-smoke`/`tier-core`) are the manual version.
  Revisit when a scenario has a machine-checkable oracle and needs task volume. Not
  scheduled.
- **Leaderboard submission verification** (scripted re-validation of submitted runs).
  M9 territory; note for P02 when a public comparison surface actually exists.
