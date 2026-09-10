No standards or spec objections.

`9fc7eaa..f5a88eb` contains only the three requested fixes:

- Both SDK label reads have the 60-second timeout; bounded-context test added.
- `git ls-files state.lock` is empty.
- Comments/helpers/docstrings use corrected “≥400 / non-Session” wording.

SDK labels mapping verified. Existing assertions preserved; A1–A3 pass. R1 POST, R3 helpers, watchdog GET, and concurrent implementation regions remain untouched.

Verification: **300 passed, 1 skipped**; Ruff and diff checks exit **0**. Reverting the import in memory makes the start test fail, exit **1**, as required. Worktree clean. A4 excluded.

APPROVE
