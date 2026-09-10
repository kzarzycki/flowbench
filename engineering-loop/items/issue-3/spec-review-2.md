# Spec review 2 — APPROVE (reviewer: fresh-context opus subagent, scoped re-review)

Both review-1 objections resolved, no new contradictions:
1. AC4 now baseline-relative with the D1 environmental failure exempt.
2. Uniform run_case_n return contract {run_root, trials, aggregate} for
   all n>=1; main() prints trials[0] (n=1, byte-identical stdout verified
   against run.py:123-135,242) or aggregate (n>1); ACs 2/3/5 assert the
   shape offline in both modes. In-memory aggregate vs on-disk run.json
   shapes used coherently.
