# P02 — Reporting & scenario-author DX (proposal, milestone M9)

Not yet an epic spec. Promote to `epics/` before starting. Everything here is a pure
reader over run dirs — nothing wraps execution (locked seam).

## Reporting

1. **Per-run report v2.** Today's `report.md` (swe_planning) is serviceable; v2 adds the
   judge's per-criterion scores as a table, per-flow timing/turn/token stats, and links to
   `conversation_url` for every session (flow, sim, judge) so a human can jump into any
   live session from the report.
2. **Aggregate report v2.** Winner counts + score means ± spread (from P01), trial table
   with links, and the position-bias view.
3. **HTML export.** Same content, one self-contained HTML file per run for sharing outside
   the terminal. Markdown stays the source; HTML is a renderer.
4. **Optional Inspect exporter.** If browsing in `inspect view` is ever actually wanted:
   a ~100-line adapter that converts a run dir into an Inspect log file. Build only when
   pulled by a real consumer — this was the explicit framework-decision outcome.

## Scenario-author DX

1. **Quickstart + template case.** `docs/design/scenario-authoring.md` (engine-owned after
   E03) gains a copy-paste template: the five case files with commented placeholders and a
   minimal `flows.yaml` of two flows.
2. **`flowbench new-case <scenario> <name>`** — scaffolds the template. Nice-to-have; only
   worth it once a second author exists (this is also a framework reconsider-trigger —
   note it in the ledger when it happens).
3. **Fixture-capture helper.** Offline scorer tests need canned sessions; a small tool
   that snapshots a live run's `session.json` into a scrubbed fixture would stop authors
   from hand-writing item lists (todo_app's `fixtures/sessions.py` is hand-written today).

## Non-goals

Dashboards, databases, services, run registries — plain files until a reconsider-trigger
fires (locked decision).
