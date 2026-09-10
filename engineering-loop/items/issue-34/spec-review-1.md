# Gate 1 spec review — attempt 1 (Fable, fresh context)

VERDICT: APPROVE

- All codebase claims verified (run.py:73 len!=2 check; swap/canonical gymnastics;
  driver reasoning_effort first-class; _SCORES [AB]; baseline 116/1).
- Plain flow matches pre-#33 exactly. watch.py reads only winner_flow/plans_missing
  (both preserved) — A/B-key consumer claim holds.
- Rotation (k-1)%N ≡ today's swap for N=2; N=3/n=3 covers every position once.
- Name-keyed aggregation loses nothing either report needs; ties defined.

Nits carried to the plan:
1. codex flow keeps its `skills: [name list]` field (harness-specific filter).
2. parse_scores: decide absent-label behavior (missing keys vs empty dicts) and
   pin it in a test.
3. Single-letter labels cap N at 26 — accepted, no machinery.
