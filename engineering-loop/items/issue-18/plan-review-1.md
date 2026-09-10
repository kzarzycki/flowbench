# Plan Review 1 — Issue #18 (`artifact_grace_s` through `run_case`)

## Verdict: APPROVE

Executing the plan exactly as written satisfies all eight ACs. The RED step genuinely fails and the GREEN step genuinely fixes it. Scope is clean. The one non-obvious interception mechanic checks out. Two minor wording imprecisions are noted below but neither blocks a mid-tier implementer.

## (a) AC → discharging step

Every AC (AC1–AC8) maps to a discharging plan step: AC1/AC6 → Task 1 step 2; AC2 → step 1; AC3 → step 3; AC4 → step 4 + gates guard; AC5/AC7/AC8 → gates. No gaps.

## (b) RED/GREEN mechanics — verified against the code

- Monkeypatch interception works: `run.py:20` binds `run_agent_session` into the module namespace; patching `scenarios.swe_planning.run.run_agent_session` intercepts the call.
- RED genuinely fails on main: argument binding at the call expression raises `TypeError: run_case() got an unexpected keyword argument 'artifact_grace_s'` before asyncio.run.
- Recorder return `{"items": [], "events": [], "artifact_text": "# p"}` satisfies all post-session code (render_transcript([]) OK, json.dumps OK, plans_missing == []).
- Two flows sharing one global recorder breaks nothing; judge fake `"WINNER: A"` parses via helpers.parse_verdict → "a"; run.json write succeeds.
- Fast paths preserved: the spec's set of two hang-prone tests is exhaustive — no other test reaches the DONE path.

## (c) Scope

Plan touches only run.py + test file + issue-18 artifacts — matches AC7; non-goals align with spec out-of-scope. No drift.

## (d) Executability

Parameter placement, forwarding form, test names, commit message, and verification command all pinned. Mid-tier implementer needs no judgment calls.

## Non-blocking observations (no fix required)

1. "monkeypatch-or-stub `run_judge`" is slightly misleading — `run_judge` is a `run_case` parameter, not a module global; pass a fake as the `run_judge=` argument (the pattern every existing test uses).
2. The recorder must accept two positional args (`driver`, `simulator`) plus `**kwargs` — e.g. `async def rec(*args, **kwargs)` — since `run_case` passes driver/simulator positionally.

Neither observation changes any AC outcome. Approved.
