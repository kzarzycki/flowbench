# issue-34 Implementation Plan — N-way judging + 3 todo_app flows

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development, task-by-task.

**Goal:** generalize the swe_planning pipeline from exactly-2 (A/B) to N>=2 flows judged in one pass; restore todo_app's plain flow so the case runs claude-superpowers, codex-superpowers, and claude-plain.

**Architecture:** judge-facing labels A, B, C… exist only inside a single trial; everything cross-trial (counts, score_means, reports) keys by flow NAME. Position bias: trial k rotates the flow list left by (k-1) % N (N=2 ≡ today's even-trial swap).

## Global Constraints

- Diff confined to `scenarios/swe_planning/{run.py,helpers.py,report.py,README.md,cases/todo_app/{flows.yaml,judge.md}}` + `tests/` (spec AC8).
- Suite green after every task. Baseline: 116 passed, 1 skipped.
- Judge criteria 1-5 (incl. `conflict=<0-5>`) unchanged in wording.
- `winner_flow` and `plans_missing` keys survive in trial run.json (watch.py reads them).
- Labels are single letters A-Z (N<=26 accepted, no machinery).
- Worktree `.claude/worktrees/loop+issue-34-three-flows`, branch `loop/issue-34-three-flows`.
- TDD per task: failing tests first, then implementation. Update existing tests in the SAME task that breaks them.

---

### Task 1: N-way core — helpers + run + report (one shape switch)

**Files:** `scenarios/swe_planning/helpers.py`, `scenarios/swe_planning/run.py`, `scenarios/swe_planning/report.py`, `tests/test_swe_planning_helpers.py`, `tests/test_swe_planning_run.py`

(Single task by gate-2 direction: the helper semantics, their run.py call sites, the run.json schema, and its report.py consumers change together — any split leaves the suite red at the boundary. Write ALL failing/updated tests first, then implement across the three modules, then go green.)

Helpers part:

- [ ] `build_judge_prompt(judge_md, entries)` — entries = ordered `list[tuple[str, str, str]]` of (label, transcript, plan). Emits, per entry in order: `--- CONVERSATION <L> (flow <L> with the user) ---` block (skipped when transcript empty) then all `--- PLAN <L> ---` blocks. Same join/newline behavior as today. Old signature removed; update all callers in tests.
- [ ] `_SCORES` regex `([AB])` → `([A-Z])`. `parse_scores` returns a dict with a key per label PRESENT in the text (lowercased) — no pre-seeded a/b; absent labels are absent keys (pin in a test). Callers use `.get`.
- [ ] `parse_verdict` — winner = last `WINNER:` line matching a single letter or tie (widen `_WINNER` from a|b|tie to [a-z]|tie, case-insensitive as today); replace fixed `"a"`/`"b"` assessment keys with `assessments: {label: line}` for every label that has a `<L>: …` tail line. Keep `scores` and `prose` keys.
- [ ] `aggregate_verdicts(winners)` — winners are flow NAMES or "tie"/"unknown". Returns `{"counts": {name…, "tie": int, "unknown": int}, "winner": <name|"tie">}`; winner = strict plurality over names, any equal top count → "tie". tie/unknown never win.
- [ ] `aggregate_scores(score_dicts)` — mean per criterion per KEY over trials; drop the hardcoded ("a","b") loop, iterate the union of keys present. (Callers will pass name-keyed dicts.)
- [ ] Tests: 3-label SCORES parse; absent-label behavior; WINNER: C; plurality incl. equal-top tie and unknown-never-wins; 3-key score means; judge prompt block order for 3 entries.

run.py + report.py part:

- [ ] `run_case`: drop the len!=2 ValueError (keep `< 2`); param `swap_ab: bool` → `rotation: int = 0` (rotate flow list left by rotation % N: `flows = flows[r:] + flows[:r]`). Labels `string.ascii_uppercase[i]` per rotated position. Judge call becomes `run_judge(judge_md, entries, judge_dir)` where entries = [(label, transcript, plan_or_MISSING_PLAN)…] — update the omnigent `run_judge` adapter and fakes accordingly (adapter builds the prompt via `build_judge_prompt`).
- [ ] Trial meta: remove `A`, `B`, `swapped_ab`; add `labels: {letter: flow_name}` (rotated order) and `rotation`. `winner` = judge letter (or tie/unknown); `winner_flow` maps through labels. `flows`, `flow_stats`, `models`, `reasoning_effort`, `plans_missing`, `scores` stay name-or-label-keyed as today (scores stay label-keyed — per-trial).
- [ ] `run_case_n`: trial k uses `rotation=(k-1) % len(flows)`. Canonicalize per trial: letter→name via that trial's `labels` (winner and scores). Aggregate meta: replace `A`/`B` with `flows: [names in flows.yaml order]`; `counts`/`score_means` keyed by flow name; `trials[]` rows `{trial, winner_flow}` (drop the letter). Delete `canonical()`/`_canonical_scores` letter gymnastics.
- [ ] `report.py render_report`: winner name from `labels[meta["winner"].upper()]` (tie/unknown → None); cards for every flow in `labels` order (grid handles 3); footer unchanged in spirit.
- [ ] `report.py render_aggregate_report`: name-keyed counts; banner = plurality winner `🏆 {name} wins {x}–{y}[–{z}] (n=…)` (counts of every flow joined by –, winner's first) or `Tie x–y[–z]`; score-means table = one column per flow name; trial rows unchanged (`winner_flow`).
- [ ] `render_any` dispatch unchanged (`"trials" in meta`).
- [ ] Tests: update every A/B-shape pin; add: 3-flow run_case via fakes (labels, winner_flow mapping); rotation sequence 0,1,2 for n=3/N=3 with name-keyed aggregate invariant to per-trial positions; 2-flow flows.yaml still works end-to-end (AC1); report renders 3-flow trial + aggregate without KeyError.

### Task 2: case content — flows.yaml 3 flows + judge.md N-way

**Files:** `scenarios/swe_planning/cases/todo_app/{flows.yaml,judge.md}`, `tests/test_swe_planning_flows.py`, `scenarios/swe_planning/README.md` (flow docs if stale)

- [ ] flows.yaml, in judge order claude / codex / plain:
  - claude: as today (claude-native, haiku, medium, skills: none, 3 skill_dirs, /brainstorming prepend) — keep the header comment's harness-filter explanation.
  - codex: as today BUT `reasoning_effort: low` added; keeps `model: gpt-5.5`, `skills: [using-superpowers, brainstorming, writing-plans]`, skill_dirs (gate-1 nit 1).
  - plain: restored pre-#33 shape — claude-native, `model: haiku`, `reasoning_effort: medium`, `skills: none`, NO skill_dirs, prepend `Plan this feature directly. Ask me clarifying questions if needed.`, same append as the others.
- [ ] judge.md: "two software implementation plans, A and B" → the competing plans "labeled A, B, …"; body references to "each plan"/"that agent's conversation" stay; tail block becomes one `SCORES <L>: fulfillment=<0-5> discovery=<0-5> design=<0-5> scope=<0-5> conflict=<0-5>` line per label A, B, C, then `WINNER: <A|B|C|tie>`, then one `<L>: <one-line assessment>` per label. Criteria 1-5 text untouched.
- [ ] Update test_swe_planning_flows.py: flow names `["claude", "codex", "plain"]`; per-flow pins (plain: skills none + no skill_dirs; codex: model gpt-5.5 + effort low; claude flows haiku); judge guard `conflict=<0-5>` count becomes 3; WINNER pin stays; existing todo_app contradiction guards untouched.
- [ ] Full suite green; run `uv run python -m scenarios.swe_planning.report --help`-free sanity: `uv run pytest -q`.

## AC traceability

| AC | Task |
|----|------|
| AC1 3-flow run + 2-flow still works | 1 |
| AC2 flows.yaml contents | 2 |
| AC3 parsers/plurality/tie | 1 |
| AC4 rotation + name-keyed invariance | 1 |
| AC5 run.json shapes + reports no KeyError | 1 |
| AC6 judge.md labels + guards | 2 |
| AC7 suite green | 1-2 |
| AC8 diff scope | 1-2 |
