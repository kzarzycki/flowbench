# Plan review 1 — APPROVE (reviewer: fresh-context opus subagent)

Independent criterion→task→test mapping complete for all 7 ACs (5
aggregation edge-case tests, n=3 layout test, n=1 flat-layout regression
guard, parser tests, README/scope inspection items). Code-fit verified
against the real tree: run_case return/meta shape, mkdir(parents=True)
guarantees the aggregate run.json target dir, fakes exist at claimed
lines, README replacement matches byte-for-byte, import extensions
correct, task ordering green after each task.
