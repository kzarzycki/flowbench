"""Fake omnigent transcripts for offline phase-detection tests."""

import json


def _msg(role, text):
    return {"type": "message", "role": role, "content": text}


def _skill(name):
    # how omnigent captures the SUT's Skill tool call (arguments is a JSON string)
    return {"type": "function_call", "name": "Skill", "arguments": json.dumps({"skill": name})}


FULL_WORKFLOW = {
    "items": [
        _msg("user", "I want a command-line todo app in Python. Can you build it?"),
        _skill("superpowers:brainstorming"),
        _msg("assistant", "A few questions first: where should tasks be stored?"),
        _skill("superpowers:writing-plans"),
        _msg("assistant", "I'm using requesting-code-review to review the implementation."),
        _msg("assistant", "Tests pass (7 passed). Done — the app is working."),
    ]
}

SKIPPED_PHASES = {
    "items": [
        _msg("user", "I want a command-line todo app in Python. Can you build it?"),
        _msg("assistant", "Sure, here's the code. Done."),
    ]
}
