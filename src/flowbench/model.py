"""`.generate(prompt) -> obj.completion` shim backed by one persistent driver
session, so a case's simulator and judge can be run as agent sessions too.

The loop primes the simulator once (persona + context) and then relays only
deltas — a normal dialog against this stateful session."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from flowbench.types import TurnStatus

if TYPE_CHECKING:
    from flowbench.runner.driver import OmnigentDriver

GENERATE_ATTEMPTS = 3  # simulator/judge turns: total sends per prompt (#39)
GENERATE_RETRY_WAIT_S = 30.0  # matches OmnigentDriver.send_retry_wait_s


class SessionModel:
    """`.generate(prompt) -> obj.completion` shim backed by one persistent
    omnigent session, so the simulator and judge are omnigent agents.
    Implements `flowbench.types.UserModel`.

    The loop primes the simulator once (persona + context) and then relays
    only deltas — a normal dialog against this stateful session."""

    def __init__(self, driver: OmnigentDriver):
        self._driver = driver
        self._started = False
        self._last_text = ""  # previous turn's completion — staleness sentinel (#39)

    def _fresh(self, result) -> bool:
        """A reply that is non-empty and differs from the previous turn's
        completion — i.e. the agent actually answered THIS prompt."""
        text = result.assistant_text.strip()
        return bool(text) and text != self._last_text.strip()

    async def generate(self, prompt: str):
        if not self._started:
            await self._driver.start()
            self._started = True
        # The omnigent terminal-readiness flake ("terminal did not become ready
        # within 30.0s ... message was not delivered") ends turns 'failed', and
        # OmnigentDriver.send only retries when session labels confirm
        # non-delivery — which simulator/judge sessions don't reliably set (#39).
        # A failed turn with a FRESH reply completed before the flake fired —
        # use it. Empty/stale text means no reply landed: re-send (a repeated
        # question to a stateful dialog agent; only the fresh reply is consumed).
        # 'timeout' is NOT retried — the prompt may be mid-turn after delivery,
        # and injecting into a busy terminal is the known session-killer.
        for attempt in range(1, GENERATE_ATTEMPTS + 1):
            result = await self._driver.send(prompt)
            if (
                result.status == TurnStatus.IDLE
                or result.status == TurnStatus.TIMEOUT
                or self._fresh(result)
            ):
                break
            if attempt < GENERATE_ATTEMPTS:
                await asyncio.sleep(GENERATE_RETRY_WAIT_S)
        if result.status == TurnStatus.TIMEOUT:
            raise RuntimeError(f"simulator/judge turn ended 'timeout' (attempt {attempt})")
        if result.status != TurnStatus.IDLE:
            if not self._fresh(result):
                raise RuntimeError(
                    f"simulator/judge turn ended {result.status!r} with no fresh "
                    f"reply after {attempt} attempts"
                )
            print(
                f"[flowbench] turn status {result.status!r}; using the emitted text",
                file=sys.stderr,
            )
        self._last_text = result.assistant_text

        class _Out:
            completion = result.assistant_text

        return _Out()

    async def close(self) -> None:
        if self._started:
            await self._driver.close()
