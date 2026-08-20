# P01 — Statistics & scale (proposal, milestone M8)

Not yet an epic spec. Promote to `epics/` (with stories and verification) before starting.

## Problem

One trial per (case, flow) is noise: agents are stochastic and the judge has position and
day-of-week variance. `run_case_n` already rotates flow order across sequential trials and
tallies categorical winners, but a failing trial aborts the whole run, trials are
sequential (a 3-flow trial is ~30–60 min wall clock), and nothing quantifies spread.

## Proposal

1. **Failure-isolated trials.** A trial whose flow/simulator/judge dies records a
   `trial-XX/run.json` with `"status": "failed"` and the error; aggregation counts it,
   the run continues. Mirrors the existing scorecard rule (FAILED column, never abort).
2. **Parallel trials.** Trials are independent omnigent session groups; run K in parallel
   bounded by a `--parallel` flag. Constraint to check first: subscription rate limits and
   host tmux capacity — measure before defaulting above 2. This brushes the framework
   reconsider-trigger ("parallel N≥10 with retries") — if requirements actually reach
   N≥10, re-read the 2026-07-02 decision record before building more orchestration.
3. **Spread, not just means.** Aggregate `run.json` adds per-criterion min/max/stdev and
   the per-trial winner sequence; the aggregate report renders counts with the sequence so
   a 3–2 split reads differently from 5–0.
4. **Position-bias check.** With rotation already recorded per trial, report winner-by-
   position alongside winner-by-flow; a flow that only wins in slot A is a judge artifact.
5. **Cost accounting.** `context_tokens` is already captured per flow session; add
   simulator+judge tokens, sum per trial, and render a cost row in compare — a win at 2×
   the tokens is a different result.
6. **Regression tracking.** A pure reader over many run dirs
   (`flowbench history --case todo_app`) that lines up aggregate winners/scores by date
   and by skill version (the superpowers version is already in the scorecard via
   `skill_dirs` paths). Plain files in, markdown out; no database.
7. **pass^k reliability** (from τ²-bench — `research/tau2-bench.md`). Per (case, flow),
   over n trials with s successes, report `pass^k = comb(s, k) / comb(n, k)` for k = 1…n:
   the probability that all k of a random k-subset of trials succeed. Decreasing in k;
   pass^1 is the plain success rate. Prerequisite: a binary per-trial success gate — each
   case declares a `success_basis` of deterministic components (see P03 "outcome gate");
   judged quality scores stay out of the gate. Trials that failed on infrastructure
   (termination reason, item 9) are excluded from n, not counted as failures.
8. **Simulator-error rate.** The simulator is part of the instrument; measure it like one
   (τ² reports 16% vs 40–47% for naive prompts). An audit pass over sampled transcripts —
   unprompted leaks, contradictions of `knowledge.md`, hallucinated facts — yielding a
   per-run sim-error rate next to the judge-calibration numbers from P03 Phase 5.
9. **Resume + termination taxonomy.** Failure-isolated trials (item 1) get a resume mode:
   re-run only failed/missing trials into the same run dir instead of restarting the sweep.
   Every trial records *why* it ended (done token, deadline, turn budget, session error) as
   a first-class scorecard field, so aggregation can split quality failures from
   infrastructure failures instead of conflating them in one FAILED bucket.

## Open questions

- Judge variance vs. trial variance: same plans re-judged N times (cheap) vs. full re-runs
  (expensive) — probably both, as separate commands.
- Whether parallel trials share one simulator persona session or stay fully isolated
  (isolation is the safe default; sharing saves nothing material).
