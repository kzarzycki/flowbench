# The run schema

`run.json` and `scorecard.json` are read back, not just written: `rescore_run` rewrites a
manifest in place, and every report renders run dirs older than the code rendering them. So
both documents carry `schema_version`, and `run.json` also carries `kind`, the discriminator
that says which of its two shapes it is.

`src/flowbench/schema.py` is the executable copy of this doc: `SCHEMA_VERSION`, `RunKind`,
`FlowOutcome`, `validate_run_meta`, `require_version`, `flow_outcome`.

What writes these files is [`runner.md`](runner.md); what a case may put in a scorecard is
[`case.md`](case.md).

## The two shapes

**`kind: "trial"`** — one run of every flow, written by `run_case`.

| Field | Required | Holds |
| --- | --- | --- |
| `schema_version` | yes | `1` |
| `kind` | yes | `"trial"` |
| `run_id` | yes | the run-dir segment |
| `case` | yes | `case.name` |
| `deliverable` | yes | what proves delivery, `null` when the case declares none |
| `workspace` | yes | the declared starting workspace, `null` when no flow ran |
| `flows` | yes | flow names, in the rotated order this trial ran them |
| `labels` | yes | `{"A": flow, "B": flow, …}` — the judge-facing labels |
| `rotation` | yes | the left-rotation this trial applied |
| `winner` | yes | the judge's label, `null` without a judge |
| `winner_flow` | yes | that label's flow name, `null` without a judge |
| `scores` | yes | per-label judge scores |
| `flow_stats` | yes | per-flow map: `exit_status`, `turns`, `duration_s`, `seed_commit`, `outcome`, optional `score_error` |
| `models` | yes | per-flow model |
| `reasoning_effort` | yes | per-flow effort |
| `outcomes` | yes | per-flow `FlowOutcome`, the mirror of `flow_stats[<flow>].outcome` |
| `artifact_missing` | no | flows that delivered nothing — written only when the case declares a deliverable |

A required field may hold `null`; a manifest *missing* it is invalid, because no writer can
produce one. `validate_run_meta` enforces exactly that distinction.

**`kind: "aggregate"`** — the roll-up over `n > 1` trials, written by `run_case_n`. Required:
`schema_version`, `kind`, `run_id`, `case`, `deliverable`, `n`, `flows`, `trials`, `counts`,
`winner`, `score_means`. It has no `flow_stats`, no `labels` and no `workspace` — those are
per-trial facts, and each `trial-XX/run.json` is a trial manifest of its own.

**`scorecard.json`** carries `schema_version: 1` and nothing else the engine imposes; the rest
is whatever `case.score` returned. The engine stamps the key when it writes the card — in
`run_case` and in `rescore_run` — so a case never has to know the version exists. A card that
returns its own `schema_version` keeps that value.

## Reader rules

- A reader ignores unknown fields. Adding a key is not a version bump.
- A missing `schema_version` is version 0. That is every run dir written before this schema,
  and v0 stays readable: readers render it and say so once, in a visible note (`schema v0`).
- A version this reader does not know is an error it states, not a crash mid-render. The report
  renderers raise `SchemaVersionError` naming the file and both versions; `compare` treats an
  unknown-version manifest as absent — no `_outcome_` row, the metric table exactly as it
  renders otherwise — and says `unsupported schema_version <n>` in one line above the table, and
  renders an unknown-version scorecard as a FAILED column. Forward compatibility is not claimed,
  so it is said out loud.
- A v0 `run.json` has no `kind`: readers fall back to the key-presence guess (`trials` →
  aggregate, `flow_stats` → trial) for v0 only, so the guess survives exactly as long as the old
  files do.
- Removing or retyping a required field is what bumps the version to 2.

## The outcome vocabulary

`FlowOutcome` says how one flow ended, in precedence order — first match wins:

| value | means | computed from |
| --- | --- | --- |
| `no_start` | the flow could not start — no turn ever ran | `turns == 0` and `exit_status` is not `idle` |
| `no_deliverable` | ran, delivered nothing the case declared | the case declares a deliverable and `artifact_exists` is false |
| `scorer_failed` | ran and delivered; scoring raised | `flow_stats[<flow>].score_error` present |
| `degenerate` | ran, delivered, scored — and the comparison cannot rank it | the flow's scorecard says `degenerate: true` |
| `ok` | ran cleanly | everything else |

`no_start` deliberately does not consult `artifact_missing`: a flow that never started is
`no_start` whether or not the case declares a deliverable, which is the distinction a run whose
harness never came up could not otherwise make.

`degenerate` is the only value the engine cannot compute — whether a column is comparable is
case knowledge — so it is a one-key contract: a `score` that returns `degenerate: true` in its
card gets the outcome, and a case that never sets the key never sees the value.

`rescore_run` recomputes the outcome and its mirror whenever it rewrites a card: a rescore can
turn `scorer_failed` into `ok` or `degenerate`, and a stale outcome beside a fresh card is the
bug the version stamp exists to prevent.

### What each reader does per value

| outcome | `compare` renders | `run_report` flow table | gate 5 clean criterion |
| --- | --- | --- | --- |
| `no_start` | `_outcome_` cell `no_start`; the flow's metric cells stay as they are | `outcome` cell `no_start` | **not clean, not actionable as code** — the flow never ran, so it is an environment fact (the harness, quota, the host) |
| `no_deliverable` | `_outcome_` cell `no_deliverable` | same | **not clean** — a real failure of the run |
| `scorer_failed` | `_outcome_` cell `scorer_failed`, alongside the FAILED-column banner | same | **not clean** — a real failure |
| `degenerate` | `_outcome_` cell `degenerate` **and** the line `comparison not rankable: <flows> declared degenerate` above the table; every metric row still renders its real values | same | **engine half clean, comparison half void**: the run proves the engine drove the case end to end and ranks nothing. Not a result, and not an engine regression either |
| `ok` | `_outcome_` cell `ok` | same | clean |

`compare` reads `run.json` for `outcomes` and keeps its isolation rule: a missing, unreadable or
unknown-version manifest means no `_outcome_` row, never an abort, and the metric table renders
as it otherwise would.
