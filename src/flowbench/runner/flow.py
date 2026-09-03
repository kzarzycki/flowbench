"""A flow = one complete configuration under test.

Conceptually: harness, model, reasoning effort, bundle (skills/MCPs), optional
system prompt, prompt overlay, budgets — every field declared, nothing hidden
(docs/design/decisions/2026-09-03-flow-is-the-full-configuration.md). This
dataclass carries the bundle fields only; S03.1 widens it to the full schema.
"baseline", "superpowers", "Axis", "ACE" are all the same driver path carrying
different bundle skills/MCPs — never a separate CLI. The driver reads these
fields straight into the bundle it builds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Flow:
    """:param name: flow label (also the run-dir name and report column).
    :param harness: omnigent harness, e.g. "claude-native".
    :param skills: host-skill filter -> config.yaml top-level `skills:`.
        "all" (host ~/.claude visible), "none" (host skills suppressed; bundle
        skills still load), or a list of specific sources.
    :param skill_dirs: individual skill directories (each holding a SKILL.md),
        copied into <bundle>/skills/<name>/ so they load host-independent.
    :param mcp_files: per-flow MCP yamls, copied into <bundle>/tools/mcp/.
    """

    name: str
    harness: str = "claude-native"
    skills: str | list[str] = "all"
    skill_dirs: list[Path] = field(default_factory=list)
    mcp_files: list[Path] = field(default_factory=list)
