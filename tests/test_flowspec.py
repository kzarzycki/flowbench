import pytest

from flowbench.flowspec import compose_kickoff, load_flows


def test_compose_kickoff_orders_prepend_task_append():
    flow = {"prepend": "PRE", "append": "POST"}
    out = compose_kickoff(flow, "  TASK  ")
    assert out == "PRE\n\nTASK\n\nPOST"


def test_compose_kickoff_skips_empty_parts():
    assert compose_kickoff({"prepend": "", "append": "POST"}, "TASK") == "TASK\n\nPOST"


def test_load_flows_resolves_skill_dirs(tmp_path):
    skill = tmp_path / "skills" / "brainstorming"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# s")
    case = tmp_path / "cases" / "x"
    case.mkdir(parents=True)
    (case / "flows.yaml").write_text(
        "flows:\n  - name: a\n    skill_dirs: [../../skills/brainstorming]\n"
    )
    flows = load_flows(case / "flows.yaml")
    assert flows[0]["skill_dirs"] == [skill.resolve()]


def test_load_flows_missing_skill_dir_raises(tmp_path):
    case = tmp_path / "c"
    case.mkdir()
    (case / "flows.yaml").write_text("flows:\n  - name: a\n    skill_dirs: [../nope]\n")
    with pytest.raises(ValueError, match="nope"):
        load_flows(case / "flows.yaml")


def test_load_flows_without_skill_dirs_unchanged(tmp_path):
    (tmp_path / "flows.yaml").write_text("flows:\n  - name: a\n    skills: none\n")
    flows = load_flows(tmp_path / "flows.yaml")
    assert "skill_dirs" not in flows[0]
