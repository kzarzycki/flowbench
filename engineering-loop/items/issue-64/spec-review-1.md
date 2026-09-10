Gate 1, attempt 1 — verdict REVISE (Claude reviewer, opus, fresh context; codex/omnigent
not dispatched from this session).

Held: scope matches S02.1 with no invention/loss; size proportional; all codebase claims
verified true (five live statuses incl. `running` via `driver.py:463`, StrEnum vs
`(str, Enum)` formatting, downstream imports, 188 tests); every decisions.md entry
derivable from issue + code.

Objections:
1. (blocking) AC5 named `ScriptedDriver` (a driver stub) as a `UserModel` double and
   invoked a non-existent "driver protocol" — `AgentDriver` is an ABC and `ScriptedDriver`
   is duck-typed; the `UserModel` double is `StubSim`. The "or a static assignment check"
   escape hatch is unfalsifiable for an unattended implementer.
2. "the driver's own `__all__` grows accordingly" presupposes an `__all__` that no module
   in `src/flowbench` has.
3. AC2 contradicts "Why safe": three of the current matches are comments
   (`driver.py:40,169,176`), so the sweep must rewrite comment text too.
Nit: decisions.md cited `model.py:66` for `_Out`; it is at 71-72.

All four fixed in spec.md/decisions.md/plan.md.
