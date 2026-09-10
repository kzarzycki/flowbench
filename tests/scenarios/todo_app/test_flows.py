"""flows.yaml: baseline vs superpowers, both bare skills="none" (host-independent),
superpowers carrying the vendored skill_dirs bundle."""

from pathlib import Path

from flowbench.flowspec import load_flows

CASE_DIR = Path(__file__).parent.parent.parent.parent / "scenarios/swe_e2e/cases/todo_app"
SKILLS_DIR = CASE_DIR.parent.parent / "skills"


def _flows():
    return load_flows(CASE_DIR / "flows.yaml")


def test_flow_names_and_skills_none():
    flows = _flows()
    assert [f["name"] for f in flows] == ["baseline", "superpowers"]
    assert all(f.get("skills") == "none" for f in flows)


def test_no_steering():
    # neither flow carries a prepend/append system-prompt-shaped nudge — the SUT
    # is vanilla Claude Code, whether skills == "none" or the superpowers bundle.
    for f in _flows():
        assert not f.get("prepend")
        assert not f.get("append")


def test_superpowers_skill_dirs_resolve_and_count_14():
    flows = _flows()
    superpowers = next(f for f in flows if f["name"] == "superpowers")
    dirs = superpowers["skill_dirs"]
    assert len(dirs) == 14
    for d in dirs:
        assert (Path(d) / "SKILL.md").is_file()


def test_version_md_names_6_3_0():
    assert "6.3.0" in (SKILLS_DIR / "VERSION.md").read_text()
