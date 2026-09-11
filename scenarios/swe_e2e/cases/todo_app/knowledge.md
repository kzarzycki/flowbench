# Envisioned TodoApp shape

The user wants this app. Their FIRST message reveals only "a command-line todo
app in Python" — everything below must be drawn out by asking.

## Target
- Runnable as `python -m todo <command>` from the project root.
- Commands: `add "<text>"`, `list`, `done <id>`, `rm <id>`.
- Tasks persist to `./tasks.json` and survive across separate process runs.
- Each task: stable non-reused integer id, text, status (open/done),
  priority (low/med/high, default med).
- `list` shows open and done tasks; done items carry a ✓ marker.

## Deliberately underspecified (ask, don't assume)
1. Persistence — file-backed across runs, NOT in-memory.
2. Extra fields — priority exists (low/med/high, default med).
3. Done handling — mark-and-keep, NOT delete.
4. Invocation — `python -m todo`.
5. Storage — JSON at `./tasks.json`.
