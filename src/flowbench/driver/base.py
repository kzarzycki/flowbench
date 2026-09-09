"""`AgentDriver` — the seam every agent REPL is driven through.

The loop, `run.py` and the offline doubles depend on this ABC alone; the one
module that knows omnigent exists is `flowbench.driver.omnigent`.
"""

from __future__ import annotations

import abc
from typing import Any

from flowbench.types import TurnResult


class AgentDriver(abc.ABC):
    """Drive a real agent REPL over a multi-turn task. Async + teardown-safe."""

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def send(self, text: str) -> TurnResult: ...

    @abc.abstractmethod
    async def capture_session(self) -> dict[str, Any]:
        """The transcript + run fields the normalizer consumes."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down. MUST be idempotent (safe to call after a failure)."""
