# S02.1 implementation plan — `flowbench/types.py` (issue #64)

Engine worktree: `/Users/zarz/dev/agents/flowbench--s021`, branch `loop/s02-1-types` off
`origin/master` (4352a13). Scenarios worktree: `/Users/zarz/dev/xebia/flowbench-scenarios--s021`,
branch `loop/issue-64-types` off `origin/main`. Baseline verified before T1:
**188 passed, 1 skipped**.

## Global constraints (verbatim from spec.md)

- No behavior change: `StrEnum` members compare equal to, hash equal to, and serialize as
  the same strings the code emits today. Nothing written to disk changes.
- `TurnResult` canonical in `types.py`, re-exported from `flowbench.runner.driver`
  (one-release compat policy, same as S02.2's).
- The sweep is comparisons, constructions and the comments that name the literals; no
  control flow moves.
- No test weakened, skipped or removed; test count ≥ 188.
- Out of scope: driver split (S02.2), retry policy (S02.3), `artifact_name` (S02.4),
  a `StallReason` enum.

## Ground-truth literal inventory (definition of done for the sweep)

Verified in the worktree at 4352a13. A task's line list is exact, but the **grep is the
definition of done**, not the list — re-run it after editing.

- `src/flowbench/runner/driver.py`: 40, 169, 176 (comments); 353, 388, 395, 399, 443,
  458, 459, 460, 461, 463, 467 (code) — 14 sites.
- `src/flowbench/runner/loop.py`: 91, 132
- `src/flowbench/model.py`: 53 (×2), 57, 59
- `src/flowbench/watch.py`: 87, 99
- `src/flowbench/testing.py`: 45, 46
- `tests/runner/test_driver.py`: 62, 63, 218, 222, 231, 235, 274, 275, 289, 300, 308,
  323, 338, 346, 350, 359, 369, 378, 389, 394, 399, 409, 414, 426, 438
- `tests/runner/test_loop.py`: 90, 91, 92, 132, 133, 159, 160, 161, 186, 209, 210, 229,
  247, 263, 283, 301, 315
- `tests/test_model.py`: 14, 27, 28, 29, 43, 45, 53, 63, 71, 85
- `tests/test_watch.py`: 15, 33, 102, 113, 124, 126
- **Deliberately out of the sweep** (single-quoted, so outside AC2's grep, and outside
  the spec's three named comment sites): `src/flowbench/model.py:43,49` (comments) and
  `:58` (a `RuntimeError` message whose wording `tests/test_model.py:45` matches on).
  Left as-is; do not improvise a wider sweep.
- `tests/report/test_run_report.py`: 122, 128 — **the one exception**: an on-disk JSON
  fixture asserting the string form, which is exactly the contract AC4 protects. Stays
  literal, with a one-line comment saying so.

## T1 — create `src/flowbench/types.py`

```python
class TurnStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    TIMEOUT = "timeout"
    STALLED = "stalled"

@dataclass
class TurnResult:
    status: TurnStatus | str  # a TurnStatus for every documented value; decisions #7
    assistant_text: str
    artifact_exists: bool
    child_busy: bool = False
    stall_reason: str | None = None
    pane_tail: str | None = None

@runtime_checkable
class Completion(Protocol):
    completion: str

@runtime_checkable
class UserModel(Protocol):
    async def generate(self, prompt: str) -> Completion: ...
```

`TurnStatus`'s docstring: the omnigent session-status vocabulary (`idle`/`running`/
`failed`, read off `GET /v1/sessions/{id}`; documented closed at those three in
`omnigent_client/_sessions.py:126-127`) plus flowbench's derived `TIMEOUT` and `STALLED`.
Per-member comments carry the meanings currently at `driver.py:40` and in the
`_wait_idle`/`_send_once` comments — moved, not duplicated.

New `tests/test_types.py`:
- `test_members_are_their_values` (AC1): `{m.name: m.value for m in TurnStatus}` equals
  the exact five-pair mapping; `member == member.value` for each.
- `test_fstring_is_bare_value` (AC4): `f"{TurnStatus.IDLE}" == "idle"`. **Load-bearing** —
  this is the only test that fails if `StrEnum` is swapped for `(str, Enum)`;
  `json.dumps` emits `"idle"` for both, so the JSON test alone would not catch it.
- `test_completion_is_the_declared_return` (AC1): `typing.get_type_hints(UserModel.generate)
  ["return"] is flowbench.types.Completion`. Without it `Completion` is asserted nowhere —
  under `from __future__ import annotations` the annotation is a string, so an implementer
  could misspell or omit it and every other planned test would still pass.
- `test_json_round_trip` (AC4): `json.loads(json.dumps({"exit_status": TurnStatus.STALLED}))
  == {"exit_status": "stalled"}`.
- `test_turn_result_status_compares_to_literal` (AC4):
  `TurnResult(TurnStatus.IDLE, "", False).status == "idle"`.

Green after T1: new module, new tests, nothing else imports it yet.

## T2 — canonicalize `TurnResult`, sweep `src/`

- `src/flowbench/runner/driver.py`: delete the local `TurnResult` dataclass (its comment
  at :40 moves to `types.py` with it); add
  `from flowbench.types import TurnResult, TurnStatus  # re-export, one-release compat`.
  **No `__all__`** — no module in `src/flowbench` has one and this story does not start
  that convention. Sweep all 14 sites above, comments included. `_wait_idle`'s return type
  becomes `TurnStatus | str` with a docstring naming the passthrough (decisions #7):
  **no coercion, no fallback, no new control flow** — `return st or TurnStatus.TIMEOUT`
  keeps returning an undocumented `st` verbatim. `_stalled` returns `TurnStatus.STALLED`.
  Note :443 (`if st == "running"`, the `seen_running` latch) explicitly: inverting it
  hangs the suite rather than failing it, so it is the easiest site to break unnoticed.
- `src/flowbench/runner/loop.py`: :91 `!= TurnStatus.IDLE`, :132 `== TurnStatus.STALLED`;
  annotate `user_model: UserModel` in `run_agent_session`'s signature (AC6); import
  `TurnStatus`, `UserModel` from `flowbench.types`.
- `src/flowbench/model.py`: :53, :57, :59 become `TurnStatus.*`; `SessionModel`'s class
  docstring names `flowbench.types.UserModel` (AC6).
- `src/flowbench/watch.py`: :87 `cur == TurnStatus.FAILED`, :99 `cur == TurnStatus.RUNNING`
  — both omnigent session statuses (decisions #3).
- `src/flowbench/testing.py`: :45, :46 `TurnResult(TurnStatus.IDLE, ...)`; import
  `TurnResult`, `TurnStatus` from `flowbench.types`.

Tests added in T2:
- `tests/test_types.py::test_driver_reexports_types` (AC3):
  `flowbench.runner.driver.TurnResult is flowbench.types.TurnResult`, same for
  `TurnStatus`.
- `tests/test_types.py::test_user_model_implementations` (AC5):
  `isinstance(SessionModel(ScriptedDriver([])), UserModel)`,
  `isinstance(StubSim([]), UserModel)`, plus the negative control
  `assert not isinstance(object(), UserModel)` so the protocol is shown to discriminate.
  (`SessionModel(ScriptedDriver([]))` constructs — the `OmnigentDriver` annotation is
  `TYPE_CHECKING`-only.)
- `tests/test_types.py::test_user_model_annotation_and_docstring` (AC6):
  `typing.get_type_hints(run_agent_session)["user_model"] is flowbench.types.UserModel`
  and `"flowbench.types.UserModel" in SessionModel.__doc__`. Without this AC6 has no
  test — `test_user_model_implementations` passes whether or not the signature was
  touched.
- `tests/runner/test_driver.py::test_undocumented_server_status_passes_through` (AC10):
  a snapshot yielding a status omnigent never documents (e.g. `"zombie"`) makes
  `_send_once` return `TurnResult.status == "zombie"` — no exception, no relabelling.
  Fails if the boundary is later tightened to `TurnStatus(st)`. The test MUST set
  `d.turn_timeout_s = 0.1` (as `tests/runner/test_driver.py:385,410` already do): the
  passthrough return is reached only by exhausting the turn budget in real monotonic time,
  which `_instant_sleep` does not fast-forward.

Green after T2: full suite (the still-literal tests keep passing — `StrEnum` members
compare equal to their strings).

## T3 — sweep `tests/`

Sweep every site in the inventory above except `tests/report/test_run_report.py:122,128`.
The `_FakeChat` scripts in `tests/runner/test_driver.py` are raw **server** statuses fed
to `_snapshot`; they become `TurnStatus.*` too (same strings), with a comment that these
are server-side inputs, not driver outputs. `tests/test_model.py:45` is
`pytest.raises(RuntimeError, match="timeout")` — a regex over the exception message, not a
status: leave it as a literal.

T3 has its own completeness gate (AC2's grep is `src/`-only and would not catch a missed
test literal), recorded in `gates.md`:

```
rg -n '"idle"|"failed"|"timeout"|"stalled"|"running"' tests/
```
→ only the three declared exceptions: `tests/report/test_run_report.py:122,128` (on-disk
JSON fixture), `tests/test_model.py`'s `pytest.raises(..., match="timeout")` (a regex over
an exception message, not a status), and the new `tests/test_types.py` (it asserts the
string values themselves — that is its whole job).

## T4 — docs, downstream, gates

- `docs/design/runner.md:57-59`: the prose listing the five statuses is replaced by a
  member → meaning → producer table (`IDLE`/`RUNNING`/`FAILED` produced by the omnigent
  server; `TIMEOUT` and `STALLED` derived by `_wait_idle`/`_send_once`), plus a pointer to
  `flowbench/types.py` as the vocabulary's home. The surrounding watchdog paragraph stays.
- `CLAUDE.md` Layout: one line for `src/flowbench/types.py`.
- `docs/roadmap/current-state.md`: add the `types.py` row to the per-module table and
  update `runner/driver.py`'s line count (the dataclass leaves it).
- Gates, each recorded in `.claude/engineering-loop/items/issue-64/gates.md` (scenarios
  worktree) with its command and output tail:
  1. AC2 grep (`src/`) → only `src/flowbench/types.py`.
  2. T3 grep (`tests/`) → only the three declared exceptions: `tests/report/test_run_report.py:122,128` (on-disk
JSON fixture), `tests/test_model.py`'s `pytest.raises(..., match="timeout")` (a regex over
an exception message, not a status), and the new `tests/test_types.py` (it asserts the
string values themselves — that is its whole job).
  3. V1: `uv run pytest -q` → ≥ 188 passed, 1 skipped.
  4. `uv run ruff check` and `uv run ruff format --check`.
  5. **V2, against THIS branch.** `$SCENARIOS` sources flowbench from
     `{ git = ..., branch = "master" }` (`pyproject.toml:36`), so `uv sync` alone installs
     the pinned engine (7e696c7, two commits behind master) and never loads
     `flowbench/types.py`. **`uv pip install -e` is not enough either**: `uv run`
     implicitly re-syncs the locked environment and silently uninstalls the editable
     overlay before running the command (verified at gate 2). Use one of the two forms
     that survive the implicit sync:
     ```
     cd /Users/zarz/dev/xebia/flowbench-scenarios--s021
     uv run --with-editable /Users/zarz/dev/agents/flowbench--s021 pytest -q
     # or: uv sync && uv pip install -e <engine worktree> && uv run --no-sync pytest -q
     ```
     The gate is **self-verifying, not trust-the-install-line**: record in `gates.md` the
     output of
     ```
     uv run --with-editable /Users/zarz/dev/agents/flowbench--s021 \
       python -c "import flowbench, flowbench.types; print(flowbench.__file__)"
     ```
     and require it to print a path under the engine worktree. Gate 6's post-rebase re-run
     uses the same form.
     This is the only gate that exercises the one live downstream consumer of the changed
     import: `scripts/codex_review.py:76` (`result.status != "idle"`) and
     `tests/test_codex_review.py:7` (`from flowbench.runner.driver import TurnResult`) —
     which is also the concrete reason the compat re-export cannot be dropped
     (decisions #4, corrected).
  6. `git fetch origin && git rebase origin/master`; re-run gates 3 and 5 (gate 5 in the
     same `--with-editable` form, path assertion included).

## Criterion → task → test map

| AC | Task | Test |
| --- | --- | --- |
| 1 members/values + `Completion` | T1 | `test_members_are_their_values`, `test_completion_is_the_declared_return` |
| 2 no literals in `src/` | T2 | `gates.md` gate 1 |
| 3 driver re-export | T2 | `test_driver_reexports_types` |
| 4 str/json compat | T1 | `test_fstring_is_bare_value`, `test_json_round_trip`, `test_turn_result_status_compares_to_literal` |
| 5 protocol conformance | T2 | `test_user_model_implementations` (with negative control) |
| 6 annotation + docstring | T2 | `test_user_model_annotation_and_docstring` |
| 7 V1 ≥ 188 | T1–T4 | `gates.md` gate 3 |
| 8 V2 | T4 | `gates.md` gate 5 (editable install recorded) |
| 9 ruff | T4 | `gates.md` gate 4 |
| 10 unknown status passthrough | T2 | `test_undocumented_server_status_passes_through` |
| (T3 completeness) | T3 | `gates.md` gate 2 |
