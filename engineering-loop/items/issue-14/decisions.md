# issue-14 decisions (rule-3 self-answered questions)

- D1 **Which case gets the contradiction?** `todo_app` — the only active case
  (`scenarios/swe_planning/cases/`); the issue says "a case's knowledge.md".
- D2 **Which contradiction pair?** Reuse the existing firm MUST ("Done tasks stay
  visible as done (mark-and-keep, NOT deleted)", knowledge.md:21-22) as half X, and
  add half Y as an early offhand remark: "when I finish something I want it out of
  my list." Grounded in the issue ("contradict each other or an earlier answer") and
  the ledger's FUTURE note; contradicting an *existing* firm need is the minimal
  change and reads naturally — real users say both of these.
- D3 **Fixed resolution, revealed only when confronted.** When (and only when) the
  agent points out the conflict, the user resolves it: done tasks must be kept
  forever (record/history), but the default list view should hide them; showing them
  on demand is fine. A fixed resolution keeps runs judgeable and repeatable. If the
  agent silently picks a side, the user never volunteers the resolution.
- D4 **Judge criterion + scoring key.** Add criterion 5 "Conflict handling" and
  `conflict=<0-5>` to both SCORES tail lines. No Python change needed:
  `helpers.parse_scores` regex `([a-z_]+)\s*=\s*(\d+)` accepts arbitrary keys, and
  aggregation/report iterate criteria dynamically (verified by reading helpers.py
  and report.py).
- D5 **Delivery mechanics live in simulator.md, facts in knowledge.md** — matching
  the existing split (knowledge = what the user wants, simulator = how they behave).
  Half Y is volunteered unprompted within the user's first few replies; half X
  surfaces when done-task behavior comes up (or as MUST-violation pushback); the
  user never flags the contradiction themselves.
- D6 **If the conflict never surfaces in a conversation** (agent never elicited
  half X), the judge grades that transcript as-is — the criterion text tells the
  judge how to score an unsurfaced contradiction (low: the plan silently follows
  one half). No special-casing in code.
- D7 **Tests:** extend `tests/test_swe_planning_flows.py` with content guards
  (both halves present in knowledge.md, delivery rule in simulator.md,
  `conflict=` in both SCORES lines, WINNER line intact). Existing tests only pin
  file existence + "WINNER:" so the content edits are otherwise unpinned.
