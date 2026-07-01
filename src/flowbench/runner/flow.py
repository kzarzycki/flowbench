"""An flow = one approach under test, expressed as omnigent-bundle data.

Omnigent is always the meta-harness; an flow is nothing but the bundle contents
plus which harness runs them. "baseline", "superpowers", "ADF", "ACE" are all the
same driver path carrying different bundle skills/MCPs — never a separate CLI.
The driver (OmnigentDriver) reads these fields straight into the bundle it builds.
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
