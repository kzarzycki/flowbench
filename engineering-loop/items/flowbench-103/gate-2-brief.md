You are reviewing an implementation plan for an unattended pipeline; context-free
subagents will execute it task by task. Reject unless: (a) full traceability — build
the criterion→task→test mapping yourself from spec.md's acceptance criteria; any
criterion without a task or without a test is an automatic reject; (b) tasks are
ordered so the branch builds and tests green after each one; (c) exact file paths and
interfaces are specified per task (vague tasks fail); (d) the test strategy would
catch the bug / verify the feature, not just exercise the happy path. APPROVE or
REVISE with numbered objections.

Inputs (read them yourself; shell access to the cwd = the engine worktree):
- Approved spec: /Users/zarz/dev/xebia/flowbench-scenarios--s023/.claude/engineering-loop/items/flowbench-103/spec.md
- Plan under review: /Users/zarz/dev/xebia/flowbench-scenarios--s023/.claude/engineering-loop/items/flowbench-103/plan.md
- Code: src/flowbench/driver/omnigent.py, src/flowbench/transcript.py,
  src/flowbench/model.py, src/flowbench/loop.py, src/flowbench/types.py,
  tests/driver/test_omnigent.py, tests/test_transcript.py, tests/test_model.py,
  tests/test_loop.py, docs/design/runner.md.

Final message: first line APPROVE or REVISE, then numbered objections with file:line.
