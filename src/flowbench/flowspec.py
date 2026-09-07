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
    return flows
