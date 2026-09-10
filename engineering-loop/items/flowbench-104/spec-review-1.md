reviewer: claude-code subagent gate1-review-104 (Fable, fresh context; same vendor as implementer — brief directs Claude reviewers)

REVISE

1. AC4 not satisfiable as specified: post-capture probe unbounded adds 1 s after the 0.1 s poll cut. → AC4 restated (probe blocks on first call only).
2. §5 misattributes `make_grader_omni` (lives in `scenarios/coding_workflow/cases/todo_app/scoring.py`). → fixed.
3. §7 misses `docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md:13` (ABC list). → added.
All other codebase claims and decisions #1–#8 verified.
