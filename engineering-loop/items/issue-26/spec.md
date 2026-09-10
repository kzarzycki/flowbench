# issue-26: Aggregate report.html for n>1 runs — design spec

**Problem.** `--n 2+` runs write per-trial `report.html` pages but the top-level
aggregate `run.json` (counts, winner, score_means, per-trial winners) is never
rendered — reading an n>1 run means opening JSON.

**Change.** One new template path in `scenarios/swe_planning/report.py`:

- `render_aggregate_report(run_root: Path) -> Path` — pure reader over the
  aggregate `run.json`; writes `<run_root>/report.html` (same self-contained
  html + existing `CSS` block). Content, top to bottom:
  1. Header: case, run_id, n.
  2. Winner banner from canonical counts: `🏆 <flow> wins <x>–<y> (n=<n>)`;
     `winner == "tie"` → `Tie <x>–<y>`. Nonzero `tie`/`unknown` counts appear in
     the banner tail (e.g. `· 1 tie`).
  3. Score-means table: one row per criterion (union of a/b keys, insertion
     order), columns labeled with the canonical A/B flow names. Omitted entirely
     when both sides are empty (pre-SCORES judges).
  4. Trials table: one row per `trials[]` entry — trial id (linked to
     `<trial>/report.html`, relative href) and winner flow name (or tie/unknown).
- `render_any(run_root: Path) -> Path` — dispatch: aggregate shape (`"trials"`
  key present) → `render_aggregate_report`, else `render_report`. `__main__`
  switches to `render_any` so the standalone command works on both dir kinds.
- `run_case_n` (n>1 path, `scenarios/swe_planning/run.py`) calls
  `render_aggregate_report(run_root)` immediately after writing the aggregate
  run.json, mirroring `run_case`'s existing `render_report` call. n=1 path
  unchanged.

**Why safe.** Renderer is a pure reader (no run.json shape changes, no engine
changes); the only orchestrator delta is one call after the aggregate write.
Existing single-run rendering and its tests are untouched.

**Out of scope.** Cross-trial flow-stats rollups (aggregate run.json carries no
`models`/`flow_stats`), aggregate-page styling beyond the existing CSS, changes
to run.json shapes. (Decisions and sources: `decisions.md`.)

## Acceptance criteria (machine-checkable)

1. `run_case_n` with `n=2` fake factories writes `<run_root>/report.html`
   containing both trial links (`trial-01/report.html`, `trial-02/report.html`)
   and the counts-derived winner text. (offline test)
2. `render_aggregate_report` on a hand-built aggregate dir with
   `winner: "tie"` and empty `score_means` renders a Tie banner and NO scores
   table, without raising. (offline test)
3. `render_aggregate_report` renders score-mean values (e.g. `4.5`) and canonical
   flow-name column labels when `score_means` is populated. (offline test)
4. `render_any` picks the aggregate template for an aggregate-shaped run.json and
   the single-run template for a single-run-shaped one. (offline test)
5. Full offline suite green (`uv run pytest -q`), no existing test modified.
