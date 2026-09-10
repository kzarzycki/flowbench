# issue-26 decisions (rule-3 self-answered)

D1. **Where does the renderer live?** `scenarios/swe_planning/report.py`, new
`render_aggregate_report(run_root)`. Source: the issue itself ("report.py is the
natural home; ... needs its own template path"). Not a new module.

D2. **How does the standalone CLI pick a template?** Dispatch on run.json shape:
aggregate has a `trials` key, single-run does not (single predicate). A small
`render_any(run_root)` dispatches; `__main__` calls it. Source: issue requires the
aggregate shape to have "its own template path"; the module docstring promises a
single standalone entrypoint over a run dir — keeping one entrypoint that works on
both dirs is the non-breaking reading.

D3. **What goes on the page?** Exactly the issue's list: winner banner from
canonical counts (e.g. "superpowers wins 2–0"), score-means table per side,
per-trial rows linking to `trial-XX/report.html`. No flows table — the aggregate
run.json has no `models`/`flow_stats` (issue states this), and inventing a
cross-trial stats rollup is scope invention.

D4. **Wiring.** `run_case_n` (n>1 path) calls `render_aggregate_report(run_root)`
right after writing the aggregate run.json, mirroring `run_case`'s
`render_report(run_root)` "pure reader over the files just written" pattern
(run.py:157). n=1 path unchanged (flat layout already rendered by `run_case`).

D5. **Edge shapes.** `winner` can be "tie" (equal counts — aggregate_verdicts never
returns "unknown" at the top level but counts carry tie/unknown trials): banner says
"Tie" and shows counts; nonzero tie/unknown counts are displayed. `score_means` can
be `{"a": {}, "b": {}}` (judges emitted no SCORES lines): skip the scores section,
no crash. Source: helpers.aggregate_verdicts/parse_scores lenient-by-design
docstrings.

D6. **Links.** Relative hrefs (`trial-01/report.html`) — the aggregate page sits in
the run root, trials are direct children (run.py:201 layout). Self-contained html,
same CSS block reused.

D7. **Validation.** Issue says "run with --n 2, aggregate report renders" — the
offline fake-factory test (`_n_run_factories` pattern, tests/test_swe_planning_run.py)
verifies the same contract without a live run. Live confirmation rides Phase 9.5 /
issue #27's n>=5 run rather than a dedicated paid run for a report page.
