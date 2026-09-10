# Aggregate report.html for n>1 runs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render an `--n 2+` run's top-level aggregate `run.json` as a self-contained `report.html` (winner banner from canonical counts, score-means table, per-trial rows linking to trial reports).

**Architecture:** One new template path in `scenarios/swe_planning/report.py` (`render_aggregate_report`, a pure reader like the existing `render_report`), a shape dispatcher (`render_any`) so the standalone `__main__` works on both run-dir kinds, and one call added to `run_case_n`'s n>1 path right after it writes the aggregate run.json.

**Tech Stack:** stdlib only (json/html/pathlib), existing `CSS` block in report.py, pytest offline suite.

## Global Constraints (verbatim from spec)

- Renderer is a pure reader (no run.json shape changes, no engine changes); the only orchestrator delta is one call after the aggregate write.
- Existing single-run rendering and its tests are untouched — no existing test modified.
- Same self-contained html + existing `CSS` block.
- Out of scope: cross-trial flow-stats rollups, styling beyond the existing CSS, run.json shape changes.
- Full offline suite green (`uv run pytest -q`).

**Worktree:** `/Users/zarz/dev/xebia/flowbench-scenarios/.claude/worktrees/loop+issue-26-aggregate-report` (branch `loop/issue-26-aggregate-report`). All paths below relative to it. Run tests with `uv run pytest ...`.

---

### Task 1: `render_aggregate_report` (spec AC2 + AC3)

**Files:**
- Modify: `scenarios/swe_planning/report.py` (append after `render_report`, before `if __name__`)
- Test: `tests/test_swe_planning_run.py` (append at end of file)

**Interfaces:**
- Consumes: existing `CSS` str and `html`/`json`/`Path` imports in report.py.
- Produces: `render_aggregate_report(run_root: Path) -> Path` — reads `<run_root>/run.json` (aggregate shape: `run_id, case, n, A, B, trials[], counts, winner, score_means`), writes and returns `<run_root>/report.html`. The page's `<h1>` is exactly `flowbench aggregate report` (Task 2's dispatch test keys on it). Later tasks import it from `scenarios.swe_planning.report`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_swe_planning_run.py`:

```python
# --- aggregate report rendering (issue #26) ---------------------------------

from scenarios.swe_planning.report import render_aggregate_report


def _aggregate_dir(tmp_path, *, winner, counts, score_means, winner_flows=("superpowers", "plain")):
    """Hand-built aggregate run dir: run.json only (renderer must not need more)."""
    root = tmp_path / "agg"
    root.mkdir()
    meta = {
        "run_id": "agg",
        "case": "todo_app",
        "n": sum(counts.values()),
        "A": "superpowers",
        "B": "plain",
        "trials": [
            {"trial": f"trial-{k:02d}", "winner": w[0], "winner_flow": w[1]}
            for k, w in enumerate(zip(("a", "b"), winner_flows, strict=False), 1)
        ],
        "counts": counts,
        "winner": winner,
        "score_means": score_means,
    }
    (root / "run.json").write_text(json.dumps(meta))
    return root


def test_aggregate_report_tie_no_scores(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="tie",
        counts={"a": 1, "b": 1, "tie": 0, "unknown": 0},
        score_means={"a": {}, "b": {}},
        winner_flows=("superpowers", "plain"),
    )
    out = render_aggregate_report(root)
    text = out.read_text()
    assert out == root / "report.html"
    assert "flowbench aggregate report" in text
    assert "Tie 1–1" in text
    assert "Score means" not in text  # both sides empty -> section omitted
    assert 'href="trial-01/report.html"' in text
    assert 'href="trial-02/report.html"' in text


def test_aggregate_report_winner_and_scores(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="a",
        counts={"a": 2, "b": 0, "tie": 0, "unknown": 0},
        score_means={
            "a": {"fulfillment": 5.0, "discovery": 4.5},
            "b": {"fulfillment": 4.0, "discovery": 3.5},
        },
        winner_flows=("superpowers", "superpowers"),
    )
    text = render_aggregate_report(root).read_text()
    assert "superpowers wins 2–0 (n=2)" in text
    assert "Score means" in text
    assert "4.5" in text and "3.5" in text
    # canonical flow names label the score columns
    assert "superpowers (A)" in text and "plain (B)" in text


def test_aggregate_report_shows_nonzero_tie_unknown_counts(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="a",
        counts={"a": 2, "b": 1, "tie": 1, "unknown": 0},
        score_means={"a": {}, "b": {}},
    )
    text = render_aggregate_report(root).read_text()
    assert "superpowers wins 2–1 (n=4)" in text
    assert "1 tie" in text
    assert "unknown" not in text.split("<footer>")[0]  # zero counts stay hidden
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_swe_planning_run.py -k aggregate_report -v`
Expected: FAIL at import — `ImportError: cannot import name 'render_aggregate_report'`

- [ ] **Step 3: Implement `render_aggregate_report`**

Append to `scenarios/swe_planning/report.py` (after `render_report`, before `if __name__`):

```python
def render_aggregate_report(run_root: Path) -> Path:
    """n>1 template path: aggregate run.json (counts/winner/score_means/trials)
    -> report.html linking the per-trial reports. Pure reader, same CSS."""
    meta = json.loads((run_root / "run.json").read_text())
    a_name, b_name = meta["A"], meta["B"]
    counts = meta["counts"]

    if meta["winner"] == "a":
        headline = f"🏆 {a_name} wins {counts['a']}–{counts['b']} (n={meta['n']})"
    elif meta["winner"] == "b":
        headline = f"🏆 {b_name} wins {counts['b']}–{counts['a']} (n={meta['n']})"
    else:
        headline = f"Tie {counts['a']}–{counts['b']} (n={meta['n']})"
    extras = [f"{counts[k]} {k}" for k in ("tie", "unknown") if counts.get(k)]
    banner = html.escape(" · ".join([headline, *extras]))

    means = meta.get("score_means") or {}
    a_means, b_means = means.get("a") or {}, means.get("b") or {}
    criteria = list(dict.fromkeys([*a_means, *b_means]))
    scores_html = ""
    if criteria:
        rows = "".join(
            f"<tr><td>{html.escape(c)}</td><td>{a_means.get(c, '–')}</td>"
            f"<td>{b_means.get(c, '–')}</td></tr>"
            for c in criteria
        )
        scores_html = f"""<h2>Score means</h2>
<table><tr><th>criterion</th><th>{html.escape(a_name)} (A)</th>
<th>{html.escape(b_name)} (B)</th></tr>{rows}</table>"""

    trial_rows = "".join(
        f"<tr><td><a href=\"{t['trial']}/report.html\">{html.escape(t['trial'])}</a></td>"
        f"<td>{html.escape(str(t.get('winner_flow') or t['winner']))}</td></tr>"
        for t in meta["trials"]
    )

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>flowbench · {meta["case"]} · {meta["run_id"]} · aggregate</title>
<style>{CSS}</style></head><body><main>
<h1>flowbench aggregate report</h1>
<div class="sub">case <strong>{meta["case"]}</strong> · run <strong>{meta["run_id"]}</strong>
 · {meta["n"]} trials · scenario swe_planning</div>
<div class="banner">{banner}</div>
{scores_html}
<h2>Trials</h2>
<table><tr><th>trial</th><th>winner</th></tr>{trial_rows}</table>
<footer>generated from {run_root} · A/B canonical to trial-01 · per-trial reports linked above</footer>
</main></body></html>"""
    out = run_root / "report.html"
    out.write_text(doc)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_swe_planning_run.py -k aggregate_report -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/report.py tests/test_swe_planning_run.py
git commit -m "feat: render aggregate report.html for n>1 runs"
```

---

### Task 2: `render_any` shape dispatch + `__main__` (spec AC4)

**Files:**
- Modify: `scenarios/swe_planning/report.py` (append `render_any` after `render_aggregate_report`; replace the `__main__` block)
- Test: `tests/test_swe_planning_run.py` (append at end of file)

**Interfaces:**
- Consumes: `render_report` and `render_aggregate_report(run_root: Path) -> Path` from Task 1; test helpers `_aggregate_dir`, `_n_run_factories`, `run_case`, `scenario` already in the test file.
- Produces: `render_any(run_root: Path) -> Path` — dispatches on the run.json shape: `"trials"` key present → aggregate template, else single-run template.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_swe_planning_run.py`:

```python
def test_render_any_dispatches_on_shape(tmp_path):
    from scenarios.swe_planning.report import render_any

    # aggregate-shaped dir -> aggregate template
    agg = _aggregate_dir(
        tmp_path,
        winner="tie",
        counts={"a": 1, "b": 1, "tie": 0, "unknown": 0},
        score_means={"a": {}, "b": {}},
    )
    assert "flowbench aggregate report" in render_any(agg).read_text()

    # single-run-shaped dir (full run_case output) -> single-run template
    mfd, ms, rj = _n_run_factories(["A"])
    result = asyncio.run(
        run_case(
            scenario.CASE_DIR("feature_flag_service"),
            run_id="single",
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )
    text = render_any(Path(result["run_root"])).read_text()
    assert "flowbench run report" in text
    assert "flowbench aggregate report" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_swe_planning_run.py::test_render_any_dispatches_on_shape -v`
Expected: FAIL — `ImportError: cannot import name 'render_any'`

- [ ] **Step 3: Implement `render_any` and switch `__main__`**

Append to `scenarios/swe_planning/report.py` after `render_aggregate_report`:

```python
def render_any(run_root: Path) -> Path:
    """Standalone entrypoint over either run-dir kind: the aggregate run.json is
    the only one with a `trials` key (run.py writes both shapes)."""
    meta = json.loads((run_root / "run.json").read_text())
    return render_aggregate_report(run_root) if "trials" in meta else render_report(run_root)
```

Replace the existing `__main__` block:

```python
if __name__ == "__main__":
    print(render_any(Path(sys.argv[1])))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_swe_planning_run.py::test_render_any_dispatches_on_shape -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/report.py tests/test_swe_planning_run.py
git commit -m "feat: report module dispatches single-run vs aggregate shape"
```

---

### Task 3: wire `run_case_n` + full-suite gate (spec AC1 + AC5)

**Files:**
- Modify: `scenarios/swe_planning/run.py:31` (import) and the n>1 path of `run_case_n` (immediately after `(run_root / "run.json").write_text(...)`, currently run.py:231)
- Test: `tests/test_swe_planning_run.py` (append at end of file)

**Interfaces:**
- Consumes: `render_aggregate_report(run_root: Path) -> Path` from Task 1; `_n_run_factories` fixture.
- Produces: `run_case_n` (n>1) leaves `<run_root>/report.html` next to the aggregate run.json. No signature change.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_swe_planning_run.py`:

```python
def test_run_case_n_writes_aggregate_report(tmp_path):
    case = scenario.CASE_DIR("feature_flag_service")
    # trial-02 runs swapped: positional B is superpowers, so A,B -> superpowers 2-0
    mfd, ms, rj = _n_run_factories(["A", "B"])
    result = asyncio.run(
        run_case_n(
            case,
            run_id="agg-report-run",
            n=2,
            make_flow_driver=mfd,
            make_simulator=ms,
            run_judge=rj,
            runs_root=tmp_path,
        )
    )
    text = (Path(result["run_root"]) / "report.html").read_text()
    assert "flowbench aggregate report" in text
    assert "superpowers wins 2–0 (n=2)" in text
    assert 'href="trial-01/report.html"' in text
    assert 'href="trial-02/report.html"' in text
    # scripted judge emits no SCORES lines -> section omitted, no crash
    assert "Score means" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_swe_planning_run.py::test_run_case_n_writes_aggregate_report -v`
Expected: FAIL — `FileNotFoundError: ... report.html`

- [ ] **Step 3: Wire the call**

In `scenarios/swe_planning/run.py`, change the import (line 31):

```python
from scenarios.swe_planning.report import render_aggregate_report, render_report
```

In `run_case_n`, right after `(run_root / "run.json").write_text(json.dumps(aggregate_meta, indent=2, default=str))`:

```python
    (run_root / "run.json").write_text(json.dumps(aggregate_meta, indent=2, default=str))
    render_aggregate_report(run_root)  # pure reader over the files just written
    return {"run_root": str(run_root), "trials": trials, "aggregate": {"n": n, **agg}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_swe_planning_run.py::test_run_case_n_writes_aggregate_report -v`
Expected: PASS

- [ ] **Step 5: Full offline suite + lint gate (AC5)**

Run: `uv run pytest -q`
Expected: all pass (baseline was 100 passed, 1 skipped; now 105 passed, 1 skipped), no existing test modified (`git diff --stat origin/main -- tests/` shows only appended lines in tests/test_swe_planning_run.py).

Run: `uv run pre-commit run --all-files`
Expected: all hooks pass.

- [ ] **Step 6: Commit**

```bash
git add scenarios/swe_planning/run.py tests/test_swe_planning_run.py
git commit -m "feat: run_case_n renders the aggregate report"
```
