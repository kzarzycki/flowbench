Gate 3, attempt 1 — verdict REVISE (Claude reviewer, opus, fresh context).

Everything on the branch verified good (V1 197+1, V2 loading the worktree, both greps
clean, all ACs mutation-tested, no behavior change, no out-of-scope edits) — but the
branch was 8 commits behind `origin/master` and gate 6 had not been run. Master's #68 had
rewritten `_wait_idle`/`_snapshot`, the exact code this branch sweeps: a non-trivial
conflict, and 3 new literal sites in `driver.py` that would make AC2 fail after any clean
resolution.

Rework: rebased onto c1541c3 (three conflicts, resolutions recorded in gates.md "Gate 6"),
swept the literals master added, dropped the now-dead `TurnResult.child_busy`, re-ran every
gate.
