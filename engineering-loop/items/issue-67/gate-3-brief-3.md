Gate 3: adversarial review of one follow-up commit. Read-only; do not edit files.

Worktree (cwd): /Users/zarz/dev/agents/flowbench--live — branch loop/issue-67-wakeup, one commit over master (`git diff master...HEAD`). Read the commit message first: it states the live failure this fixes.
Inputs: /Users/zarz/dev/xebia/flowbench-scenarios--issue-67/.claude/engineering-loop/items/issue-67/spec.md; omnigent's own docs on pending_inputs at .venv/lib/python3.13/site-packages/omnigent/runtime/pending_inputs.py.
Run: `uv run pytest -q tests/runner`, `uv run ruff check src tests` (non-login shell; redirect caches if the sandbox blocks them).

Look hard at: the new _wait_idle state machine (had_children / cleared_at) — can it loop past the wake-up, re-arm wrongly, or return idle while a child is busy; interaction with the heartbeat/no_progress path; whether dropping pending_inputs from _PROMPT_KEYS loses a real human-prompt signal (cite omnigent code, not guesses); tests passing for the wrong reason.

Output: `APPROVE` or `REVISE`, then numbered objections with file:line and a concrete failure scenario. Nothing else.
