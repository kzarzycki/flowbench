# flowbench #59 — self-answered questions (loop.md rule 3)

1. **Rename or drop?** The issue offers both. Both, split by declaration: a case with an
   artifact gets `artifact_*`; a case without gets neither key. Derivable from the issue
   text ("Rename ... or drop when the case has no artifact").
2. **How does `run_case` learn the case has no artifact?** Explicit
   `artifact_name: str | None` parameter, not by sniffing the driver's `"__none__"`
   sentinel: the sentinel is scheduled for removal (roadmap S02.4 / E02) and is not
   reachable offline without a driver. Source: `docs/roadmap/epics/E02-runtime-robustness.md:92-96`.
3. **Does todo_app really have no artifact?** Verified in the run dir, not assumed:
   `todo-app-004/baseline/session.json` has `artifact_exists: false` while
   `baseline/tasks.json` exists on disk — the file is written *after* capture by
   `acceptance.py` exercising the app. `tasks.json` is app state, not a deliverable.
4. **Back-compat for `plans_missing`/`plan_lines`?** No. In-repo readers are
   `watch.py` and `report/run_report.py` (both updated); `git grep` on the scenarios
   repo's `origin/main` finds no code reader, only ledger/plan prose. Run dirs are
   disposable outputs under `../flowbench-runs/`, not a published schema.
   `run_report.flow_card`'s existing `or len(plan.splitlines())` fallback keeps old run
   dirs rendering anyway.
5. **Skip the artifact grace-poll when there is no artifact?** Yes — same root cause as
   the issue (a case with no artifact being treated as one that has a missing artifact),
   one line, and it removes a 60 s-per-flow dead wait from every todo_app run. Loop.md
   rule 7 (follow-ups land on the open item) rather than a new ticket.
6. **Is `--rescore` scope invention?** No — the owner scoped it into this issue in the
   ledger: `origin/main:.claude/engineering-loop/LOG.md:1073` ("flowbench #59 (run.json
   plan vocabulary, fold in the `--rescore` CLI from the 004 lesson)"), and the brief
   for this item repeats it. On the issue text alone it would read as invented scope.
6b. **Where does `--rescore` live?** The re-scoring loop is scenario-agnostic (it reads
   `run.json`, `session.json`, `flows.yaml` — all engine artifacts) → engine helper
   `flowbench.run.rescore_run`; the scenario CLI owns only the flag and the
   `score_flow` partial. Same split as `run_case_n` vs `scenarios/*/run.py` today.
7. **Item dir name.** `items/flowbench-59`, not `items/issue-59`: scenarios #59 is a
   different, open issue ("feature_flag_service superpowers flow depends on host
   skills"), and loop.md forbids touching another issue's item dir.
8. **Does the write of `<flow>/plan.md` get renamed to the artifact's name?** No — it is
   the HTML report's input, and the report only renders for a case with `judge.md`,
   whose artifact *is* `plan.md`. That invariant was assumed, not enforced: report
   rendering is gated on `has_judge` (`run.py:166`), independent of `artifact_name`, so
   a future case with `judge.md` and no artifact would hit `FileNotFoundError` in
   `flow_card` (`report/run_report.py:82`). Enforced here as a `ValueError` in
   `run_case` (AC13). Renaming the written file stays report-schema work, not this issue.
9. **Does `loop.md` count as a reader?** Yes — decision 4's "no code reader" is true of
   code but wrong about `loop.md:347`, which is an executing procedure (Phase 9.5's
   clean criterion). Not self-answerable: `loop.md` reserves its own edits for the
   owner, who was asked and approved the one-clause sync (2026-09-09).
10. **Do the engine docs need updating?** Yes, in this item: `CLAUDE.md:47` and
   `docs/design/runner.md:93-95` document the old signature, and `runner.md` is the
   mandated pre-read for `src/flowbench/runner/` changes (`CLAUDE.md:41-42`) — a stale
   line there misleads the next agent (AC14).
