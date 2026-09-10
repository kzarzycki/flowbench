# S02.1 decisions (self-answered, rule 3)

1. **The epic names three members (`IDLE`, `FAILED`, `TIMEOUT`); the code produces five.**
   `_wait_idle` (`driver.py:463`) returns `st or "timeout"` where `st` is the raw omnigent
   session status, so a turn that hits the per-turn cap while the agent is still working
   surfaces as `"running"` — `runner/loop.py`'s comment names this case explicitly, and
   `todo-app-001` recorded `exit_status=running` for both flows. `"stalled"` was added by
   #57/#63 after the epic text was written. Enumerating three would silently drop two live
   values. Decision: five members. Derived from code + the ledger, not product judgment.

2. **`StrEnum` vs `Enum` + `str` mixin.** Python floor is 3.12 (`pyproject.toml:7`), so
   `enum.StrEnum` is available and is the form whose `str()`/`format()` yield the bare
   value — a plain `class X(str, Enum)` formats as `"TurnStatus.IDLE"` under f-strings,
   which would corrupt `session.json`. Decision: `StrEnum`.

3. **`watch.py:87` compares an omnigent *session* status, not a `TurnStatus`.** The
   vocabulary is the same one the driver reads off the server and passes through; the
   epic's verify line requires no literal outside `types.py`. Decision: `TurnStatus.FAILED`
   is used there too, and `TurnStatus`'s docstring states it is the omnigent session-status
   vocabulary plus flowbench's derived `TIMEOUT`/`STALLED`. No new type for the same strings.

4. **Where does `TurnResult` live, and does `driver.py` keep exporting it?** The epic puts
   it in `types.py`; S02.2 relies on the driver shrinking. Downstream (`$SCENARIOS`) DOES consume it in live
   code — `scripts/codex_review.py:76` compares `result.status != "idle"` and
   `tests/test_codex_review.py:7` does `from flowbench.runner.driver import TurnResult`
   (corrected at gate 2; an earlier draft of this entry wrongly said only historical plan
   docs referenced it). That consumer is the concrete reason the re-export cannot be
   dropped, and the reason V2 must run against this branch rather than the git-pinned
   master (`$SCENARIOS/pyproject.toml:36`). Decision: canonical in `types.py`, re-exported from
   `flowbench.runner.driver`, same one-release policy.

5. **`UserModel` return type.** `SessionModel.generate` returns an ad-hoc `_Out` class with
   a `completion` attribute (`model.py:71-72`); the loop reads `out.completion` and nothing
   else. Decision: a two-Protocol shape (`Completion` with `completion: str`, `UserModel`
   with `async generate(prompt: str) -> Completion`) — the narrowest declaration of what
   the loop actually consumes. No refactor of `_Out` into a dataclass here (that would be
   a behavior-adjacent change outside the story's "mechanical replacement" scope).

6. **No `StallReason` enum.** Not asked for by the story; `stall_reason` has two values
   set in one place. YAGNI until S02.2 touches the driver.

7. **Annotating `_wait_idle` creates a boundary question the story did not have: what
   happens to a server status outside the enum?** Today it passes through verbatim into
   `TurnResult.status` and thence `session.json`'s `exit_status` (`driver.py:463`,
   `runner/loop.py:130`) — `todo-app-001` recorded `exit_status: "running"` this way. The
   omnigent client documents the vocabulary closed at three values
   (`.venv/.../omnigent_client/_sessions.py:126-127`), so the question is hypothetical —
   but `TurnStatus(st)` would turn a cosmetic upstream contract drift into a `ValueError`
   that kills a live run, and a `try/except` fallback to `FAILED` would destroy the
   diagnostic. Decision: no coercion, no fallback, no new control flow. The types say
   `TurnStatus | str` and a test (AC10) locks the passthrough. Behavior-preserving, which
   is what the story asks for; narrowing the boundary is S02.6 (error taxonomy) work.
