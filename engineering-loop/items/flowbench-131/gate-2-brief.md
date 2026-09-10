Reject unless: (a) full traceability — build the criterion→task→test mapping yourself; any
criterion without a task or without a test is an automatic reject; (b) tasks are ordered so
the branch builds and tests green after each one; (c) exact file paths and interfaces are
specified per task (this plan will be executed by context-free subagents — vague tasks
fail); (d) the test strategy would catch the bug / verify the feature, not just exercise the
happy path. APPROVE or REVISE with numbered objections.

Inputs (read these yourself; nothing else is in scope):
- Approved spec: /Users/zarz/dev/xebia/flowbench-scenarios--i131/.claude/engineering-loop/items/flowbench-131/spec.md
- Plan: /Users/zarz/dev/xebia/flowbench-scenarios--i131/.claude/engineering-loop/items/flowbench-131/plan.md
- Engine worktree (read-only): /Users/zarz/dev/agents/flowbench--i131 (src/flowbench/, tests/, docs/design/runner.md, docs/onboarding.md)
Do not modify any file. Reply with the verdict only, in the format above.
