from pathlib import Path

import pytest
import yaml

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


def _flows_file(tmp_path, flows) -> Path:
    """A flows.yaml beside a real skill dir — `load_flows` resolves entries
    relative to the file and rejects one without a SKILL.md."""
    skill = tmp_path / "skills" / "greeting-file"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: greeting-file\ndescription: x\n---\nx\n")
    path = tmp_path / "flows.yaml"
    path.write_text(yaml.safe_dump({"flows": flows}))
    return path


def test_skills_none_with_skill_dirs_raises(tmp_path):
    """A5: the combination cannot work, so it fails loudly at load rather than
    scoring as a flow that had its bundle."""
    path = _flows_file(
        tmp_path,
        [{"name": "superpowers", "skills": "none", "skill_dirs": ["skills/greeting-file"]}],
    )

    with pytest.raises(ValueError, match="superpowers"):
        load_flows(path)


def test_skills_none_without_skill_dirs_loads(tmp_path):
    """The baseline shape stays legal — `none` is how a flow is provably bare."""
    path = _flows_file(tmp_path, [{"name": "baseline", "skills": "none"}])

    (flow,) = load_flows(path)

    assert flow["skills"] == "none"


def test_skills_list_with_skill_dirs_loads(tmp_path):
    path = _flows_file(
        tmp_path,
        [{"name": "superpowers", "skills": ["project"], "skill_dirs": ["skills/greeting-file"]}],
    )

    (flow,) = load_flows(path)

    assert [Path(d).name for d in flow["skill_dirs"]] == ["greeting-file"]
