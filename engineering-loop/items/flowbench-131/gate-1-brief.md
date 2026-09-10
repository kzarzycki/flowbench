You are reviewing a design spec written by an engineer you've never met, for an unattended
pipeline — you are the only design review this work will ever get. Reject unless ALL hold:
(a) the spec solves the issue as filed — no scope invention, no scope loss; (b) every
acceptance criterion is objectively checkable from code/tests; (c) claims about the existing
codebase are true (verify by reading it); (d) every entry in decisions.md is a reasonable
inference from issue + code, not a product-judgment guess — if any decision required judgment
the issue doesn't support, reject and say which. Verdict: APPROVE, or REVISE with numbered
specific objections.

Inputs (read these yourself; nothing else is in scope):
- Issue: `gh issue view 131 --repo kzarzycki/flowbench`
- Spec: /Users/zarz/dev/xebia/flowbench-scenarios--i131/.claude/engineering-loop/items/flowbench-131/spec.md
- Decisions: /Users/zarz/dev/xebia/flowbench-scenarios--i131/.claude/engineering-loop/items/flowbench-131/decisions.md
- Engine worktree (read-only): /Users/zarz/dev/agents/flowbench--i131 — relevant files
  src/flowbench/types.py, src/flowbench/transcript.py, src/flowbench/driver/omnigent.py,
  src/flowbench/loop.py, src/flowbench/model.py, src/flowbench/watch.py,
  docs/design/runner.md, tests/driver/test_omnigent.py, tests/test_watch.py, tests/test_types.py
- Evidence run: /Users/zarz/dev/xebia/flowbench-runs/coding_workflow/s025p2-620b16b/superpowers/session.json
Do not modify any file. Reply with the verdict only, in the format above.
