"""The engine's vocabulary of turn outcomes: `TurnStatus`, `TurnResult`, and the
`UserModel`/`Completion` protocols that `run_agent_session` drives.

Canonical home for these types; `flowbench.runner.driver` re-exports `TurnResult`
and `TurnStatus` for one release (existing imports, engine and downstream, keep
working unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class TurnStatus(StrEnum):
    """The omnigent session-status vocabulary (`idle`/`running`/`failed`, read off
    `GET /v1/sessions/{id}`; documented closed at those three in
    `omnigent_client/_sessions.py:126-127`) plus flowbench's two derived values.

    `StrEnum` so every member compares equal to, hashes equal to, and formats/
    serializes as the same plain string the code has always emitted — nothing
    written to disk (session.json, run.json) changes.
    """

    IDLE = "idle"  # turn settled: the agent is awaiting the user
    RUNNING = "running"  # still mid-turn when the per-turn cap fired (loop.py)
    FAILED = "failed"  # the omnigent session reported failed
    TIMEOUT = "timeout"  # derived: idle but silent, or _wait_idle's budget expired
    STALLED = "stalled"  # derived: a prompt nobody can answer, or no heartbeat


@dataclass
class TurnResult:
    status: TurnStatus | str  # a TurnStatus for every documented value; an
    # undocumented server status passes through verbatim as a diagnostic
    # (decisions #7) — never coerced, never raised on.
    assistant_text: str  # latest assistant-authored text after the turn
    artifact_exists: bool
    stall_reason: str | None = None  # "prompt" | "no_progress" when stalled
    pane_tail: str | None = None  # last terminal lines at the stall, best effort


@runtime_checkable
class Completion(Protocol):
    completion: str


@runtime_checkable
class UserModel(Protocol):
    """`.generate(prompt) -> Completion` — the loop's contract for the user side
    of a turn (simulator or judge). Implemented by `flowbench.model.SessionModel`
    and the offline double `flowbench.testing.StubSim`."""

    async def generate(self, prompt: str) -> Completion: ...
