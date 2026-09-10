You are reviewing a revised design spec AND its implementation plan for an unattended
pipeline. Both were approved once, then the base branch moved under them: origin/master
1a6a714 migrated the two label reads in src/flowbench/driver/omnigent.py onto the SDK
(`self._client.sessions.get()` under `asyncio.timeout(_LABEL_READ_S)`), and the spec's
malformed-body contract and Task 1 were rewritten for that substrate. Review the whole of
both documents, not just the delta. Spec — reject unless ALL hold: (a) solves the issue as
filed, no scope invention or loss; (b) every acceptance criterion is objectively checkable
from code/tests; (c) claims about the codebase and the installed SDK are true — verify by
reading `.venv/lib/python3.13/site-packages/omnigent_client/_sessions.py` (`Session.from_dict`,
`get`) and `_errors.py`, and probe with `uv run python` if in doubt; (d) every decisions.md
entry is a reasonable inference from issue + code, not a product guess. Plan — reject unless:
(a) full criterion→task→test traceability (build it yourself); (b) the branch is green after
each task — note Tasks 2 and 3 are already on the branch, Task 1 lands last; (c) exact paths
and interfaces per task; (d) tests would catch the bug, not just the happy path. Size S: reject
gaps and bloat alike. Verdict: APPROVE or REVISE with numbered objections, marked [spec] or
[plan]. Start your final message with the single word APPROVE or REVISE.

Inputs (your shell cwd is the engine worktree, branch already at origin/master + Tasks 2, 3):
- Issue: `gh issue view 106 -R kzarzycki/flowbench`; epic section "S02.6 Error taxonomy" in
  docs/roadmap/epics/E02-runtime-robustness.md.
- Spec: /Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/spec.md
- Decisions: /Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/decisions.md
- Plan: /Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md
- Code: src/flowbench/driver/omnigent.py, src/flowbench/transcript.py, src/flowbench/watch.py,
  scenarios/coding_workflow/cases/todo_app/scorers.py, pyproject.toml, docs/design/runner.md,
  tests/driver/test_omnigent.py (`_label_client`, `_real_sdk_client`, `_FakeSessions`).
