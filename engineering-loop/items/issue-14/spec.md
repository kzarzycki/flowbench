# issue-14: inject contradicting requirements the agent should detect

**Problem.** The todo_app case tests underspecification only. Issue #14 asks for a
second imperfection class: the simulated user states two requirements that
contradict each other; a strong flow notices and resolves the conflict WITH the
user instead of silently picking a side. Three needs, per the issue: a
contradiction pair in the case's knowledge.md, a simulator rule delivering both
halves naturally, and a judge criterion rewarding detection/resolution.

**Change (content-only, `scenarios/swe_planning/cases/todo_app/` + tests).**

1. `knowledge.md` — keep the existing MUST "Done tasks stay visible as done
   (mark-and-keep, NOT deleted)" as half X. Add a "Deliberate tension" section
   defining half Y — an offhand early remark "when I finish something I want it
   out of my list" — and the fixed resolution the user gives ONLY if the agent
   raises the conflict: done tasks are kept forever (they're my record), but the
   default list view hides them; showing them on demand is fine.
2. `simulator.md` — delivery rule: volunteer half Y unprompted within your first
   few replies (it's how you talk about todo lists); state half X when done-task
   handling comes up or as pushback on a MUST violation; NEVER point out the
   contradiction yourself; give the resolution only when the agent explicitly
   surfaces the conflict.
3. `judge.md` — criterion 5 "Conflict handling": the user's statements contain a
   deliberate contradiction about done-task behavior; reward the agent that
   notices it and resolves it with the user; penalize silently picking a side,
   planning both, or never uncovering the second half. SCORES tail lines gain
   ` conflict=<0-5>` for both A and B; `WINNER:` line unchanged.
4. `tests/test_swe_planning_flows.py` — content guards for the above (no runner
   or helper changes: `parse_scores` already accepts arbitrary criteria keys).

**Why safe.** No Python surface changes; scoring/aggregation/report handle the new
key dynamically (verified in helpers.py `parse_scores` and report.py). Existing
tests pin only file existence and the WINNER marker.

## Acceptance criteria (machine-checkable from diff + tests)

- AC1 `knowledge.md` contains both halves: the exact string "out of my list"
  (half Y, marked as volunteered early) and the unchanged mark-and-keep MUST
  (half X), plus a resolution reachable only via agent confrontation.
- AC2 `simulator.md` contains a rule to volunteer half Y within the first few
  replies, a rule never to flag the contradiction unprompted, and a rule to give
  the resolution only when the agent raises the conflict.
- AC3 `judge.md` lists a 5th criterion covering contradiction detection/
  resolution, and both SCORES lines include `conflict=<0-5>`; the final-lines
  block still ends `SCORES A / SCORES B / WINNER / A: / B:`.
- AC4 New tests in `tests/test_swe_planning_flows.py` assert AC1-AC3 content and
  fail on the pre-change files; full offline suite green (baseline 105 passed /
  1 skipped, plus the new tests).
- AC5 Diff touches nothing outside `scenarios/swe_planning/cases/todo_app/` and
  `tests/test_swe_planning_flows.py`.
