"""The case content lives as plain .md files (task.md/simulator.md/knowledge.md),
not Python — same shape as swe_planning's cases. These five intents replace the
Python-source checks in the now-deleted test_task.py."""

from pathlib import Path

from scenarios.swe_e2e.cases.todo_app import scorers

CASE_DIR = Path(__file__).parent.parent.parent.parent / "scenarios/swe_e2e/cases/todo_app"


def test_first_prompt_leaks_only_python_cli():
    p = (CASE_DIR / "task.md").read_text().lower()
    assert "python" in p and ("command-line" in p or "cli" in p)
    for leak in ("json", "priority", "tasks.json", "python -m todo", "done <id>"):
        assert leak not in p


def test_simulator_names_no_done_token_and_knowledge_carries_shape():
    # the token is the engine's (flowbench.loop.DONE_TOKEN), appended to the
    # prime prompt; the persona must not name a competing one.
    sim = (CASE_DIR / "simulator.md").read_text()
    knowledge = (CASE_DIR / "knowledge.md").read_text()
    assert "<<DONE>>" not in sim
    assert "tasks.json" in knowledge


def test_delivered_and_continue_rules_present():
    sim = (CASE_DIR / "simulator.md").read_text()
    assert "Continue." in sim
    assert "DELIVERED" in sim  # what "delivered" means here, in the case's words
    assert "<<DONE>>" not in sim
    assert "take your time" in sim.lower()


def test_simulator_never_states_corrections():
    sim = " ".join((CASE_DIR / "simulator.md").read_text().lower().split())
    assert "do not state the correct value" in sim
    assert "never do the agent's thinking" in sim


def test_underspecified_topics_cover_the_five_points():
    assert set(scorers.UNDERSPECIFIED_TOPICS) == {
        "persistence",
        "fields",
        "done_handling",
        "invocation",
        "storage_format",
    }
    assert all(scorers.UNDERSPECIFIED_TOPICS.values())
