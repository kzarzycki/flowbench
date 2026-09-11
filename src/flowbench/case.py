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
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from flowbench.flowspec import load_flows
from flowbench.settings import Settings

SCENARIOS_DIR = "scenarios"

# Pinned so the seed commit is a function of the DECLARATION alone: the same
# workspace seeds to the same SHA in every flow dir and every run, which is what
# lets one run-level record in run.json be true for all of them.
SEED_COMMIT_DATE = (
    "2020-01-01T00:00:00Z"  # the form git echoes back, so a test can compare literally
)
SEED_COMMIT_MESSAGE = "chore: seed workspace"


@dataclass(frozen=True)
class Workspace:
    """What a flow's working directory contains before the agent's first turn.

    The default is the EMPTY declaration — an empty directory and no repo — and
    it is a declaration, not a missing one: the engine creates no repo a case did
    not ask for, so whether an agent sets up version control itself stays an
    observable rather than a precondition.

    `git` is the whole of "what history" an in-repo seed can express: one commit
    holding exactly the seed. Richer history needs a cloned ref, which brings a
    network, a cache and credentials with it — a different subsystem.
    """

    seed: str | None = None  # a directory inside the case folder, copied in
    git: bool = False  # the tree is a repo whose single commit is the seed


def seed_workspace(workspace: Workspace, case_dir, flow_dir) -> dict:
    """Materialize `workspace` in `flow_dir` and answer what was done.

    The single seeding step: everything the framework puts in the workspace goes
    through here, against this one declaration, and is recorded the same way.
    Nothing beyond the declaration is implied — an empty `Workspace()` leaves an
    empty directory with no repo.

    Answers `{"seed", "git", "seed_files", "seed_commit"}`, which `run_case`
    writes to `run.json`."""
    case_dir = Path(case_dir).resolve()
    flow_dir = Path(flow_dir)
    flow_dir.mkdir(parents=True, exist_ok=True)

    seed_files = 0
    if workspace.seed is not None:
        src = _seed_dir(workspace.seed, case_dir)
        shutil.copytree(src, flow_dir, dirs_exist_ok=True)
        seed_files = sum(1 for p in src.rglob("*") if p.is_file())

    seed_commit = _seed_commit(flow_dir) if workspace.git else None
    return {
        "seed": workspace.seed,
        "git": workspace.git,
        "seed_files": seed_files,
        "seed_commit": seed_commit,
    }


def _seed_dir(seed: str, case_dir: Path) -> Path:
    """The seed tree, or a `ValueError` naming the case folder and the value. A
    seed is versioned WITH the case, so a path outside the case folder is a
    declaration the case cannot carry, not a convenience."""
    src = (case_dir / seed).resolve()
    if not src.is_relative_to(case_dir):
        raise ValueError(f"{case_dir}: workspace seed {seed!r} escapes the case folder")
    if not src.exists():
        raise ValueError(f"{case_dir}: workspace seed {seed!r} does not exist")
    if not src.is_dir():
        raise ValueError(f"{case_dir}: workspace seed {seed!r} is not a directory")
    return src


def _seed_commit(flow_dir: Path) -> str:
    """Make the seed commit if there is no repo yet, and answer HEAD either way."""

    def run(*args: str) -> subprocess.CompletedProcess:
        # Scrub GIT_* before adding our own: a caller that is itself a git hook
        # exports GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE pointing at the OUTER repo,
        # which would redirect this nested git at it (#49).
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = SEED_COMMIT_DATE
        return subprocess.run(
            # commit.gpgsign off: a signature would make the SHA depend on the
            # operator's key, which is the opposite of the pinned dates' point.
            ["git", "-c", "commit.gpgsign=false", "-C", str(flow_dir), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    if not (flow_dir / ".git").exists():
        run("init", "-q")
        # Local identity, so the commit does not depend on the operator's git config.
        run("config", "user.email", "agent-eval@example.com")
        run("config", "user.name", "agent-eval")
        run("add", "-A")
        # --allow-empty: an empty declaration commits nothing rather than inventing
        # a .gitkeep the case never declared and every scorer must learn to ignore.
        run("commit", "-q", "--allow-empty", "-m", SEED_COMMIT_MESSAGE)
    return run("rev-parse", "HEAD").stdout.strip()


class Case:
    """The runtime contract of one case folder. Subclass it in the folder's
    `case.py` to override any of it; the defaults are a complete case."""

    deliverable: str | None = None
    max_turns: int = 80
    deadline_s: float = 1800.0
    workspace: Workspace = Workspace()

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

        A candidate that is still the seed, byte for byte, is not a deliverable:
        the flow did not produce it. Seeded candidates are dropped BEFORE the
        pick, so an untouched shallow copy cannot hide a modified deeper one.

        The nested pick is ordered — shallowest, then lexicographic — not
        `rglob`'s first yield, which follows `os.scandir` and so varies by
        filesystem. Two nested copies is ordinary (a subagent's working dir holds
        one), and an unordered pick would make the recorded deliverable path, the
        canonical copy and the rendered report differ between machines."""
        if self.deliverable is None:
            return None
        flow_dir = Path(flow_dir)
        top = flow_dir / self.deliverable
        if top.exists() and not self._is_untouched_seed(flow_dir, top):
            return top
        matches = sorted(
            (
                p
                for p in flow_dir.rglob(self.deliverable)
                if not self._is_untouched_seed(flow_dir, p)
            ),
            key=lambda p: (len(p.relative_to(flow_dir).parts), p.as_posix()),
        )
        return matches[0] if matches else None

    def _is_untouched_seed(self, flow_dir: Path, path: Path) -> bool:
        """Did this path come from the seed and stay identical to it? The seed
        tree is already on disk in the case folder, versioned with the case, so
        the comparison needs no manifest and no repo — it holds for a `git=False`
        declaration too."""
        seed = self.workspace.seed
        if seed is None:
            return False
        original = self.case_dir / seed / path.relative_to(flow_dir)
        try:
            return original.is_file() and original.read_bytes() == path.read_bytes()
        except OSError:
            return False

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
