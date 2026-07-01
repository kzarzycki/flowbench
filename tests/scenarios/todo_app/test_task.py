"""Case loading + the simulator system prompt."""

import pytest

from scenarios.coding_workflow.cases.todo_app import task


def test_first_prompt_leaks_only_python_cli():
    p = task.FIRST_PROMPT.lower()
    assert "python" in p and ("command-line" in p or "cli" in p)
    # the underspecified facts must NOT be in the opening prompt
    for leak in ("json", "priority", "tasks.json", "python -m todo", "done <id>"):
        assert leak not in p


def test_simulator_system_embeds_shape_profile_and_done_token():
    sys = task.simulator_system("cooperative_faithful")
    assert "tasks.json" in sys  # the full shape is available
    assert "reveal" in sys.lower()  # partial-reveal rule
    assert task.DONE_TOKEN in sys  # how to signal completion
    assert "visual companion" in sys.lower()  # decline-the-companion rule


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        task.simulator_system("nope")


def test_no_steering_prompt_defined():
    # bug 3: the case must NOT inject a system prompt that tells the agent to use
    # the workflow / ask clarifying questions — the SUT is vanilla Claude Code.
    assert not hasattr(task, "AGENT_PROMPT")


def test_done_rules_cover_continue_and_done():
    # Fix C: a working/progress idle gets a terse "Continue."; DONE only on a
    # finished app — and the chatty filler is explicitly forbidden.
    sysmsg = task.simulator_system()
    assert "Continue." in sysmsg
    assert task.DONE_TOKEN in sysmsg
    assert "take your time" in sysmsg.lower()  # named as forbidden


def test_simulator_does_not_leak_corrections():
    # H4 fix: on a contradiction the sim names the dimension but must NOT hand over
    # the value or do the agent's thinking.
    sys = " ".join(task.simulator_system().lower().split())  # collapse line wraps
    assert "do not state the correct value" in sys
    assert "never do the agent's thinking" in sys


def test_underspecified_topics_cover_the_five_points():
    assert set(task.UNDERSPECIFIED_TOPICS) == {
        "persistence",
        "fields",
        "done_handling",
        "invocation",
        "storage_format",
    }
    assert all(task.UNDERSPECIFIED_TOPICS.values())  # each has keywords
