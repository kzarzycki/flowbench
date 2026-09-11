"""The engine's own smoke gate: one flow, one file, one relay.

Cheap enough to run live on demand and still touch everything a real case
touches — the kickoff, a simulator relay, the deliverable probe, `score`, the run
dir. `task.md` withholds the file name and the line and tells the agent to ask
for both, so a passing run proves the simulator answered, not just that the prime
landed.
"""

from __future__ import annotations

from flowbench.case import Case


class HelloCase(Case):
    """`score` is what grades each flow — there is no `judge.md`, because the
    flows here are one per harness the engine can drive, not rival approaches to
    compare. The budget is tight on purpose: a greeting that needs a fifth turn
    or five minutes is a broken engine, not a slow agent, and a gate should say
    so fast."""

    deliverable = "hello.txt"
    max_turns = 4
    deadline_s = 300.0

    async def score(self, flow, flow_dir, session) -> dict:
        """Did the file arrive, and does it greet? Presence is the session's
        `artifact_exists` — an empty file and a directory both have no text — and
        the greeting is matched case-insensitively: `knowledge.md` asks for one
        exact line, but a run that wrote `HELLO, WORLD!` did the job."""
        exists = bool(session.get("artifact_exists"))
        text = (session.get("artifact_text") or "") if exists else ""
        greets = "hello" in text.lower()
        return {
            "objective": {"acceptance": 1.0 if greets else 0.0},
            "deliverable": {"name": self.deliverable, "exists": exists, "greets": greets},
        }
