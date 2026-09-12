"""Pure, stateless helpers for reading a case's flows.yaml and composing a
flow's kickoff message. No omnigent, no I/O beyond reading the flows file.
Everything here is unit-tested offline."""

from __future__ import annotations

from pathlib import Path

import yaml


def compose_kickoff(flow: dict, task_text: str) -> str:
    """The single first message sent to a flow: prepend + task + append."""
    parts = [
        (flow.get("prepend") or "").strip(),
        task_text.strip(),
        (flow.get("append") or "").strip(),
    ]
    return "\n\n".join(p for p in parts if p)


def _check_skills_can_load(flow: dict, path, wants_workspace: bool) -> None:
    """Every flow must declare setting sources that load what it says it loads.

    The seeding step fills `<flow_dir>/.claude/skills/`, and only the `project`
    setting source reads it. Every other shape silently loses the declared skills,
    or silently gains the operator's own — and a flow scored as though it had its
    bundle is the one lie this benchmark cannot afford, so these fail at load.

    - an EMPTY list emits no flag, so the CLI falls back to its default sources and
      the host `~/.claude` leaks in (#151) — the accident that looks like `"all"`.
    - a non-string entry would die later inside `",".join`.

    Those two are rejected for EVERY flow: the leak is the declaration's, not the
    skill_dirs'. `wants_workspace` adds the rest, for a flow whose `skill_dirs` the
    seeding step put in `<flow_dir>/.claude/skills/` — `"none"` (omnigent's `--setting-sources ""`, appended after
    flowbench's own args) reads nothing at all.

    `"all"` is legal and explicit: its defaults do include the project source.
    """
    skills = flow.get("skills", "all")
    name = flow.get("name")
    if skills == "all":
        return
    if isinstance(skills, (list, tuple)) and not skills:
        raise ValueError(
            f"flow {name!r} in {path}: skills [] emits no setting-sources flag at all, so the "
            "CLI's defaults load the operator's own ~/.claude (#151) — say skills: 'all' if "
            "that is what you mean, or name the sources"
        )
    if wants_workspace and not isinstance(skills, (list, tuple)):
        raise ValueError(
            f"flow {name!r} in {path}: skills {skills!r} loads nothing from the workspace, "
            "so the declared skill_dirs would be invisible — use skills: [project]"
        )
    if not isinstance(skills, (list, tuple)):
        return
    bad = [s for s in skills if not isinstance(s, str) or not s]
    if bad:
        raise ValueError(
            f"flow {name!r} in {path}: skills entries must be non-empty setting-source "
            f"names (user, project, local); got {bad!r}"
        )


def load_flows(path) -> list[dict]:
    path = Path(path)
    flows = yaml.safe_load(path.read_text())["flows"]
    for flow in flows:
        if "skill_dirs" in flow:
            resolved = []
            for entry in flow["skill_dirs"]:
                skill_dir = (path.parent / entry).resolve()
                if not (skill_dir / "SKILL.md").is_file():
                    raise ValueError(
                        f"skill_dirs entry {entry!r} in {path}: no SKILL.md at {skill_dir}"
                    )
                resolved.append(skill_dir)
            flow["skill_dirs"] = resolved
        _check_skills_can_load(flow, path, wants_workspace=bool(flow.get("skill_dirs")))
    return flows
