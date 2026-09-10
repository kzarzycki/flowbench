# Spec: N>1 runs per (case, flow) + aggregation (issue #3, dup #10)

## Problem

`scenarios/swe_planning/run.py` runs each case once: two flows produce
plans, one judge emits a `WINNER: A|B|tie` verdict. Planning output is
stochastic, so a single verdict is an anecdote, not a measurement. The
benchmark needs K repeated trials per case and an aggregate verdict.

The issue text predates the current architecture (it mentions per-run
"Scorecards" and a dimension vector, both deleted). The aggregation target
today is the categorical verdict from `parse_verdict` — see
`decisions.md` D2.

## Design

### `run_case_n` wrapper (`scenarios/swe_planning/run.py`)

New async function beside the untouched `run_case`:

```python
async def run_case_n(case_dir, *, run_id, n, make_flow_driver,
                     make_simulator, run_judge, runs_root=None,
                     max_turns=80, deadline_s=1800.0) -> dict
```

Return shape is **uniform for every n >= 1** (this is the contract):

```python
{"run_root": str,
 "trials": [<run_case meta dict>, ...],   # len == n, trial order
 "aggregate": {"n": int, "counts": {...}, "winner": str}}
```

- `n == 1`: delegates straight to `run_case` with the same `run_id` —
  today's flat on-disk layout, byte-for-byte identical (no `trial-XX/`
  dirs, no extra aggregate file; `run.json` is the single-run meta that
  `run_case` already writes). `trials` holds that one meta dict;
  `aggregate` is computed from its single verdict.
- `n > 1`: calls `run_case` sequentially (decisions D5) once per trial
  with `run_id = f"{run_id}/trial-{k:02d}"` for k in 1..n. Each trial dir
  therefore has the full existing single-run layout (per-flow
  `plan.md`/`transcript.md`/`session.json`, `judge.md`, `run.json`).
  After all trials, writes an aggregate `run.json` at
  `<runs_root>/<run_id>/run.json`.
- `n < 1`: `ValueError`.
- A trial that raises propagates immediately (decisions D6); completed
  trials' artifacts stay on disk.

Aggregate `run.json` shape (n > 1):

```json
{
  "run_id": "...", "case": "...", "n": 3,
  "A": "<flow>", "B": "<flow>",
  "trials": [{"trial": "trial-01", "winner": "a"}, ...],
  "counts": {"a": 2, "b": 1, "tie": 0, "unknown": 0},
  "winner": "a"
}
```

### `aggregate_verdicts` pure helper (`scenarios/swe_planning/helpers.py`)

```python
def aggregate_verdicts(winners: list[str]) -> dict
```

Input: the per-trial `winner` strings (`"a"|"b"|"tie"|"unknown"`).
Output: `{"counts": {...}, "winner": ...}` where counts always contains
all four keys and `winner` is the strict plurality of `a` vs `b`; equal
a/b counts → `"tie"` (decisions D7). `tie`/`unknown` trial verdicts are
counted but cannot win.

### CLI

Argument parsing moves to a module-level `_parse_args(argv=None)` (same
flags as today plus `--n`, int, default 1, rejected if < 1) so tests can
drive it directly. `main()` always calls `run_case_n` and prints from the
uniform return:

- `n == 1`: prints `result["trials"][0]` as JSON — byte-identical stdout
  to today's `result["meta"]` print — plus the existing run-root line.
- `n > 1`: prints `result["aggregate"]` as JSON plus the run-root line.

No mode-dependent key access; the `KeyError` class of bug is structurally
impossible.

### Docs

`scenarios/swe_planning/README.md`: document `--n`, the `trial-XX/`
layout, and the aggregate `run.json`.

## Out of scope

Parallel trials, judge-score dimensions (#8), report rendering (#6/#12),
new cases (#11). No changes to `run_case`, the judge, the simulator, or
flowbench.

## Acceptance criteria (machine-checkable)

1. `helpers.aggregate_verdicts` exists; unit tests cover: clear a-majority,
   clear b-majority, equal a/b → `"tie"`, all-`unknown` → `"tie"` with
   zero a/b counts, and mixed input including `tie`/`unknown` never
   winning plurality.
2. `run.py` exposes `run_case_n`; with fakes (offline), `n=3` produces
   `trial-01/ trial-02/ trial-03/` each containing the full single-run
   layout, plus a top-level `run.json` matching the aggregate shape above,
   and returns the uniform `{run_root, trials, aggregate}` shape (all
   three keys asserted).
3. With `n=1`, `run_case_n` (fakes, offline) produces today's flat
   `run_case` layout (no `trial-01/` dir) AND returns the same uniform
   shape — both asserted by a test, so the value `main()` prints exists
   in both modes.
4. No new test failures relative to the branch-point baseline; no
   existing test is edited or deleted. (The pre-existing
   `test_default_runs_root_is_sibling_of_repo` failure is environmental —
   worktree-location-sensitive, see decisions.md D1 — and exempt: it
   fails identically with and without this change.)
5. `_parse_args` exists; a test verifies `--n` defaults to 1, parses
   `--n 3`, and rejects `--n 0`.
6. `README.md` in the scenario dir mentions `--n` and the trial layout.
7. Diff touches only: `scenarios/swe_planning/run.py`,
   `scenarios/swe_planning/helpers.py`, `scenarios/swe_planning/README.md`,
   `tests/test_swe_planning_helpers.py`, `tests/test_swe_planning_run.py`,
   and `.claude/engineering-loop/items/issue-3/` artifacts.
