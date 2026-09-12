"""The engine's own smoke gate: one flow, one file, one relay, one skill.

Cheap enough to run live on demand and still touch everything a real case
touches — the kickoff, a simulator relay, the deliverable probe, `score`, the run
dir. `task.md` withholds the file name and the line and tells the agent to ask
for both, so a passing run proves the simulator answered, not just that the prime
landed. The flow's one skill is seeded into the workspace rather than bundled, so
the gate also proves that path loads — `score` reports whether it fired.
"""

from __future__ import annotations

import json

from flowbench.case import Case, Workspace

SKILL = "greeting-file"


def _skill_fired(session: dict, name: str) -> bool:
    """Did the SUT actually invoke the workspace-seeded skill? Read off its `Skill`
    tool calls (omnigent captures them as `function_call` items) — on-disk ground
    truth that the skill LOADED, as distinct from narrating that it did.

    Namespace-agnostic: the workspace path exposes a bare `greeting-file` where the
    bundle path exposed `claude_code:greeting-file`."""
    for item in session.get("items", []):
        if item.get("type") != "function_call" or item.get("name") != "Skill":
            continue
        try:
            skill = json.loads(item.get("arguments") or "{}").get("skill")
        except (ValueError, TypeError):
            continue
        if isinstance(skill, str) and skill.rsplit(":", 1)[-1] == name:
            return True
    return False


class HelloCase(Case):
    """One flow, so `score` is what grades it — a lone flow with no override is a
    load error — and there is no `judge.md` to compare against. The budget is
    tight on purpose: a greeting that needs a fifth turn or five minutes is a
    broken engine, not a slow agent, and a gate should say so fast."""

    deliverable = "hello.txt"
    max_turns = 4
    deadline_s = 300.0
    # A repo and nothing else. This case is the engine's live gate, so the gate
    # covers workspace materialization — which is also where the flow's skills are
    # placed (flows.yaml seeds `greeting-file`); an empty commit adds no content the
    # agent has to reason about.
    workspace = Workspace(git=True)

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
            # Reported, not scored: the deliverable is what this case grades, and a
            # skill that did not fire is a finding about the run, not a failed gate.
            # It is the live evidence that a workspace-seeded skill loads at all.
            "skill_fired": _skill_fired(session, SKILL),
        }
