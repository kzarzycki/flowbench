# Gate 1 spec review — attempt 1 (Fable, fresh context)

VERDICT: APPROVE

- Scope: exactly the issue's three needs + loop-mandated guard tests; nothing extra.
- Checkability: AC1-AC3 greppable; AC4 baseline verified live (105 passed, 1 skipped);
  "fail on pre-change files" makes new tests falsifiable.
- Codebase claims all verified: helpers.py:38 _SCORE_KV regex matches D4 quote;
  aggregate_scores + report.py iterate criteria dynamically; MUST quote verbatim at
  knowledge.md:21-22; judge tail exactly SCORES A/SCORES B/WINNER/A:/B:. Existing
  test pins actually target feature_flag_service, not todo_app — safety conclusion
  holds a fortiori.
- decisions.md D1-D7 all grounded in issue + ledger + code; D3 is engineering
  repeatability, not product judgment.

Non-blocking notes carried to the plan:
1. D1 "only active case" imprecise — scenario.CASES still lists feature_flag_service
   (stale; out of scope for #14).
2. Phrase the volunteer rule explicitly as an EXCEPTION to simulator.md's
   "answer ONLY what is asked" base rule, so the base rule doesn't suppress it.
