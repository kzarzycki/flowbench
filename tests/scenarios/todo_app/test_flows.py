"""flows.yaml: baseline bare (skills="none"), superpowers loading the vendored
skill_dirs from its workspace (skills=["project"]). Both host-independent: the
operator's own ~/.claude is hidden either way."""

from pathlib import Path

from flowbench.flowspec import load_flows

CASE_DIR = Path(__file__).parent.parent.parent.parent / "scenarios/swe_e2e/cases/todo_app"
SKILLS_DIR = CASE_DIR.parent.parent / "skills"


def _flows():
    return load_flows(CASE_DIR / "flows.yaml")


def test_baseline_is_bare_and_superpowers_declares_project():
    """A10. Baseline is provably bare — `none` is `--setting-sources ""`, which
    loads no skills from anywhere, so the comparison is not contaminated by the
    mechanism. Superpowers names the `project` source, which loads the workspace's
    own `.claude/skills/` and still hides the operator's `~/.claude`."""
    flows = _flows()
    assert [f["name"] for f in flows] == ["baseline", "superpowers"]
    baseline, superpowers = flows
    assert baseline.get("skills") == "none"
    assert not baseline.get("skill_dirs")
    assert superpowers.get("skills") == ["project"]
    assert superpowers.get("skill_dirs")


def test_no_steering():
    # neither flow carries a prepend/append system-prompt-shaped nudge — the SUT
    # is vanilla Claude Code, whether skills == "none" or the superpowers set.
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
