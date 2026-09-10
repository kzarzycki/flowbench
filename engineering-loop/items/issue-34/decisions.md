# issue-34 decisions

- D1 **N-way single judging** — user-chosen (AskUserQuestion, 2026-07-04) over
  round-robin pairs and pick-2-per-run. Generalize to N>=2, not hardcode 3.
- D2 **Codex model** — user chose "cheapest gpt tier"; live probe showed every
  mini id rejected on the ChatGPT account (gpt-5.5-mini, gpt-5.5-codex-mini,
  gpt-5.1-codex-mini, codex-mini-latest → 400 "not supported"). Cheapest usable
  = gpt-5.5 + reasoning_effort: low (first-class in OmnigentDriver,
  driver.py:239,399). Recorded on the issue (comment 2026-07-04).
- D3 **plain flow shape** — restored from pre-#33 flows.yaml (git show
  f1ebb65^): claude-native, haiku, medium, skills: none, no skill_dirs, direct
  "Plan this feature directly" prepend, same append as the others.
- D4 **Position bias for N flows** — rotate flow order per trial: trial k runs
  flows rotated left by (k-1) % N. For N=2 this reproduces today's even-trial
  swap exactly. run_case's `swap_ab: bool` becomes `rotation: int = 0`.
- D5 **Canonical aggregation keys = flow NAMES**, not letters. Today's
  canonical() letter-mapping gymnastics exist only because trials disagree on
  which flow is "a". Keying counts/score_means by flow name removes the
  remapping entirely and reads better in run.json. Letters remain only inside
  a single trial (judge-facing labels).
- D6 **run.json schema break** — trial meta: A/B fields replaced by
  `labels: {"A": name, ...}` (order = judge labels); `winner` stays the judge's
  letter (or tie/unknown), `winner_flow` stays the name. Aggregate meta: A/B
  replaced by `flows: [names]` (canonical order = flows.yaml), counts +
  score_means keyed by flow name. Only consumer is report.py (updated in the
  same change); fixtures/tests updated. No external consumers (grepped).
- D7 **judge.md** — rewritten for N plans: intro "two software implementation
  plans" → "the competing software implementation plans, labeled A, B, ...";
  tail block = one SCORES line per label + WINNER: <letter|tie> + one
  assessment line per label. parse_scores label regex widens [AB] → [A-Z].
  Criteria 1-5 unchanged (incl. #14's conflict handling).
- D8 **Judge input size** — 3 haiku-scale transcripts+plans fit a judge context
  comfortably (todo-011 pairs were far under limits); no chunking machinery.
- D9 **Ties in N-way plurality** — aggregate winner = strict plurality of flow
  wins; any equal top count → "tie" (generalizes today's a-vs-b rule).
