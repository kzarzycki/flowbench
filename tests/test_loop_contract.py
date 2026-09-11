"""The loop's gate-5 contract (issue #162): the shared live-gate case declares only
harnesses the gate requires, and the gate names a command that still exists. Prose is
asserted the way `test_board_sh.py` does it — whitespace-normalized, placement and
uniqueness — because a rule restated elsewhere, or a command deleted under the text, is
exactly how this gate stopped meaning anything."""

from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "engineering-loop"
README = " ".join((LOOP / "README.md").read_text().split())  # the prose is hard-wrapped
GATE5 = README.split("**LIVE (gate 5)**", 1)[1].split("Then: spawned", 1)[0]
RULE = "The gate case declares only harnesses the gate requires."


def test_gate5_states_the_harness_rule_once():
    assert README.count(RULE) == 1
    assert RULE in GATE5


def test_gate5_names_a_command_that_exists():
    assert "flowbench run scenarios/swe_planning/cases/smoke_todo_app" in GATE5
    assert "flowbench watch" in GATE5
    # deleted by #137 (scenarios 3bdcbc6): neither module exists any more
    assert "scenarios.swe_planning.run" not in README
    assert "scenarios.swe_planning.watch" not in README
