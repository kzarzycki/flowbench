# E00 — Guardrails: hygiene and CI gates

Milestone M0. Mechanical, low-risk. Do this before any structural epic so later refactors
are caught by machines.

## Goal

A weaker model working autonomously must not be able to silently regress the engine.
After this epic: naming drift is gone (so greps and docs stay truthful), every known live
incident has a named regression test, and CI fails on uncovered new code.

## Context

The code was written across many sessions, partly by weaker models. Symptoms in the tree
today: `flow.py` opens with "An flow = one approach…", `report/compare.py` still says
`{arm_name: …}` (the glossary retired "arm"), the driver's default model env var is
`OMNIGENT_PROBE_MODEL` (a leftover from the pre-flowbench probe spike), and the omnigent
extra is called `spike`. The war-story comments in `driver.py`/`loop.py` each describe a
live failure that shaped the code; not all of them have a test that would catch a refactor
dropping the behavior.

## Stories

### S00.1 Vocabulary and naming sweep

- Grep-driven: `arm`, `An flow`, `SUT` (glossary keeps SUT only in retired-terms), `probe`.
- Fix docstrings/comments in place; no behavior change.
- `OMNIGENT_PROBE_MODEL` → `FLOWBENCH_MODEL` (read new name first, fall back to old,
  comment marks the old one deprecated). The `spike` extra rename happens in S01.4 with
  the Inspect removal (it changes install instructions; keep it with that PR).
- Verify: V6 (vocabulary sweep), V1 (offline suite) — see `../verification.md`.

### S00.2 CI hardening

- Add coverage to the offline suite: `pytest --cov=src/flowbench --cov-report=xml`;
  gate PRs with `diff-cover` (already a dev dep) at a high threshold for changed lines.
- Keep an absolute floor modest (the driver's live paths can't run offline); the
  diff-cover gate is the real protection.
- Record the offline-suite wall-clock budget in CI (fail if it balloons) so the suite
  stays fast enough to run every loop iteration.
- Verify: V8 wired into CI (prove it: a draft PR adding an uncovered function fails);
  V1 stays green.

### S00.3 Regression tests for the war stories

Each of these constraints came from a live incident. For each: point at the existing test
if one covers it, else write one against `FakeDriver`-style doubles:

| Constraint (source comment) | Behavior to pin |
| --- | --- |
| Lying idle / settle loop (`driver._send_once`) | idle status with no new assistant message keeps polling, then reports `timeout`, never a stale reply |
| Undelivered injection retry (`driver.send`) | `failed` + label `runner_error`/"not delivered" → wait and re-send same text, bounded attempts |
| Read-retry on transient transport (`_read_retry`) | one `httpx.ReadError` during polling does not kill the run; sends are never retried by it |
| Nudge cap (`loop._MAX_CONSEC_NUDGES`) | a child that never clears `busy` still reaches a simulator turn after 3 nudges |
| DONE with late artifact (`loop` grace poll) | DONE token with missing artifact polls up to `artifact_grace_s` before capture |
| Control-message filtering (`dedup_items`) | `<task-notification>` items never enter the cleaned transcript |
| Fresh-text trust on failed turns (issue #39, downstream today) | covered downstream now; moves to the driver in S02.3 — note the migration in the test file |
| Subscription guard (`start()`) | `ANTHROPIC_API_KEY` set → `start()` raises before any HTTP call (the whole of `start()` is untested today) |
| Lying-idle heuristic (`_wait_idle`) | direct test: `idle` before `running` within `min_wait` is not trusted; `failed` returns immediately (settle tests currently stub around this) |
| Undelivered-label parsing (`_injection_undelivered`) | the `runner_error` + "not delivered" label match is exercised against realistic label payloads, not stubbed |
| Retry exhaustion (`send`) | all attempts consumed → the failed result is returned, attempts counted correctly |
| Loop deadline (`deadline_s`) | wall-clock backstop actually stops the loop |
| Scorecard shape parity | the scorecard the orchestrator writes and the shape `compare` reads are asserted against the same fixture, not two hand-built dicts |

- Verify: V1; each table row maps to a named test in `tests/runner/`.

### S00.4 Docs wiring

- CLAUDE.md: add a pointer line — "planning structural work? read `docs/roadmap/` first".
- `docs/design/runner.md`: refresh so it matches the code as of this epic (it already
  documents the one-execution-model decision; keep it current).
- Verify: links resolve; no duplicated content between CLAUDE.md and the docs.

## Non-goals

Any behavior change; any module move (that is E01/E02); fixing findings marked as design
debt in `current-state.md` (those have their own epics).

## Done

All four stories merged, CI green with the new gates, live validation not required
(no runtime behavior changed) — but run V4 anyway if S00.1 touched `driver.py` strings,
since that file is imported by the live path.
