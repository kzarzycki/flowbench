"""The two proof flows for the todo task: vanilla baseline vs superpowers.

Both set skills="none" so the host's ~/.claude skills are suppressed and the
comparison is host-independent — the ONLY difference is the superpowers flow
carries the superpowers skill dirs in its bundle. That copied skill set is the
variable under test.
"""

from __future__ import annotations

import re
from pathlib import Path

from flowbench.runner.flow import Flow

_SUPERPOWERS_CACHE = Path.home() / ".claude/plugins/cache/claude-plugins-official/superpowers"
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


def _newest_superpowers_skills() -> Path:
    """Newest `superpowers/<semver>/skills` under the plugin cache. Version dirs
    move on upgrade, so resolve at import and let the resolved path (which carries
    the version) land in the run manifest for traceability."""
    versioned = [
        (tuple(int(n) for n in p.parent.name.split(".")), p)
        for p in _SUPERPOWERS_CACHE.glob("*/skills")
        if _SEMVER.fullmatch(p.parent.name)
    ]
    if not versioned:
        raise FileNotFoundError(f"no superpowers/<semver>/skills under {_SUPERPOWERS_CACHE}")
    return max(versioned)[1]


def _superpowers_skill_dirs() -> list[Path]:
    """The individual skill dirs (each with a SKILL.md) inside the newest
    superpowers release — what the driver copies into <bundle>/skills/<name>/."""
    root = _newest_superpowers_skills()
    return sorted(p for p in root.iterdir() if (p / "SKILL.md").exists())


FLOWS = [
    Flow(name="baseline", harness="claude-native", skills="none"),
    Flow(
        name="superpowers",
        harness="claude-native",
        skills="none",
        skill_dirs=_superpowers_skill_dirs(),
    ),
]


def by_name(name: str) -> Flow:
    for flow in FLOWS:
        if flow.name == name:
            return flow
    raise KeyError(f"unknown flow {name!r}; have {[a.name for a in FLOWS]}")
