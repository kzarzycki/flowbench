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
    :param skills: Claude Code's setting sources -> config.yaml top-level `skills:`.
        "all" (the CLI's defaults, host ~/.claude visible), "none" (nothing loads
        at all — how a baseline flow is provably bare), or a list of sources such
        as ["project"], which loads the workspace's own .claude/skills/ and hides
        the host. "none" together with skill_dirs is rejected at flows.yaml load.
    :param skill_dirs: individual skill directories (each holding a SKILL.md),
        seeded into <flow_dir>/.claude/skills/<name>/ so they load by the harness's
        own project convention, host-independent (#157).
    :param mcp_files: per-flow MCP yamls, copied into <bundle>/tools/mcp/.
    """

    name: str
    harness: str = "claude-native"
    skills: str | list[str] = "all"
    skill_dirs: list[Path] = field(default_factory=list)
    mcp_files: list[Path] = field(default_factory=list)
