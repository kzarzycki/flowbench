# decisions.md — issue #3 (N>1 runs per (case, flow) + aggregation)

Self-answered questions per loop rule 3. The spec reviewer audits these.

## D1. Baseline test failure in the worktree is environmental
`tests/test_swe_planning_run.py::test_default_runs_root_is_sibling_of_repo`
fails in the loop worktree and passes on the same commit in the main
checkout. Cause: the test asserts `"flowbench-scenarios" not in p.parts`,
and the worktree lives at
`flowbench-scenarios/.claude/worktrees/loop+issue-3-n-runs-aggregation/`,
so `_REPO_ROOT.parent` keeps the repo name in the path. Location-sensitive
test, not a red base. Decision: treat baseline as green; do not modify the
test unless the issue's work requires touching it.

## D2. Aggregation target is the categorical WINNER verdict, not a
## "dimension vector"
The issue text predates the rework: it references per-run "Scorecards" and
a dimension vector, both deleted. The current judge
(`scenarios/swe_planning/run.py`, `helpers.py`, `cases/*/judge.md`) returns
free-text prose + a `WINNER: A|B|tie` tail. Decision: "aggregate the
dimension vector (mean + spread)" maps to "tally WINNER verdicts across K
runs (majority winner) and record the per-run verdict table"; "surface
variance in the report" maps to showing the per-run verdict spread in
run.json (and the aggregate block). Duplicate issue #10 states exactly this
shape ("--n to run each flow N times and aggregate verdicts (majority
winner, per-run table in run.json)"), confirming the intent.

## D3. K is configurable, default preserves current behavior
Issue says "Decide K". Decision: expose `--n` (per #10's wording), default
1 — single-run behavior and outputs stay unchanged when unset. No hardcoded
K; the "decide K and the aggregation" ask is resolved as: aggregation =
majority vote over categorical verdicts (mean/median are meaningless for
A|B|tie), K = user-chosen via --n.

## D4. Approach: wrapper around run_case, not a rewrite of it
Three options considered: (a) loop inside run_case with layout forked on n;
(b) new `run_case_n` wrapper calling the untouched `run_case` once per
trial into `trial-XX/` subdirs, aggregating after; (c) always-trials layout
even for n=1. Chose (b): shortest diff, n=1 behavior and layout byte-for-
byte unchanged (existing tests prove it), aggregation is a pure helper.
(c) breaks existing consumers/README for no benefit; (a) mixes two layouts
inside one function.

## D5. Trials run sequentially
No parallelism knob. One omnigent server, unknown concurrency headroom,
and live runs are long anyway. Parallel trials can be a later issue if
wall-clock matters.

## D6. Trial failure = fail fast
A raising trial propagates (same as run_case today). Completed trials'
artifacts are already on disk, so nothing is lost; a silently partial
aggregate would be worse than a loud failure.

## D7. Aggregation rule for categorical verdicts
Verdicts are categorical (a|b|tie|unknown) so mean/median (issue's stale
wording) don't apply. Rule: count each verdict; aggregate winner = strict
plurality among {a, b}; if the a-count equals the b-count, aggregate =
"tie". "tie" and "unknown" trial verdicts appear in the counts table but
never win the plurality themselves. Spread is surfaced as the counts dict
plus the per-trial table (duplicate #10's requested shape).

## D8. Uniform run_case_n return shape (spec review 1, objection 2)
`run_case_n` returns `{run_root, trials, aggregate}` for every n >= 1
(n=1 still delegates to run_case for execution and keeps the flat
layout). `main()` always goes through `run_case_n`; the printed payload
is `trials[0]` (n=1, byte-identical stdout to today) or `aggregate`
(n>1). Removes the mode-dependent KeyError the reviewer found. Arg
parsing extracted to `_parse_args(argv=None)` so the flag is testable.

## D9. Phase-8 mechanical fix: fakes vs flowbench grace-poll (issue #18)
Mid-pipeline, flowbench 9c93ec5 added a 60s artifact grace-poll to
run_agent_session; the offline fakes return artifact_path()=None, so every
fake-driven test started burning 60s/flow — reproduced on plain
origin/main, i.e. a base breakage, not this branch. Mechanical fix within
allowed files: _FakeDriver.artifact_path() truthfully returns "plan.md"
(its plan exists as artifact_text); _MissingPlanDriver overrides back to
None (a crashed flow SHOULD pay the grace — one deliberately slow test).
This edits a pre-existing test helper (AC4 said tests append-only) — the
constraint predates the upstream change; the gate-3 re-reviewer judges it.
Proper fix (thread artifact_grace_s through run_case and/or flowbench
knob + CI story) filed as #18, priority:high.
