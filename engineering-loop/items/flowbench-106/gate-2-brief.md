You are reviewing an implementation plan for an unattended pipeline; context-free subagents
will execute it task by task. Reject unless: (a) full traceability — build the
criterion→task→test mapping yourself from the spec's acceptance criteria; any criterion
without a task or without a test is an automatic reject; (b) tasks are ordered so the branch
builds and tests green after each one; (c) exact file paths and interfaces are specified per
task; (d) the test strategy would catch the bug / verify the feature, not just exercise the
happy path. The item is size S — reject bloat as well as gaps. Verdict: APPROVE or REVISE
with numbered objections. Start your final message with the single word APPROVE or REVISE.

Inputs (read them yourself; your shell cwd is the engine worktree):
- Approved spec: /Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/spec.md
- Plan: /Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md
- Engine code (cwd): src/flowbench/driver/omnigent.py, src/flowbench/transcript.py,
  src/flowbench/watch.py, scenarios/coding_workflow/cases/todo_app/scorers.py, pyproject.toml,
  and the tests under tests/driver/test_omnigent.py, tests/test_transcript.py,
  tests/test_watch.py, tests/scenarios/todo_app/test_scorers.py.
