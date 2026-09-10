Reject unless: (a) full traceability — build the criterion→task→test mapping yourself; any
criterion without a task or without a test is an automatic reject; (b) tasks are ordered so
the branch builds and tests green after each one; (c) exact file paths and interfaces are
specified per task (this plan will be executed by context-free subagents — vague tasks
fail); (d) the test strategy would catch the bug / verify the feature, not just exercise the
happy path. APPROVE or REVISE with numbered objections.

Inputs (read only these plus the repos):
- Approved spec: /Users/zarz/dev/xebia/flowbench-scenarios--s024/.claude/engineering-loop/items/flowbench-104/spec.md
- Plan: /Users/zarz/dev/xebia/flowbench-scenarios--s024/.claude/engineering-loop/items/flowbench-104/plan.md
- Engine repo (read access, branch at origin/master, no code changes yet): /Users/zarz/dev/agents/flowbench--s024
- Scenarios repo (read access): /Users/zarz/dev/xebia/flowbench-scenarios--s024

Output: the verdict line (APPROVE or REVISE) first, then numbered objections if any. Nothing else.
