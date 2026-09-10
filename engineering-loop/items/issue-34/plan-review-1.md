# Gate 2 plan review — attempt 1 (opus, fresh context)

VERDICT: REVISE

- AC mapping complete; gate-1 nits honored; test strategy adequate; label/name
  layering and judge tail pinned precisely.
- Objection 1 (upheld): Task 1's aggregate_verdicts/parse_scores semantic
  changes leave test_swe_planning_run.py red at the task boundary (zero-filled
  a/b counts, pre-seeded scores dict pins) — file scope didn't include run.py
  call sites or that test file.
- Fix adopted: option (b) — merge Tasks 1+2 into a single shape-switch task.
