Gate 1, attempt 2 — verdict REVISE (Claude reviewer, opus, fresh context).

All four attempt-1 objections verified fixed, not reworded. Independent re-verification of
the rest held (five live statuses corroborated against `todo-app-001` session.json;
`StrEnum` availability and the `(str, Enum)` f-string trap; literal sites; 188+1 baseline).

Objections:
1. (blocking) plan T2 invented a behavior change the spec forbids: coercing `_wait_idle`'s
   raw server status with a fallback to `TurnStatus.FAILED` plus a stderr note, uncovered
   by any AC. The server vocabulary is documented closed at three values
   (`omnigent_client/_sessions.py:126-127`); today an unknown value passes through to
   `exit_status` intact. Decide the boundary in spec + decisions, not in the plan.
2. AC6's "declares it implements it" is ambiguous between a docstring and Protocol
   subclassing; unfalsifiable as written.
Nit: T2's sweep line-enumeration was incomplete (e.g. `driver.py:443`).

Resolution: decisions.md #7 records the boundary decision — no coercion, no fallback, no
new control flow; `_wait_idle -> TurnStatus | str` and `TurnResult.status: TurnStatus | str`
with the passthrough documented, locked by new AC10 and
`test_undocumented_server_status_passes_through`. AC6 now reads "`SessionModel`'s class
docstring names `flowbench.types.UserModel`". The plan sweeps by AC2 grep rather than a
fixed line list.
