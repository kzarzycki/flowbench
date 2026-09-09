"""`.generate(prompt) -> obj.completion` shim backed by one persistent driver
session, so a case's simulator and judge can be run as agent sessions too.

The loop primes the simulator once (persona + context) and then relays only
deltas — a normal dialog against this stateful session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flowbench.types import TurnStatus

if TYPE_CHECKING:
    from flowbench.driver import OmnigentDriver


class SessionModel:
    """`.generate(prompt) -> obj.completion` shim backed by one persistent
    omnigent session, so the simulator and judge are omnigent agents.
    Implements `flowbench.types.UserModel`.

    The loop primes the simulator once (persona + context) and then relays
    only deltas — a normal dialog against this stateful session."""

    def __init__(self, driver: OmnigentDriver):
        self._driver = driver
        self._started = False

    async def generate(self, prompt: str):
        if not self._started:
            await self._driver.start()
            self._started = True
        # The driver owns retry policy (docs/design/runner.md, "Send/retry policy"):
        # an idle result is a completed turn (flaked or not); anything else is not
        # re-sent here — TIMEOUT may be mid-turn after delivery, FAILED is already
        # past the driver's bounded re-sends.
        result = await self._driver.send(prompt)
        text = result.assistant_text
        if result.status != TurnStatus.IDLE or not text.strip():
            raise RuntimeError(
                f"simulator/judge turn ended {result.status!r} with "
                f"{'no' if not text.strip() else 'a'} reply"
            )

        class _Out:
            completion = text

        return _Out()

    async def close(self) -> None:
        if self._started:
            await self._driver.close()
