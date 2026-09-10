You are reviewing a design spec written by an engineer you've never met, for an unattended pipeline — you are the only design review this work will ever get. Reject unless ALL hold: (a) the spec solves the issue as filed — no scope invention, no scope loss; (b) every acceptance criterion is objectively checkable from code/tests; (c) claims about the existing codebase are true (verify by reading it); (d) every entry in decisions.md is a reasonable inference from issue + code, not a product-judgment guess — if any decision required judgment the issue doesn't support, reject and say which. Verdict: APPROVE, or REVISE with numbered specific objections.

Inputs (read these yourself; shell access is available):
- Issue: https://github.com/kzarzycki/flowbench/issues/41 — text below.
- Spec: /Users/zarz/dev/xebia/flowbench-scenarios/.claude/engineering-loop/items/issue-41/spec.md
- Decisions: /Users/zarz/dev/xebia/flowbench-scenarios/.claude/engineering-loop/items/issue-41/decisions.md
- Epic (story S01.1 + "What moves where" table): /Users/zarz/dev/agents/flowbench/docs/roadmap/epics/E01-one-execution-model.md
- Source being moved: /Users/zarz/dev/xebia/flowbench-scenarios/scenarios/swe_planning/{run,helpers,report,watch}.py and tests/test_swe_planning_{helpers,run}.py
- Engine target: /Users/zarz/dev/agents/flowbench/src/flowbench/ (branch loop/issue-41-lift-runtime, currently identical to master)

--- ISSUE #41 ---
S01.1 Lift the generic runtime out of swe_planning into the engine

Epic E01 — one execution model (`docs/roadmap/epics/E01-one-execution-model.md`), story S01.1.

Move the generic runtime from `$SCENARIOS/scenarios/swe_planning/` into the engine, behavior-preserving (copy, adapt imports, no redesign). Mapping per the E01 "What moves where" table:

- `run.py` run_case / run_case_n + omnigent factories → `flowbench/run.py`
- `run.py` OmnigentModel → `flowbench/model.py` as `SessionModel` (issue-#39 freshness retry kept exactly)
- `helpers.py` load_flows / compose_kickoff → `flowbench/flowspec.py`
- `helpers.py` parse_verdict / parse_scores / build_judge_prompt / aggregate_* → `flowbench/runner/judge.py`; make `last_json_object` string-aware while moving
- `helpers.py` render_transcript + driver `_item_text`, dedup_items, is_control_message, last_assistant_text, n_assistant_messages → `flowbench/transcript.py` (closes #3)
- `report.py` → `flowbench/report/run_report.py`; `watch.py` → `flowbench/watch.py`
- new `flowbench/testing.py`: FakeDriver + scripted simulator + canned judge
- port the relevant offline tests

Verify: V1 (`uv run pytest -q`) + `uv run --no-extra spike python -c "import flowbench.run, flowbench.model"` (no omnigent import at module top level).

Paired follow-up: S01.2 (scenarios consumes the engine, deletes local copies).
