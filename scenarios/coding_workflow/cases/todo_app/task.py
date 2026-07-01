"""The spike-2 case: load the envisioned shape, expose the agent prompt, the
ambiguous first prompt, and the simulator profiles. The agent-under-test never
sees the shape; the simulator reveals it only when asked."""

from __future__ import annotations

from pathlib import Path

CASE_DIR = Path(__file__).parent / "case"
ENVISIONED_SHAPE = (CASE_DIR / "envisioned-shape.md").read_text()

FIRST_PROMPT = (
    "I want a command-line todo app in Python. Before building anything, let's "
    "brainstorm it together — interview me to clarify what I need."
)

DONE_TOKEN = "<<DONE>>"

# The SUT is VANILLA Claude Code: NO system prompt, NO harness-level steering. The
# invite to brainstorm/interview lives in FIRST_PROMPT — it is the USER's request,
# phrased the way this user actually opens a build, NOT something we inject into the
# agent. With superpowers installed, whether that invite actually fires the
# brainstorming workflow and how well it covers the underspecified points is what we
# measure (clarifying_coverage). The request is still ambiguous: it names only a
# Python CLI todo app and leaks none of the envisioned shape. The AskUserQuestion
# card is disabled at the harness level (it deadlocks the tmux prompt), so the agent
# asks in plain text on its own.

_PROFILES = {
    "cooperative_faithful": """\
You are a hands-off user who wants MAXIMALLY AUTONOMOUS coding. You NEVER write,
edit, or fix code yourself, and you never debug or run things — you always ask
the AGENT to do it. You only: describe what you want, answer questions, and
approve or reject.
You answer ONLY the specific question the agent actually asks, with the minimal
fact needed — like a busy user. You revealed nothing beyond "a command-line todo
app in Python"; do NOT volunteer the rest of the shape. If the agent asks
something broad or open ("what do you want it to do?", "tell me your
requirements"), do NOT dump the spec — give one short sentence and tell them to
ask about specifics. Answer concrete questions truthfully from the shape.
When the agent proposes a design or plan: APPROVE it only if it matches the shape.
If it CONTRADICTS the shape, say briefly that the specific aspect is wrong (name
the dimension, e.g. "the storage" or "the done behaviour") and ask the agent to
fix it — but do NOT state the correct value and do NOT propose the fix yourself;
make the agent figure it out. Never do the agent's thinking for it. If offered a
"visual companion" / browser mockups, DECLINE — say plain text is fine. Keep
replies short.""",
}

# The five deliberately-underspecified points, with question keywords used to
# OBJECTIVELY detect whether the SUT asked about each (clarifying_coverage). This
# does not trust the judge's prose — it scans the SUT's own questions.
UNDERSPECIFIED_TOPICS: dict[str, list[str]] = {
    "persistence": [
        "persist",
        "save",
        "saved",
        "store across",
        "across runs",
        "between runs",
        "survive",
        "remember",
        "in-memory",
        "in memory",
    ],
    "fields": [
        "field",
        "priority",
        "attribute",
        "due date",
        "metadata",
        "what information",
        "what data",
        "properties",
    ],
    "done_handling": [
        "mark",
        "complete",
        "completed",
        "delete when",
        "remove when",
        "keep done",
        "check off",
        "vs delete",
        "or delete",
    ],
    "invocation": [
        "invoke",
        "run it",
        "python -m",
        "entry point",
        "how do you run",
        "how should i run",
        "subcommand",
        "command name",
        "cli interface",
    ],
    "storage_format": [
        "json",
        "sqlite",
        "csv",
        "yaml",
        "format",
        "filename",
        "file name",
        "where should",
        "which file",
        "location",
        "path",
    ],
}

_PREAMBLE = (
    "You are role-playing a USER who wants a todo app built. You are NOT the "
    "engineer. Stay in character.\n\n"
)

_DONE_RULES = (
    f"\n\nHOW TO REPLY each turn, in priority order:\n"
    f"1. If the agent asked you a question, answer it (per the rules above).\n"
    f"2. If the agent is mid-build / working / reporting progress and is NOT asking "
    f"you anything and has NOT yet delivered a finished app, reply with EXACTLY "
    f"`Continue.` — nothing else. Do NOT add encouragement, do NOT say "
    f'"take your time", do NOT re-state the task.\n'
    f"3. When — and only when — the agent has delivered a finished, working app and "
    f"is asking you nothing further, reply with EXACTLY `{DONE_TOKEN}` and nothing "
    f"else.\n"
)


def simulator_system(profile: str = "cooperative_faithful") -> str:
    rules = _PROFILES[profile]  # KeyError on unknown profile is intended
    return _PREAMBLE + rules + _DONE_RULES + "\n\nENVISIONED SHAPE:\n" + ENVISIONED_SHAPE
