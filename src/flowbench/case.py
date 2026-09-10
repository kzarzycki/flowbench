"""A case is a folder. The text files (`task.md`, `simulator.md`, `knowledge.md`,
`flows.yaml`, optional `judge.md`) stay the only source of what the agent is told;
an optional `case.py` beside them — or in the nearest ancestor up to the scenarios
root — declares the runtime shape: what proves delivery, how long a flow may run,
what happens before and after it, how it is graded.

Everything has a default, so a text-only folder is already a runnable case."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

from flowbench.flowspec import load_flows
from flowbench.settings import Settings

SCENARIOS_DIR = "scenarios"


class Case:
    """The runtime contract of one case folder. Subclass it in the folder's
    `case.py` to override any of it; the defaults are a complete case."""

    deliverable: str | None = None
    max_turns: int = 80
    deadline_s: float = 1800.0

    def __init__(self, case_dir, settings: Settings | None = None):
        self.case_dir = Path(case_dir).resolve()
        self.name = self.case_dir.name
        self.settings = settings if settings is not None else Settings()

    @property
    def judge_path(self) -> Path:
        """Where the comparative rubric lives; absent means no judge stage."""
        return self.case_dir / "judge.md"

    def validate(self) -> list[str]:
        """The flow names this case benchmarks, in `flows.yaml` order."""
        return [flow["name"] for flow in load_flows(self.case_dir / "flows.yaml")]

    def has_score_override(self) -> bool:
        """Does this case grade a flow on its own? `score` is a real method, so
        only comparing it against the base method can tell."""
        return type(self).score is not Case.score

    def find_deliverable(self, flow_dir) -> Path | None:
        """What proves this flow delivered: the declared path at the flow-dir
        root, else its first nested hit (a subagent's cwd, say), else nothing.
        A case that declares no deliverable never has one.

        The nested pick is ordered — shallowest, then lexicographic — not
        `rglob`'s first yield, which follows `os.scandir` and so varies by
        filesystem. Two nested copies is ordinary (a subagent's working dir holds
        one), and an unordered pick would make the recorded deliverable path, the
        canonical copy and the rendered report differ between machines."""
        if self.deliverable is None:
            return None
        flow_dir = Path(flow_dir)
        top = flow_dir / self.deliverable
        if top.exists():
            return top
        matches = sorted(
            flow_dir.rglob(self.deliverable),
            key=lambda p: (len(p.relative_to(flow_dir).parts), p.as_posix()),
        )
        return matches[0] if matches else None

    async def setup(self, flow, flow_dir) -> None:
        """Runs the case folder's `setup.sh` when it has one."""
        self._script("setup.sh", flow, flow_dir)

    async def teardown(self, flow, flow_dir) -> None:
        """Runs the case folder's `teardown.sh` when it has one."""
        self._script("teardown.sh", flow, flow_dir)

    async def score(self, flow, flow_dir, session) -> dict | None:
        """The flow's scorecard, or None when nothing grades a flow on its own."""
        return None

    def _script(self, name: str, flow, flow_dir) -> None:
        """`<case_dir>/<name>` with the case folder as cwd and the flow in the
        environment; absent is a no-op, non-zero raises."""
        script = self.case_dir / name
        if not script.is_file():
            return
        subprocess.run(
            ["bash", str(script)],
            cwd=self.case_dir,
            check=True,
            env={
                **os.environ,
                "FLOW_NAME": flow["name"],
                "FLOW_DIR": str(Path(flow_dir).resolve()),
            },
        )


def scenarios_root(case_dir) -> Path:
    """The last folder discovery may look in: the case folder itself or its first
    ancestor named `scenarios`, else the filesystem root."""
    case_dir = Path(case_dir).resolve()
    for folder in (case_dir, *case_dir.parents):
        if folder.name == SCENARIOS_DIR:
            return folder
    return Path(case_dir.anchor)


def load_case(case_dir, settings: Settings | None = None) -> Case:
    """The case at `case_dir`: the single `Case` subclass of the nearest `case.py`
    from the folder up to the scenarios root, or a plain `Case` when there is none."""
    case_dir = Path(case_dir).resolve()
    path = _find_case_py(case_dir)
    cls = Case if path is None else _load_case_class(path)
    return cls(case_dir, settings=settings)


def _walk(case_dir: Path) -> Iterator[Path]:
    """The case folder, then each ancestor, stopping after the scenarios root."""
    root = scenarios_root(case_dir)
    for folder in (case_dir, *case_dir.parents):
        yield folder
        if folder == root:
            return


def _find_case_py(case_dir: Path) -> Path | None:
    for folder in _walk(case_dir):
        candidate = folder / "case.py"
        if candidate.is_file():
            return candidate
    return None


def _load_case_class(path: Path) -> type[Case]:
    """Import `path` under a module name keyed by that path, so two scenarios'
    `case.py` files in one process cannot shadow each other, and return the one
    `Case` subclass it defines."""
    slug = re.sub(r"\W+", "_", path.parent.name)
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    module_name = f"flowbench._case_{slug}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    found = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Case) and obj is not Case
    ]
    if len(found) != 1:
        raise ValueError(f"{path}: needs exactly one Case subclass, found {len(found)}")
    return found[0]
