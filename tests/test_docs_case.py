"""`docs/design/case.md` owns the case format, so it states each part of it once.

A restatement elsewhere is the failure mode this catches: two places that can
disagree, and a reader who cannot tell which is current."""

from pathlib import Path

DOCS = Path(__file__).parents[1] / "docs"
CASE_MD = DOCS / "design" / "case.md"


def test_the_starting_workspace_is_one_section():
    text = CASE_MD.read_text()

    assert text.count("## The starting workspace") == 1


def test_each_workspace_field_is_documented_once():
    text = CASE_MD.read_text()

    assert text.count("| `seed: str \\| None` |") == 1
    assert text.count("| `git: bool` |") == 1


def test_no_doc_still_points_at_git_init_repo():
    """It is gone from the engine (#158); a doc naming it would send a reader to
    a helper that no longer exists."""
    stale = [p for p in DOCS.rglob("*.md") if "git_init_repo" in p.read_text()]

    assert stale == []
