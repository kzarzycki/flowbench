# issue-34: recover claude plain flow — todo_app runs 3 flows, judged N-way

**Problem.** PR #33 rebuilt todo_app as a 2-flow codex-vs-claude matchup and
dropped the plain (no-skills) flow; `run_case` hard-rejects anything but
exactly 2 flows (run.py:73). Issue #34 wants 3 flows — claude superpowers,
codex superpowers, claude plain — on the cheapest models (smoke test).
User-confirmed design: ONE judging pass grades all N plans (not round-robin).

**Change.**

1. `helpers.py`
   - `build_judge_prompt(judge_md, entries)` where entries = ordered list of
     `(label, transcript, plan)`; emits `--- CONVERSATION <L> ---` /
     `--- PLAN <L> ---` blocks per entry (replaces plan_a/plan_b params).
   - `parse_scores`: label regex `[AB]` → `[A-Z]`; returns a dict keyed by
     every label present (lowercased), e.g. `{"a": {...}, "b": {...}, "c": {...}}`.
   - `parse_verdict`: unchanged winner semantics (last `WINNER:` line, now any
     single letter or tie); per-label assessment lines for all labels present.
   - `aggregate_verdicts(winners)` takes flow NAMES (or "tie"/"unknown"):
     counts keyed by name + tie + unknown; winner = strict plurality name,
     equal top → "tie".
   - `aggregate_scores` keyed by flow name (callers pass name-keyed dicts).
2. `run.py`
   - `run_case`: accept N>=2 flows (ValueError below 2); labels = A, B, C…
     by (possibly rotated) order; one judge call over all entries; meta drops
     `A`/`B`/`swapped_ab` for `labels: {letter: flow_name}` + `rotation`;
     `winner_flow` maps the judge letter through labels.
   - `swap_ab: bool` param → `rotation: int = 0` (rotate flow list left);
     `run_case_n` trial k uses rotation `(k-1) % N` (N=2 ≡ today's swap).
   - `run_case_n` aggregation: canonicalize per trial via `labels` (letter →
     name); aggregate meta gets `flows: [names]` (flows.yaml order), counts +
     `score_means` keyed by flow name; `trials[]` rows keep winner_flow.
3. `cases/todo_app/judge.md` — N-plan wording ("plans labeled A, B, …"), tail:
   one `SCORES <L>: fulfillment=… conflict=<0-5>` line per plan, `WINNER:
   <letter|tie>`, one `<L>: <one-line assessment>` per plan. Criteria 1-5
   unchanged.
4. `cases/todo_app/flows.yaml` — 3 flows in judge order:
   claude (claude-native, haiku, medium, vendored skill_dirs),
   codex (codex-native, gpt-5.5, reasoning_effort low, vendored skill_dirs),
   plain (claude-native, haiku, medium, skills none, NO skill_dirs, pre-#33
   direct-planning prepend, same append).
5. `report.py` — per-run report renders one section/column per flow from
   `labels`; aggregate report tables keyed by flow name (banner: plurality
   winner "wins x–y–z (n=…)" or Tie).
6. Tests updated for the new shapes; new tests cover 3-flow run_case, rotation
   canonicalization, N-way plurality (incl. equal-top tie), 3-label parsing.

**Out of scope.** Round-robin mode; per-pair reports; changing criteria; other
cases (feature_flag_service untouched); flowbench driver (already supports
codex-native + reasoning_effort).

## Acceptance criteria

- AC1 `uv run python -m scenarios.swe_planning.run --case todo_app` path (via
  offline fakes in tests) runs THREE flows and produces one judge verdict; a
  2-flow flows.yaml still works (N-way is a generalization, not a fork).
- AC2 flows.yaml defines exactly the 3 flows above; plain has `skills: none`,
  no `skill_dirs`, and no /brainstorming prepend; codex has model gpt-5.5 +
  `reasoning_effort: low`; both claude flows `model: haiku`.
- AC3 `parse_scores` returns per-label dicts for >=3 SCORES lines;
  `aggregate_verdicts` over flow names picks strict-plurality winner and
  returns "tie" on equal top counts (unit-tested).
- AC4 Rotation: with n=3 trials and 3 flows, trial rotations are 0,1,2 and the
  aggregate counts are keyed by flow name regardless of per-trial label
  positions (unit-tested with fakes).
- AC5 run.json shapes: trial meta has `labels` + `winner_flow`, no `A`/`B`/
  `swapped_ab`; aggregate meta has `flows`, name-keyed `counts`/`score_means`,
  no `A`/`B`. report.py renders both without KeyError (tested).
- AC6 judge.md contains one SCORES line per label A/B/C with `conflict=<0-5>`
  and the WINNER line; existing judge-content guard tests updated and green.
- AC7 Full offline suite green (baseline 116 passed / 1 skipped, minus tests
  rewritten for the new schema, plus the new ones).
- AC8 Diff confined to scenarios/swe_planning/{run.py,helpers.py,report.py,
  cases/todo_app/{flows.yaml,judge.md}} + tests + README flow docs if stale.
