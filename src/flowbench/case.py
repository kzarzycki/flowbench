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
# A second commit exists only on the path where the SEED brought its own repo: the init branch
# below already sweeps the skills in with `add -A`, so this message appears only when a case
# seeds a repo AND its flows declare skills.
SEED_SKILLS_COMMIT_MESSAGE = "chore: seed flow skills"


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


def seed_workspace(workspace: Workspace, case_dir, flow_dir, skill_dirs=()) -> dict:
    """Materialize `workspace` in `flow_dir` and answer what was done.

    The single seeding step: everything the framework puts in the workspace goes
    through here, against this one declaration, and is recorded the same way.
    Nothing beyond the declaration is implied — an empty `Workspace()` leaves an
    empty directory with no repo.

    `skill_dirs` is the FLOW's contribution, which is why it is an argument rather
    than a `Workspace` field: the declaration is a property of the case and is
    identical for every flow, and skills are exactly the part that differs. They
    land at `<flow_dir>/.claude/skills/<name>/`, where the harness's own convention
    finds them, and they are placed BEFORE the commit so they belong to the seed
    rather than to the agent's diff — which is what scorers read.

    Answers `{"seed", "git", "seed_files", "seed_commit", "skills"}`, which
    `run_case` writes to `run.json`."""
    case_dir = Path(case_dir).resolve()
    flow_dir = Path(flow_dir)
    flow_dir.mkdir(parents=True, exist_ok=True)

    seed_files = 0
    seed_skill_names: set[str] = set()
    seed_has_repo = False
    if workspace.seed is not None:
        src = _seed_dir(workspace.seed, case_dir)
        _reject_workspace_settings(src)
        shutil.copytree(src, flow_dir, dirs_exist_ok=True)
        seed_files = sum(1 for p in src.rglob("*") if p.is_file())
        # Every fact about the seed is read from the SOURCE, never from the
        # materialized flow dir: that dir also holds whatever the last seeding
        # placed and whatever the AGENT then wrote, and neither is the case's
        # declaration. A snapshot taken there would call every declared skill a
        # collision on the second run, and would blame the case for a settings
        # file the agent itself created.
        seed_skills = src / ".claude" / "skills"
        if seed_skills.is_dir():
            seed_skill_names = {p.name for p in seed_skills.iterdir()}
        seed_has_repo = (src / ".git").exists()

    skills = _place_skills(flow_dir, skill_dirs, seed_skill_names)

    # A commit only where the framework owns the history: the declared repo, or a
    # repo the SEED brought. Never a repo the AGENT created — `.git` merely
    # existing in the flow dir is not the engine's to write to.
    needs_commit = workspace.git or (skills and seed_has_repo)
    seed_commit = _seed_commit(flow_dir, bool(skills)) if needs_commit else None
    return {
        "seed": workspace.seed,
        "git": workspace.git,
        "seed_files": seed_files,
        "seed_commit": seed_commit,
        "skills": skills,
    }


def _reject_workspace_settings(seed_src: Path) -> None:
    """A settings file in the SEED is a second, undeclared steering channel.

    Turning the `project` setting source on — which is how a flow's skills load —
    also turns on the workspace's `.claude/settings.json`, and settings files are
    exactly what differ between a `skills: none` flow and a `skills: [project]` one.
    A flow is the full configuration, every knob declared and recorded, so the engine
    asserts the case seeds none rather than silently inheriting one.

    Checked on the seed SOURCE, like every other seed fact: a settings file the AGENT
    wrote mid-run is the agent's doing, and failing a repeat seeding over it would
    blame the case for something the case never declared."""
    for name in ("settings.json", "settings.local.json"):
        path = seed_src / ".claude" / name
        if path.exists():
            raise ValueError(
                f"{path}: a case may not seed a workspace settings file — a flow is "
                "steered only by declared flow fields"
            )


def _place_skills(flow_dir: Path, skill_dirs, seed_skill_names: set[str]) -> list[str]:
    """Copy each flow skill dir under `<flow_dir>/.claude/skills/`, and answer the
    names placed. A name the SEED already carries is a collision the case author has
    to resolve: letting either side win silently would mean a flow ran without the
    bundle it declared."""
    placed: list[str] = []
    for entry in skill_dirs:
        name = Path(entry).name
        if name in placed:
            raise ValueError(
                f"{flow_dir}: two skill_dirs entries are both named {name!r} — one would "
                "silently overwrite the other, so the flow would not get what it declared"
            )
        if name in seed_skill_names:
            raise ValueError(
                f"{flow_dir}: flow skill {name!r} collides with one the workspace seed "
                "already carries — rename the flow's skill or drop it from the seed"
            )
        shutil.copytree(entry, flow_dir / ".claude" / "skills" / name, dirs_exist_ok=True)
        placed.append(name)
    return sorted(placed)


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


def _seed_commit(flow_dir: Path, skills_placed: bool = False) -> str:
    """Make the seed commit if there is no repo yet, and answer HEAD either way.

    When the SEED brought its own repo, the init branch never runs, so skills placed
    into it would stay untracked and land in the agent's own `git add -A`. The second
    branch commits just those, and only when something was actually staged — an
    `--allow-empty` here would manufacture a commit on every repeat run and move the
    SHA the pinned dates exist to fix."""

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        # Scrub GIT_* before adding our own: a caller that is itself a git hook
        # exports GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE pointing at the OUTER repo,
        # which would redirect this nested git at it (#49).
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = SEED_COMMIT_DATE
        return subprocess.run(
            # Neutralise the operator's own git config, which would otherwise
            # reach into the seed: a signature or a hook-rewritten message moves
            # the SHA the pinned dates exist to fix, and autocrlf rewrites the
            # seeded bytes that `find_deliverable` compares against.
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=",
                "-c",
                "core.autocrlf=false",
                "-C",
                str(flow_dir),
                *args,
            ],
            check=check,
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
    elif skills_placed:
        # Scoped to the skills at EVERY step, including the commit: the flow dir may
        # already hold agent work, and an unscoped `commit` would sweep it into a
        # commit labelled as the seed — attributing the agent's output to the
        # framework and corrupting the very diff this placement exists to keep clean.
        run("add", "--", ".claude/skills")
        if run("diff", "--cached", "--quiet", "--", ".claude/skills", check=False).returncode:
            run("commit", "-q", "-m", SEED_SKILLS_COMMIT_MESSAGE, "--", ".claude/skills")
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

        A candidate FILE that is still the seed, byte for byte, is not a
        deliverable: the flow did not produce it. Seeded candidates are dropped
        BEFORE the pick, so an untouched shallow copy cannot hide a modified
        deeper one. A directory deliverable is never dropped — see
        `_is_untouched_seed`.

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
        """Did this FILE come from the seed and stay identical to it? The seed
        tree is already on disk in the case folder, versioned with the case, so
        the comparison needs no manifest and no repo — it holds for a `git=False`
        declaration too.

        Files only, deliberately. Answering it for a directory means reading both
        trees whole, and the directory deliverable exists precisely because a
        ported project is too large to copy (see "Deliverable semantics"). No case
        declares a directory that its own seed also contains; the day one does,
        that is the trigger to pay for the tree compare."""
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
