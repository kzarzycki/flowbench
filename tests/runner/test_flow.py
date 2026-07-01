"""The Flow record: sane defaults, and each flow is an independent value (no shared
mutable default lists)."""

from pathlib import Path

from flowbench.runner.flow import Flow


def test_arm_defaults_are_the_vanilla_baseline():
    a = Flow(name="baseline")
    assert a.harness == "claude-native"
    assert a.skills == "all"
    assert a.skill_dirs == [] and a.mcp_files == []


def test_arms_do_not_share_mutable_defaults():
    a, b = Flow(name="x"), Flow(name="y")
    assert a.skill_dirs is not b.skill_dirs


def test_arm_carries_skill_dirs():
    a = Flow(
        name="superpowers", skills="none", skill_dirs=[Path("/s/brainstorming"), Path("/s/tdd")]
    )
    assert a.skills == "none"
    assert [p.name for p in a.skill_dirs] == ["brainstorming", "tdd"]
