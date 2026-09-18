"""The schema doc is the prose copy of `flowbench.schema`: a member the enums
carry and the doc does not is a vocabulary nobody can read."""

from pathlib import Path

from flowbench.schema import FlowOutcome, RunKind

DOC = Path(__file__).parents[1] / "docs" / "design" / "run-schema.md"


def test_doc_exists():
    assert DOC.is_file()


def test_doc_spells_every_vocabulary_value():
    text = DOC.read_text()
    for value in (*FlowOutcome, *RunKind):
        assert value.value in text, value


def test_doc_states_the_two_reader_rules_verbatim():
    text = DOC.read_text()
    assert "A reader ignores unknown fields." in text
    assert "A missing `schema_version` is version 0." in text
