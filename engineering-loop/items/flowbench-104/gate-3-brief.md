Adversarial whole-branch review, fresh context. You are the last reviewer before merge; you must be able to fail this branch.

Inputs ONLY:
- Spec: /Users/zarz/dev/xebia/flowbench-scenarios--s024/.claude/engineering-loop/items/flowbench-104/spec.md
- Plan: /Users/zarz/dev/xebia/flowbench-scenarios--s024/.claude/engineering-loop/items/flowbench-104/plan.md
- Engine diff: `cd /Users/zarz/dev/agents/flowbench--s024 && git diff origin/master...HEAD` (full branch), plus read access to that worktree.
- Paired scenarios diff: `cd /Users/zarz/dev/xebia/flowbench-scenarios--s024 && git diff origin/main...HEAD -- scripts tests` plus read access to that worktree (its venv has the engine worktree installed editable; run its suite with `uv run --no-sync pytest -q`).

Checklist, all non-negotiable:
(a) every acceptance criterion in the spec is met AND covered by a test that would fail without the change — mutation-test at least AC3, AC4, AC5 and the probe wiring by reverting the relevant line and watching the named test go red;
(b) no test weakened, skipped, or tailored to the implementation;
(c) no unexplained changes beyond the plan;
(d) the diff touches no CI config, no gate definitions, and nothing under `.claude/` except `engineering-loop` state/artifacts;
(e) docs state current truth once, in the doc that owns that kind of content — a retired item is removed, not struck through or annotated "done (date)"; the same fact is not restated in a second file (link to it instead); no narration of how the text came to be. History belongs in git and LOG.md;
(f) correctness: the DONE grace-poll under `asyncio.timeout` + `asyncio.to_thread`, the post-capture probe, `find_artifact`, the fakes; concurrency-region discipline (no edits to `OmnigentDriver.start`, the client import block, the labels GETs, `except Exception` sites).
Run `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .` in the engine worktree yourself.

Verdict: APPROVE, or REVISE with file:line objections. Output the verdict line first, then numbered objections, nothing else.
