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


def check_gradable(case: Case) -> list[str]:
    """The case's flow names, once something can grade them: a `judge.md` needs two
    flows to compare, and a lone flow needs a `score()` override. A run that could
    produce no verdict at all is a load error, not a spent session.

    Load-time in both senses — `load_case` raises for a folder that already has a
    `flows.yaml`, and the runner raises again before it builds a factory."""
    flows = case.validate()
    if len(flows) < 2 and case.judge_path.exists():
        raise ValueError(
            f"{case.case_dir}/judge.md needs 2+ flows to compare, flows.yaml has {len(flows)}"
        )
    if len(flows) < 2 and not case.has_score_override():
        raise ValueError(
            f"{case.case_dir}: nothing grades this case — one flow and no score() override "
            "(add a second flow to compare, or override Case.score)"
        )
    return flows


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
    if path is None:
        cls = Case
    else:
        _make_scenarios_importable(case_dir)
        cls = _load_case_class(path)
    case = cls(case_dir, settings=settings)
    if (case_dir / "flows.yaml").is_file():
        # No flows file: there is no flow list to check yet, and the runner raises
        # when it reads one that isn't there.
        check_gradable(case)
    return case


def _make_scenarios_importable(case_dir: Path) -> None:
    """Put the folder that holds `scenarios/` at the front of `sys.path`, so a
    `case.py` can import its siblings by package path (`from scenarios.x import y`).

    Nothing else does it: under pytest the checkout root is already there, but the
    installed console script's `sys.path[0]` is the script's own directory and the
    cwd is never added — so `flowbench run scenarios/…/todo_app` would fail at
    `import scenarios`. A case with no `scenarios` ancestor has no package path to
    resolve and adds nothing."""
    root = scenarios_root(case_dir)
    if root.name != SCENARIOS_DIR:
        return
    parent = str(root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


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
    # Compile the file's own text instead of `spec.loader.exec_module(module)`:
    # CPython invalidates a cached `.pyc` on `(source mtime-to-the-second, size)`,
    # so a same-size edit inside one second is served stale from `__pycache__` —
    # and `flowbench run --rescore` straight after editing a case is exactly that.
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    # `__module__` is the filter, not `is not Case`: a `case.py` may legitimately
    # import a shared base or another scenario's class, and only the subclass this
    # file *defines* is the case. Counting the imports too made a sibling import
    # read as "found 2", and a file that only imported one wrongly pass.
    found = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Case) and obj.__module__ == module_name
    ]
    if len(found) != 1:
        raise ValueError(f"{path}: needs exactly one Case subclass, found {len(found)}")
    return found[0]
