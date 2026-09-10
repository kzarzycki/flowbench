# N>1 Runs + Aggregation Implementation Plan (issue #3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run each swe_planning case N times and aggregate the categorical judge verdicts (majority winner + per-trial table), behind a `--n` CLI flag that defaults to today's single-run behavior.

**Architecture:** A new `run_case_n` wrapper calls the untouched `run_case` sequentially once per trial into `trial-XX/` subdirs and writes an aggregate `run.json`; verdict tallying is a pure `aggregate_verdicts` helper. `main()` always goes through `run_case_n` and prints `trials[0]` (n=1, byte-identical stdout to today) or `aggregate` (n>1).

**Tech Stack:** Python 3 via `uv run`, pytest, asyncio. No new dependencies.

## Global Constraints (from the approved spec)

- Diff touches ONLY: `scenarios/swe_planning/run.py`,
  `scenarios/swe_planning/helpers.py`, `scenarios/swe_planning/README.md`,
  `tests/test_swe_planning_helpers.py`, `tests/test_swe_planning_run.py`,
  and `.claude/engineering-loop/items/issue-3/` artifacts.
- No changes to `run_case`, the judge, the simulator, or flowbench.
- Trials run sequentially; a trial that raises propagates immediately.
- Aggregation: strict plurality of `a` vs `b`; equal a/b counts → `"tie"`;
  `tie`/`unknown` trial verdicts are counted but can never win.
- `run_case_n` returns `{"run_root": str, "trials": list, "aggregate": dict}`
  for EVERY n >= 1; `aggregate` is `{"n": int, "counts": dict, "winner": str}`.
- n=1 must stay byte-for-byte identical on disk and stdout.
- No existing test is edited or deleted.
- Commits: Conventional Commits, ending with
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Environment note: run everything from the worktree root
  (`cd` to the repo checkout you were given). Expected suite state:
  `uv run pytest -q` shows exactly ONE failure,
  `tests/test_swe_planning_run.py::test_default_runs_root_is_sibling_of_repo`
  — pre-existing and environmental (worktree-location-sensitive; see
  `.claude/engineering-loop/items/issue-3/decisions.md` D1). Do NOT touch
  that test; treat "green" as "no failures other than that one".
- Async tests are plain sync `def test_*` bodies wrapping `asyncio.run(...)`
  (repo convention; no pytest-asyncio).

---

### Task 1: `aggregate_verdicts` pure helper

**Files:**
- Modify: `scenarios/swe_planning/helpers.py` (append at end of file)
- Test: `tests/test_swe_planning_helpers.py` (append at end of file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `aggregate_verdicts(winners: list[str]) -> dict` returning
  `{"counts": {"a": int, "b": int, "tie": int, "unknown": int}, "winner": str}`.
  Task 2 imports it from `scenarios.swe_planning.helpers`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_swe_planning_helpers.py`:

```python
def test_aggregate_verdicts_a_majority():
    out = aggregate_verdicts(["a", "a", "b"])
    assert out == {"counts": {"a": 2, "b": 1, "tie": 0, "unknown": 0}, "winner": "a"}


def test_aggregate_verdicts_b_majority():
    out = aggregate_verdicts(["b", "a", "b"])
    assert out["winner"] == "b"
    assert out["counts"]["b"] == 2


def test_aggregate_verdicts_equal_ab_is_tie():
    assert aggregate_verdicts(["a", "b"])["winner"] == "tie"


def test_aggregate_verdicts_all_unknown_is_tie():
    out = aggregate_verdicts(["unknown", "unknown"])
    assert out == {"counts": {"a": 0, "b": 0, "tie": 0, "unknown": 2}, "winner": "tie"}


def test_aggregate_verdicts_tie_and_unknown_never_win():
    # 'tie' has the highest raw count but winner is still the a/b plurality
    out = aggregate_verdicts(["tie", "tie", "tie", "a"])
    assert out["winner"] == "a"
    assert out["counts"] == {"a": 1, "b": 0, "tie": 3, "unknown": 0}
```

Also add `aggregate_verdicts` to the existing `from scenarios.swe_planning.helpers import (...)` block at the top of the file (keep the list alphabetical if it already is).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_swe_planning_helpers.py -q`
Expected: ImportError — `cannot import name 'aggregate_verdicts'`.

- [ ] **Step 3: Write the implementation**

Append to `scenarios/swe_planning/helpers.py`:

```python
def aggregate_verdicts(winners: list[str]) -> dict:
    """Tally per-trial winners ("a"|"b"|"tie"|"unknown"). Aggregate winner is
    the strict plurality of a vs b; equal counts -> "tie". tie/unknown trials
    are counted but can never win (categorical verdicts: no mean/median)."""
    counts = {"a": 0, "b": 0, "tie": 0, "unknown": 0}
    for w in winners:
        counts[w if w in counts else "unknown"] += 1
    if counts["a"] > counts["b"]:
        winner = "a"
    elif counts["b"] > counts["a"]:
        winner = "b"
    else:
        winner = "tie"
    return {"counts": counts, "winner": winner}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_swe_planning_helpers.py -q`
Expected: PASS (all, including pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/helpers.py tests/test_swe_planning_helpers.py
git commit -m "feat: aggregate_verdicts helper (majority winner over categorical verdicts)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `run_case_n` wrapper

**Files:**
- Modify: `scenarios/swe_planning/run.py` (new function after `run_case`; extend the helpers import block)
- Test: `tests/test_swe_planning_run.py` (append at end of file)

**Interfaces:**
- Consumes: `aggregate_verdicts` from Task 1; existing `run_case`,
  `default_runs_root`.
- Produces: `async def run_case_n(case_dir, *, run_id, n, make_flow_driver,
  make_simulator, run_judge, runs_root=None, max_turns=80,
  deadline_s=1800.0) -> dict` returning
  `{"run_root": str, "trials": [meta, ...], "aggregate": {"n", "counts", "winner"}}`.
  Task 3's `main()` calls it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_swe_planning_run.py` (reuses this file's `_FakeDriver`
and `_StubSim`; add `run_case_n` to the existing
`from scenarios.swe_planning.run import (...)` block):

```python
def _n_run_factories(judge_winners):
    """Factories for run_case_n tests; judge pops one scripted winner per trial."""
    winners = list(judge_winners)

    def make_flow_driver(flow, flow_dir):
        if flow["name"] == "superpowers":
            return _FakeDriver("# SP plan\nunknown flag key returns 404.", [])
        return _FakeDriver("# plain plan\nno unknown-key note.", [])

    def make_simulator(flow, sim_dir):
        return _StubSim(["PLAN_COMPLETE"])

    async def run_judge(judge_md, plan_a, plan_b, transcript_a, transcript_b, judge_dir):
        w = winners.pop(0)
        return f"Some prose about the plans.\nWINNER: {w}\nA: ok\nB: ok"

    return make_flow_driver, make_simulator, run_judge


def test_run_case_n_three_trials(tmp_path):
    case = scenario.CASE_DIR("feature_flag_service")
    mfd, ms, rj = _n_run_factories(["A", "B", "A"])

    result = asyncio.run(
        run_case_n(
            case,
            run_id="agg-run",
            n=3,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )

    # uniform return shape
    assert set(result) == {"run_root", "trials", "aggregate"}
    assert result["aggregate"] == {
        "n": 3,
        "counts": {"a": 2, "b": 1, "tie": 0, "unknown": 0},
        "winner": "a",
    }
    assert [t["winner"] for t in result["trials"]] == ["a", "b", "a"]

    root = Path(result["run_root"])
    assert root == tmp_path / "agg-run"
    # each trial dir has the full single-run layout
    for k in (1, 2, 3):
        trial = root / f"trial-{k:02d}"
        assert (trial / "superpowers" / "plan.md").is_file()
        assert (trial / "superpowers" / "transcript.md").is_file()
        assert (trial / "superpowers" / "session.json").is_file()
        assert (trial / "plain" / "plan.md").is_file()
        assert (trial / "judge.md").is_file()
        assert (trial / "run.json").is_file()
    # top-level aggregate run.json
    agg = json.loads((root / "run.json").read_text())
    assert agg["n"] == 3
    assert agg["case"] == "feature_flag_service"
    assert agg["A"] == "superpowers" and agg["B"] == "plain"
    assert agg["trials"] == [
        {"trial": "trial-01", "winner": "a"},
        {"trial": "trial-02", "winner": "b"},
        {"trial": "trial-03", "winner": "a"},
    ]
    assert agg["counts"] == {"a": 2, "b": 1, "tie": 0, "unknown": 0}
    assert agg["winner"] == "a"


def test_run_case_n_single_trial_keeps_flat_layout(tmp_path):
    case = scenario.CASE_DIR("feature_flag_service")
    mfd, ms, rj = _n_run_factories(["A"])

    result = asyncio.run(
        run_case_n(
            case,
            run_id="single-run",
            n=1,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )

    # same uniform shape as n>1, so main()'s print path exists in both modes
    assert set(result) == {"run_root", "trials", "aggregate"}
    assert result["aggregate"] == {
        "n": 1,
        "counts": {"a": 1, "b": 0, "tie": 0, "unknown": 0},
        "winner": "a",
    }
    root = Path(result["run_root"])
    assert root == tmp_path / "single-run"
    # flat single-run layout, no trial dirs, run.json is the single-run meta
    assert not (root / "trial-01").exists()
    assert (root / "superpowers" / "plan.md").is_file()
    meta = json.loads((root / "run.json").read_text())
    assert meta["winner"] == "a"
    assert result["trials"] == [meta] or result["trials"][0]["winner"] == "a"


def test_run_case_n_rejects_bad_n(tmp_path):
    case = scenario.CASE_DIR("feature_flag_service")
    mfd, ms, rj = _n_run_factories([])
    with pytest.raises(ValueError):
        asyncio.run(
            run_case_n(
                case,
                run_id="x",
                n=0,
                make_flow_driver=mfd,
                make_simulator=ms,
                run_judge=rj,
                runs_root=tmp_path,
            )
        )
```

Note on `test_run_case_n_single_trial_keeps_flat_layout`'s last assert:
`result["trials"][0]` is the in-memory meta dict `run_case` built; the
`run.json` on disk is its JSON serialization. Comparing them as loaded JSON
can differ on non-JSON-native values, so the fallback `winner` check keeps
the test honest without over-asserting. Keep the assert exactly as written.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_swe_planning_run.py -q`
Expected: ImportError — `cannot import name 'run_case_n'`.

- [ ] **Step 3: Write the implementation**

In `scenarios/swe_planning/run.py`:

1. Extend the helpers import block:

```python
from scenarios.swe_planning.helpers import (
    aggregate_verdicts,
    build_judge_prompt,
    compose_kickoff,
    load_flows,
    parse_verdict,
    render_transcript,
)
```

2. Add after `run_case` (before the omnigent-factories section):

```python
async def run_case_n(
    case_dir,
    *,
    run_id: str,
    n: int,
    make_flow_driver,
    make_simulator,
    run_judge,
    runs_root=None,
    max_turns: int = 80,
    deadline_s: float = 1800.0,
) -> dict:
    """Run run_case n times (sequentially; a failing trial propagates) and
    aggregate the categorical verdicts. Uniform return shape for every n:
    {"run_root", "trials", "aggregate"}. n=1 delegates and keeps today's
    flat layout; n>1 writes trial-XX/ subdirs plus an aggregate run.json."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    kwargs = dict(
        make_flow_driver=make_flow_driver,
        make_simulator=make_simulator,
        run_judge=run_judge,
        runs_root=runs_root,
        max_turns=max_turns,
        deadline_s=deadline_s,
    )

    if n == 1:
        result = await run_case(case_dir, run_id=run_id, **kwargs)
        agg = aggregate_verdicts([result["meta"]["winner"]])
        return {
            "run_root": result["run_root"],
            "trials": [result["meta"]],
            "aggregate": {"n": 1, **agg},
        }

    trials = []
    for k in range(1, n + 1):
        result = await run_case(case_dir, run_id=f"{run_id}/trial-{k:02d}", **kwargs)
        trials.append(result["meta"])

    agg = aggregate_verdicts([t["winner"] for t in trials])
    run_root = Path(runs_root or default_runs_root()) / run_id
    aggregate_meta = {
        "run_id": run_id,
        "case": Path(case_dir).name,
        "n": n,
        "A": trials[0]["A"],
        "B": trials[0]["B"],
        "trials": [
            {"trial": f"trial-{k:02d}", "winner": t["winner"]}
            for k, t in enumerate(trials, 1)
        ],
        "counts": agg["counts"],
        "winner": agg["winner"],
    }
    (run_root / "run.json").write_text(json.dumps(aggregate_meta, indent=2, default=str))
    return {"run_root": str(run_root), "trials": trials, "aggregate": {"n": n, **agg}}
```

(`run_root` already exists for n>1: every trial dir was created beneath it
by `run_case`'s `mkdir(parents=True)`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_swe_planning_run.py -q`
Expected: only the pre-existing environmental failure
(`test_default_runs_root_is_sibling_of_repo`); every other test passes,
including the three new ones.

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/run.py tests/test_swe_planning_run.py
git commit -m "feat: run_case_n — N sequential trials with aggregated verdict (issue #3)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CLI `--n`, `_parse_args`, README

**Files:**
- Modify: `scenarios/swe_planning/run.py` (replace `main`; add `_parse_args`)
- Modify: `scenarios/swe_planning/README.md` (Run section)
- Test: `tests/test_swe_planning_run.py` (append at end of file)

**Interfaces:**
- Consumes: `run_case_n` from Task 2.
- Produces: `_parse_args(argv=None) -> argparse.Namespace` with fields
  `case`, `run_id`, `runs_root`, `n`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_swe_planning_run.py` (add `_parse_args` to the
`from scenarios.swe_planning.run import (...)` block):

```python
def test_parse_args_n_defaults_to_1():
    args = _parse_args([])
    assert args.n == 1
    assert args.case == "todo_app"


def test_parse_args_n_accepts_3():
    assert _parse_args(["--n", "3"]).n == 3


def test_parse_args_n_rejects_zero():
    with pytest.raises(SystemExit):
        _parse_args(["--n", "0"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_swe_planning_run.py -q`
Expected: ImportError — `cannot import name '_parse_args'`.

- [ ] **Step 3: Write the implementation**

In `scenarios/swe_planning/run.py`, replace the whole `main()` function with:

```python
def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return n


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="todo_app", help="case name under cases/")
    ap.add_argument("--run-id", default=None, help="default: current timestamp")
    ap.add_argument("--runs-root", default=None, help="default: ../flowbench-runs/swe_planning")
    ap.add_argument("--n", type=_positive_int, default=1, help="trials per case (default 1)")
    return ap.parse_args(argv)


def main() -> None:
    from scenarios.swe_planning import scenario

    args = _parse_args()
    result = asyncio.run(
        run_case_n(
            scenario.CASE_DIR(args.case),
            run_id=args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S"),
            n=args.n,
            make_flow_driver=make_flow_driver_omni,
            make_simulator=make_simulator_omni,
            run_judge=run_judge_omni,
            runs_root=args.runs_root,
        )
    )
    # n=1: trials[0] is run_case's meta — byte-identical stdout to the old
    # single-run print. n>1: the aggregate {n, counts, winner}.
    payload = result["trials"][0] if args.n == 1 else result["aggregate"]
    print(json.dumps(payload, indent=2))
    print(f"\nRun written to: {result['run_root']}")
```

Also update the `argparse.Namespace` import need: `argparse` is already
imported at the top of the file; no import changes required.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_swe_planning_run.py -q`
Expected: only the pre-existing environmental failure; all new tests pass.

- [ ] **Step 5: Update the README**

In `scenarios/swe_planning/README.md`, replace the line:

```
Flags: `--run-id ID` (default: timestamp), `--runs-root PATH` (default:
`../flowbench-runs/swe_planning`). Needs a live omnigent server (see flowbench)
and `ANTHROPIC_API_KEY` unset (subscription billing).
```

with:

```
Flags: `--run-id ID` (default: timestamp), `--runs-root PATH` (default:
`../flowbench-runs/swe_planning`), `--n K` (default 1: trials per case).
Needs a live omnigent server (see flowbench) and `ANTHROPIC_API_KEY` unset
(subscription billing).

With `--n K` (K>1) each trial lands in `<run-id>/trial-01/ .. trial-KK/`
(full single-run layout each), plus an aggregate `<run-id>/run.json`:
per-trial winner table, verdict counts, and the majority winner (strict
a/b plurality; equal counts → tie).
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: exactly one failure — the pre-existing environmental
`test_default_runs_root_is_sibling_of_repo` (see Global Constraints).

- [ ] **Step 7: Commit**

```bash
git add scenarios/swe_planning/run.py scenarios/swe_planning/README.md tests/test_swe_planning_run.py
git commit -m "feat: --n CLI flag for multi-trial runs; document trial layout (issue #3)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Acceptance-criteria traceability

| Spec AC | Task | Test |
|---|---|---|
| 1 aggregate_verdicts + edge cases | 1 | `test_aggregate_verdicts_*` (5 tests) |
| 2 n=3 trial dirs + aggregate run.json + uniform shape | 2 | `test_run_case_n_three_trials` |
| 3 n=1 flat layout + uniform shape | 2 | `test_run_case_n_single_trial_keeps_flat_layout` |
| 4 no new failures vs baseline, no test edits | 1-3 | full-suite runs in each task's verify step |
| 5 _parse_args default/parse/reject | 3 | `test_parse_args_n_*` (3 tests) |
| 6 README documents --n + trial layout | 3 | Task 3 Step 5 (checkable in diff) |
| 7 diff touches only the listed files | 1-3 | checkable in diff |
