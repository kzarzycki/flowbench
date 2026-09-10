# Gate 2 — plan review (Claude opus, fresh context)

Attempt 1: REVISE — (1) T6 put test-local three-flow helpers into shipped testing.py; (2) T1 re-export import would trip ruff F401; (3) AC9/AC10 had no T8 check. All fixed in plan.md.

Attempt 2: REVISE — one new objection: T5 ported `test_render_any_dispatches_on_shape`, which needs T6's run_case/fixture. Moved to T6; independence claim corrected.

Attempt 3: APPROVE. Ordering verified; cross-file test helper import verified under pyproject pythonpath.
