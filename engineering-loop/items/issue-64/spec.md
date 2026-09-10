# S02.1 — `flowbench/types.py`

Issue: flowbench #64. Epic: `docs/roadmap/epics/E02-runtime-robustness.md`, story S02.1.
Size: M (one new module + a mechanical sweep across 5 engine modules and 5 test modules).

## Problem

A turn's outcome is a bare `str`. `TurnResult.status` is documented only in a comment
(`driver.py:40`), and the vocabulary is compared by literal in five places
(`driver.py`, `runner/loop.py`, `model.py`, `watch.py`, `testing.py`) plus the tests.
A typo in a comparison is silent, an exhaustive check is impossible, and the set has
already drifted twice since the comment was written (`stalled` in #57, and `running`,
which `_wait_idle` can return via `return st or "timeout"` when the per-turn cap fires
mid-run). `run_agent_session`'s `user_model` parameter has no declared interface at all —
the only contract is "has `async generate(prompt)` returning something with `.completion`",
stated in prose in `model.py`'s docstring and in the loop's parameter name.

## Chosen fix

New module `src/flowbench/types.py`, the engine's vocabulary of turn outcomes:

- `class TurnStatus(StrEnum)` with `IDLE`, `RUNNING`, `FAILED`, `TIMEOUT`, `STALLED`.
  `StrEnum` keeps `status == "idle"` and `json.dumps` working unchanged during and after
  the transition — the members ARE the strings that already go into `session.json` and
  `run.json`.
- `TurnResult` moves here verbatim, with `status: TurnStatus | str` and per-field
  docstrings. The union is deliberate and narrow: `_wait_idle` returns the omnigent
  session status verbatim, and while that vocabulary is documented closed at three values
  (`omnigent_client/_sessions.py:126-127`: "One of `idle`, `running`, or `failed`"), an
  undocumented value must keep passing through into `exit_status` as a diagnostic rather
  than raising `ValueError` and killing a live run. Every documented value is a
  `TurnStatus`; the docstring says so.
- `class UserModel(Protocol)` — `async def generate(self, prompt: str) -> Completion`,
  where `Completion` is a Protocol with a `completion: str` attribute. Used to type
  `run_agent_session(user_model=...)` and to declare what `SessionModel` implements.

`flowbench.runner.driver` re-exports `TurnResult` (and now `TurnStatus`) so existing
imports — engine, tests, and any downstream — keep working. No module in `src/flowbench`
defines `__all__` today and this story does not introduce that convention; the re-export
is a plain `from flowbench.types import TurnResult, TurnStatus` with a comment naming the
one-release policy. Every string-literal status comparison and construction in `src/` and
`tests/` is replaced with the enum member — **including the status literals inside
comments and docstrings** (`driver.py:40`, `driver.py:169`, `driver.py:176`), which AC2's
grep does not exempt; those comments are rewritten to name the `TurnStatus` members.

No behavior change: `StrEnum` members compare equal to, hash equal to, and serialize as
the same strings the code emits today.

## Why safe

- `StrEnum` is a `str` subclass: `"idle" == TurnStatus.IDLE`, `f"{TurnStatus.IDLE}"` is
  `"idle"`, `json.dumps(TurnStatus.IDLE)` is `"idle"`. Nothing written to disk changes,
  so scorecards, `session.json` and the report reader are untouched.
- The statuses the driver *produces* come from `_wait_idle`, which returns the omnigent
  session status verbatim (`idle`/`running`/`failed`) or a flowbench-derived value
  (`timeout`, `stalled`). Enumerating all five (not the epic's three) preserves the
  existing behavior instead of narrowing it.
- The sweep is comparisons, constructions and the comments that name the literals; no
  control flow moves.
- V1 + V2 both run; the offline suite covers every touched path (188 tests today).

## Acceptance criteria

1. `src/flowbench/types.py` exists and defines `TurnStatus` (a `StrEnum` with exactly the
   members `IDLE`, `RUNNING`, `FAILED`, `TIMEOUT`, `STALLED` valued `"idle"`, `"running"`,
   `"failed"`, `"timeout"`, `"stalled"`), `TurnResult`, `UserModel`, `Completion`.
2. `rg -n '"idle"|"failed"|"timeout"|"stalled"|"running"' src/` matches only inside
   `src/flowbench/types.py`.
3. `from flowbench.runner.driver import TurnResult, TurnStatus` works, and
   `flowbench.runner.driver.TurnResult is flowbench.types.TurnResult`.
4. A test asserts the str-compat contract: for every member, `member == member.value`,
   `json.dumps` of a dict containing it round-trips to the plain string, and
   `TurnResult(TurnStatus.IDLE, "", False).status == "idle"`.
5. A test asserts `isinstance(x, UserModel)` for both simulator-side implementations —
   `flowbench.model.SessionModel` and the offline double `flowbench.testing.StubSim` —
   against a `runtime_checkable` `UserModel` Protocol. That `isinstance` check is the one
   mechanism; no static-assignment alternative. `AgentDriver` stays an ABC and
   `ScriptedDriver` stays duck-typed — turning the driver into a Protocol is S02.2 work
   and is out of scope here.
6. `run_agent_session`'s `user_model` parameter is annotated `UserModel`, and
   `SessionModel`'s class docstring names `flowbench.types.UserModel`. (Conformance
   itself is proved by AC5; this criterion is about the declaration being findable.)
7. V1 green (`uv run pytest -q`) with no test weakened or removed; test count ≥ 188.
8. V2 green (`cd $SCENARIOS && uv run pytest -q`).
9. `uv run ruff check` and `uv run ruff format --check` clean.
10. A test feeds `_wait_idle` a server status outside the documented vocabulary and
    asserts it reaches `TurnResult.status` unchanged — no exception, no relabelling. This
    locks the passthrough that the `TurnStatus | str` annotation exists to protect; it
    fails if someone later "tightens" the boundary to `TurnStatus(st)`.

## Out of scope

Driver split (S02.2), retry-policy changes (S02.3), the `artifact_name` removal (S02.4).
`TurnResult.stall_reason` stays a `str | None` — a `StallReason` enum is S02.2/S02.6 work
and the epic does not ask for it here.
