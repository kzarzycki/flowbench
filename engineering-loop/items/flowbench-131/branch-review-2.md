reviewer: claude-code:subagent gate3-131 (Fable, fresh context; same vendor as implementer)

APPROVE

Verified on `406d4fd`: the item read is gated on `updated_at` change (`src/flowbench/watch.py:120-122`) and `test_run_watch_reads_items_only_when_the_session_moved` fails without it (two ticks, one read; a moved session reads again). All 13 watcher tests pass with `urllib.request.urlopen` forbidden. Full suite 361 passed, 1 skipped; ruff check and format clean. The commit touches only `watch.py`, `tests/test_watch.py` and the onboarding line wrap; no other files changed since the first review, no CI/gate/`.claude/` touches.

One non-blocking note: `_session_read_at` is recorded before the read, so a transient items-read failure at the tick where the banner landed skips that session's `QUOTA` line until its `updated_at` moves again. Defensible trade-off (retrying on "" would reintroduce the per-tick read for ordinary replies); the driver's own `[flowbench] quota:` line still fires.
