Gate 3: adversarial whole-branch review. Read-only; do not edit files.

Repo (worktree, cwd): /Users/zarz/dev/agents/flowbench--items — branch loop/items-cap-child-wait, one commit over master.
Inputs:
- spec: /Users/zarz/dev/xebia/flowbench-scenarios--issue-67/.claude/engineering-loop/items/issue-67/spec.md
- diff: `git diff master...HEAD` in the worktree
- run it: `uv run pytest -q tests/runner` and `uv run ruff check src tests`

Question: does the diff implement the spec correctly and completely, and is anything unsafe for an unattended live run? Look hard at: the pagination loop's termination and ordering; _wait_idle's new state (quiet_polls, heartbeat tuple) for regressions against the existing stall/prompt tests and against a session with NO children; the case where the agent asks the user a question while a child is busy; any test that now passes for the wrong reason; dead code or docs left stale (grep for nudge / child_busy / Continue.).

Output: a verdict line `APPROVE` or `REVISE`, then numbered objections each with file:line and the concrete failure scenario. No praise, no restatement.
