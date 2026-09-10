# flowbench #59 — artifact vocabulary in run.json + `--rescore`

Size: **M**. Engine-only code (`flowbench` repo); this item dir + ledger ship in the
paired scenarios PR.

## Problem

Two things, one root each.

**(1) Plan vocabulary.** `run_case` writes `run.json` with `plans_missing` and
`flow_stats[<flow>].plan_lines`, and writes `<flow>/plan.md` unconditionally. Those
names assume every case's deliverable is a plan. `coding_workflow/todo_app`'s
deliverable is a working CLI app, judged black-box by `acceptance.py`; it declares
`artifact_name="tasks.json"` only because the driver's artifact probe demands a name.
`tasks.json` is the app's *runtime state file*, not a deliverable: it does not exist at
capture time (the acceptance harness creates it later by exercising the app), so
`todo-app-004` reads `plans_missing=[baseline, superpowers]`, `plan_lines=0` for two
flows that both scored acceptance 1.0, and leaves an empty `plan.md` in each flow dir.
A reader — and `watch.py`'s `TRIAL DONE ... missing=[...]` line, and loop.md's
"clean = no plans_missing" — reads that as total failure.

**(2) A dead `score_flow` is unrepairable from the CLI.** `run_case` isolates a
`score_flow` exception into `{"error": ...}` in the scorecard and `score_error` in
`flow_stats` — correct (one bad flow never aborts a run) but terminal: the fix is a
hand-written Python snippet (done at 06:53 on 2026-09-09 for `todo-app-004`, whose
superpowers judge session died with `no online host with claude-native configured`
because the lid closed one minute after the deadline). Everything the scorer needs is
already on disk (`<flow>/session.json`, the case's `flows.yaml`), so re-running it
should be a flag, not an archaeology exercise.

## Chosen fix

**(1)** The case declares whether it has an artifact, and the vocabulary follows the
declaration:

- `run_case(..., artifact_name: str | None = "plan.md")`, threaded through
  `run_case_n`. `None` = *this case declares no artifact*.
- `artifact_name` set → `run.json` carries `artifact_missing: [flow, ...]` and
  `flow_stats[f].artifact_lines`; `<flow>/plan.md` still written (it is the HTML
  report's input, and for swe_planning the artifact *is* `plan.md`).
- `artifact_name is None` → neither key appears anywhere in `run.json`, no `plan.md`
  is written, and the artifact grace-poll is skipped (`artifact_grace_s` forced to 0 —
  today todo_app pays 60 s per flow waiting for a file nobody will write).
- `omni_factories(scenario, *, artifact_name: str | None = "plan.md", ...)` accepts the
  same `None` and maps it to the driver's existing `"__none__"` sentinel, so a scenario
  CLI declares the artifact exactly once and passes that one value to both.
- Readers: `watch.py` prints `missing=` from `artifact_missing` and drops the segment
  when the key is absent; `report/run_report.py` reads `artifact_lines` (its existing
  `or len(plan.splitlines())` fallback keeps pre-rename run dirs rendering).
  `report/compare.py` reads only `scorecard.json` — nothing to change, and the issue's
  "compare must not treat them as failure" already holds.
- `coding_workflow/run.py` declares `ARTIFACT_NAME = None`.
- `run_case` rejects the one combination the report cannot render: `artifact_name is
  None` together with a case that carries `judge.md` (`flow_card` reads `<flow>/plan.md`
  unguarded, `report/run_report.py:82`) — a clear `ValueError`, not a latent
  `FileNotFoundError`.
- Docs this change falsifies are updated with it: `CLAUDE.md:47` and
  `docs/design/runner.md:93-95` (the mandated pre-read for `src/flowbench/runner/`) both
  document `omni_factories(..., artifact_name="plan.md", ...)` and "todo_app binds
  `artifact_name="tasks.json"`".
- `loop.md:347` in the scenarios repo — Phase 9.5's "Clean = ... no plans_missing" — is
  an executing procedure, not prose: after the rename it matches nothing and the live
  gate passes vacuously. The paired scenarios PR syncs that one clause to
  `artifact_missing` (owner approved the edit to their file, 2026-09-09). LOG.md history
  entries stay as written.

No back-compat shim for `plans_missing`/`plan_lines`: run dirs are disposable outputs,
the only in-repo readers are the two above, and the scenarios repo has no code reader
(checked `git grep` on `origin/main`: hits are ledger/plan prose only).

**(2)** `flowbench.run.rescore_run(case_dir, run_root, *, score_flow) -> dict` — an
engine helper, scenario-agnostic:
- for every directory under `run_root` that holds a `run.json` with `flow_stats`
  (the flat `n=1` layout and each `trial-XX/` of an `n>1` run),
- for each flow in that `run.json`'s `flows` that still has a `<flow>/session.json`:
  look the flow dict up by name in the case's `flows.yaml`, `await score_flow(flow,
  flow_dir, session)`, rewrite `<flow>/scorecard.json`, and set or clear
  `flow_stats[flow].score_error` accordingly; rewrite `run.json`.
- A scorer raising is isolated exactly as in `run_case`: the card becomes
  `{"error": ...}`, `score_error` is set, the other flows still rescore. A flow named in
  `run.json` but absent from the case's current `flows.yaml` takes the same path (the
  lookup sits inside the guard) and is recorded as a `KeyError` rather than scored
  against a config that no longer matches the run.
- Returns `{flow_name: "ok" | "<error>"}` per rescored flow dir, keyed
  `"<trial>/<flow>"` when trials are present.

`scenarios/coding_workflow/run.py` gains `--rescore <run_id>` (mutually exclusive with
a normal run): resolves `runs_root/<run_id>`, calls `rescore_run` with the same
`score_flow` partial the live path uses, prints the returned map. `--runs-root` still
applies.

## Why it's safe

- swe_planning keeps its defaults (`artifact_name="plan.md"`) — the only change to its
  output is two renamed keys, both read in this repo and both updated here.
- `--rescore` re-runs whatever the scenario's `score_flow` does. For `todo_app` that is
  not free and not read-only: `score_todo_app` re-executes the produced app black-box
  (`acceptance.py`, which rewrites the flow dir's `tasks.json` — the very mutation
  behind this issue), rewrites `<flow>/acceptance.json`, and spawns a live omnigent
  grader session (`make_grader_omni`), costing subscription quota. What rescore is
  guaranteed NOT to do: re-drive a flow, or write `session.json` / `transcript.md`.
- Every failure mode of `score_flow` is already handled by the same isolation the live
  path uses.

## Acceptance criteria (each checkable from the diff/tests alone)

1. `run_case` on a case with `artifact_name="plan.md"` (default) writes `run.json`
   containing `artifact_missing` and `flow_stats[f]["artifact_lines"]`, and containing
   neither `plans_missing` nor `plan_lines`.
2. `run_case(..., artifact_name=None)` writes a `run.json` whose serialized text
   contains none of `artifact_missing`, `artifact_lines`, `plans_missing`,
   `plan_lines`; no `<flow>/plan.md` is created; `session.json`, `transcript.md` and
   `scorecard.json` are still written.
3. `run_case(..., artifact_name=None, artifact_grace_s=30.0)` forwards
   `artifact_grace_s=0.0` to `run_agent_session` for every flow (asserted on the
   forwarded kwargs, not on wall-clock), while the same call with the default
   `artifact_name` forwards `30.0`.
4. `run_case_n` forwards `artifact_name` to `run_case` for both `n=1` and `n>1`.
5. `omni_factories("x", artifact_name=None)[0](flow, dir).artifact_name == "__none__"`;
   the default call still yields `"plan.md"`.
6. `RunWatch` prints `TRIAL DONE: trial-01 winner=<w> missing=[...]` from
   `artifact_missing`, and prints the line without any `missing=` segment when the
   trial's `run.json` has no `artifact_missing` key.
7. `flow_card` reads `artifact_lines` from `flow_stats`.
8. `rescore_run` over a synthetic flat run dir: rewrites each flow's
   `scorecard.json` from `<flow>/session.json` + the case's `flows.yaml` entry, clears
   a stale `score_error` from `flow_stats` when the rescore succeeds, and sets it (with
   the card as `{"error": ...}`) when the scorer raises — the sibling flow still
   rescores. Return map matches. A flow present in `run.json` but missing from
   `flows.yaml` is recorded as a `KeyError` error, not scored and not skipped.
9. `rescore_run` over an `n>1` layout rescores every `trial-XX/` and keys its return
   map `"trial-XX/<flow>"`.
10. `rescore_run` skips a flow dir with no `session.json` and leaves its files alone.
11. `scenarios.coding_workflow.run --rescore <id>` parses, resolves
    `runs_root/<id>`, and calls `rescore_run` with `score_flow.func is score_todo_app`
    and the case dir for `--case`; it starts no session (assert via a stubbed
    `rescore_run`).
12. `coding_workflow/run.py` passes `artifact_name=None` to both `omni_factories` and
    `run_case_n`.

12b. `flow_card` over a flow dir with no `plan.md` returns `plan_lines == 0` and empty
    `plan_html` instead of raising.
13. `run_case(..., artifact_name=None)` on a case whose dir contains `judge.md` raises
    `ValueError` naming both, before any session is started.
14. `docs/design/runner.md` and `CLAUDE.md` state the `artifact_name: str | None`
    signature and that todo_app binds `artifact_name=None, git_init=True`; neither file
    still contains the string `artifact_name="tasks.json"`.
15. The paired scenarios PR changes `.claude/loop.md:347` from `no plans_missing` to
    `no artifact_missing`, and changes nothing else in that file.

## Out of scope

- `artifact_name="__none__"` as the driver-level sentinel stays (E02 S02.4 removes the
  artifact probe from the driver).
- `MISSING_PLAN` (judge-facing prose, only reachable on a case that has `judge.md`,
  i.e. one that does have a plan) keeps its name.
- No back-compat reading of the old key names.
