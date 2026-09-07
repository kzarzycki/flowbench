"""Test doubles for the flowbench runtime — offline stand-ins for the three
omnigent factories (`make_flow_driver`, `make_simulator`, `run_judge`) that
`run_case`/`run_case_n` accept, so the whole pipeline is unit-tested without a
live omnigent server."""

from __future__ import annotations


class ScriptedDriver:
    """Duck-typed driver stub replaying scripted TurnResults."""

    def __init__(self, results):
        self.results = list(results)
        self.sent = []

    async def start(self):
        pass

    async def send(self, text):
        self.sent.append(text)
        return self.results.pop(0)

    async def close(self):
        pass
