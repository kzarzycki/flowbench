# flowbench #105, part 1 — omnigent private-API inventory (docs-only)

**Problem.** `src/flowbench/driver/omnigent.py` reaches into omnigent's private surface
(`sessions._http`, `sessions._base`, the `omnigent_client._sessions_chat` module path,
`omnigent.host.daemon_launch`). S02.5 must migrate each to a public call or file upstream for
one — but the driver is owned by S02.3 right now, so this part is read-only on the engine.

**Chosen fix.** A single design doc, `docs/design/omnigent-api-inventory.md`, listing every
reach-in with file:line, why it exists, the public equivalent in the pinned client (0.2.0) and
at upstream HEAD, and the migration verdict (now / blocked on upstream / keep). Gaps with no
public equivalent get an upstream issue draft in `items/upstream/` (scenarios repo); filing is
gated on the owner. The same inventory is posted as a comment on #105 so part 2 starts from it.

**Why safe.** No code changes; the doc states what the code does today and is checked against
the installed package and the server checkout. The `terminal_launch_args` trap is stated as a
blocker, not a suggestion to simplify.

**Acceptance (checkable from the diff).**
- A1 The engine PR touches only `docs/`.
- A2 Every hit of `rg '\._[a-z]' src/flowbench/driver/omnigent.py` that resolves to an
  omnigent attribute (not `self.`) appears in the inventory table with its line number.
- A3 Every row carries a verdict from {migrate-now, blocked-upstream, keep}; a
  `blocked-upstream` row links a draft in `items/upstream/`.
- A4 The doc names the pinned versions (client + server package 0.2.0) and the server actually
  running (editable checkout, 0.13.0.dev0), because the answer differs between them.
