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


@pytest.mark.parametrize(
    "skills",
    [
        "none",  # --setting-sources "" — loads nothing at all
        [],  # emits no flag, so the CLI's defaults leak the host ~/.claude (#151)
        None,
        "project",  # a bare string is not a source list; no flag is emitted
    ],
)
def test_skills_that_cannot_load_the_workspace_are_rejected(tmp_path, skills):
    """A flow scored as though it had a bundle it never received is the one lie
    this benchmark cannot afford, so every shape that loses the declared skills —
    or silently gains the operator's own — fails at load."""
    path = _flows_file(
        tmp_path, [{"name": "sp", "skills": skills, "skill_dirs": ["skills/greeting-file"]}]
    )

    with pytest.raises(ValueError, match="sp"):
        load_flows(path)


@pytest.mark.parametrize("skills", [[""], [None], ["project", 3]])
def test_skills_entries_must_be_source_names(tmp_path, skills):
    """A non-string entry would otherwise die inside `",".join` at session time."""
    path = _flows_file(
        tmp_path, [{"name": "sp", "skills": skills, "skill_dirs": ["skills/greeting-file"]}]
    )

    with pytest.raises(ValueError, match="setting-source"):
        load_flows(path)


def test_skills_all_with_skill_dirs_loads(tmp_path):
    """`all` is legal and explicit: the CLI's default sources include `project`."""
    path = _flows_file(
        tmp_path, [{"name": "sp", "skills": "all", "skill_dirs": ["skills/greeting-file"]}]
    )

    (flow,) = load_flows(path)

    assert flow["skills"] == "all"


def test_skills_list_with_skill_dirs_loads(tmp_path):
    path = _flows_file(
        tmp_path,
        [{"name": "superpowers", "skills": ["project"], "skill_dirs": ["skills/greeting-file"]}],
    )

    (flow,) = load_flows(path)

    assert [Path(d).name for d in flow["skill_dirs"]] == ["greeting-file"]


def test_skills_empty_list_is_rejected_even_without_skill_dirs(tmp_path):
    """An empty list emits no `--setting-sources` flag at all, so the CLI's defaults
    load the operator's own ~/.claude (#151). That leak belongs to the `skills`
    declaration, not to `skill_dirs`, so it fails for any flow."""
    path = _flows_file(tmp_path, [{"name": "baseline", "skills": []}])

    with pytest.raises(ValueError, match="#151"):
        load_flows(path)


@pytest.mark.parametrize("skills", [["user"], ["local"], ["user", "local"]])
def test_skills_without_project_cannot_see_the_workspace(tmp_path, skills):
    """A source list that omits `project` is the worst shape of all: the declared
    skill_dirs stay invisible AND the operator's own skills load in their place, so
    the flow scores as though it ran the bundle it never saw."""
    path = _flows_file(
        tmp_path, [{"name": "sp", "skills": skills, "skill_dirs": ["skills/greeting-file"]}]
    )

    with pytest.raises(ValueError, match="add project"):
        load_flows(path)
