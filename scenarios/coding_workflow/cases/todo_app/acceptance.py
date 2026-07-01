"""Black-box acceptance of a finished todo workspace. Every check is a fresh
subprocess in the workspace cwd, so file persistence is exercised implicitly."""

from __future__ import annotations

import configparser
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class AcceptanceResult:
    checks: list[CheckResult] = field(default_factory=list)
    app_runs: bool = False

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> int:
        return sum(c.passed for c in self.checks)

    @property
    def score(self) -> float:
        return round(self.passed / self.total, 3) if self.total else 0.0


_SKIP_PARTS = (".git", ".venv", "__pycache__", ".pytest_cache", ".memsearch")


def resolve_app_dir(workspace: Path) -> Path:
    """Directory from which `python -m todo` resolves. The superpowers workflow
    sometimes nests the package (e.g. <ws>/src/todo); find it so acceptance runs
    where the app actually lives, not blindly at the workspace root."""
    ws = Path(workspace)
    if (
        (ws / "todo.py").exists()
        or (ws / "todo" / "__init__.py").exists()
        or (ws / "todo" / "__main__.py").exists()
    ):
        return ws
    for cand in sorted(ws.rglob("todo")):
        if any(p in _SKIP_PARTS for p in cand.parts):
            continue
        if cand.is_dir() and ((cand / "__main__.py").exists() or (cand / "__init__.py").exists()):
            return cand.parent
    for cand in sorted(ws.rglob("todo.py")):
        if not any(p in _SKIP_PARTS for p in cand.parts):
            return cand.parent
    return ws


def _is_marked(line: str) -> bool:
    low = line.lower()
    return ("✓" in line) or ("[x]" in low) or ("done" in low) or ("✔" in line)


def _console_entry(app_dir: Path) -> tuple[str, str] | None:
    """A `module:func` console-script target declared by the app, or None.
    Reads an egg-info entry_points.txt first, then pyproject [project.scripts]."""
    for ep in sorted(app_dir.rglob("entry_points.txt")):
        if any(p in _SKIP_PARTS for p in ep.parts):
            continue
        cp = configparser.ConfigParser()
        try:
            cp.read(ep)
        except configparser.Error:
            continue
        if cp.has_section("console_scripts"):
            for _, target in cp.items("console_scripts"):
                if ":" in target:
                    mod, func = target.split(":", 1)
                    return mod.strip(), func.strip().split()[0]
    pp = app_dir / "pyproject.toml"
    if pp.exists():
        try:
            data = tomllib.loads(pp.read_text())
        except (tomllib.TOMLDecodeError, OSError):
            data = {}
        scripts = (data.get("project") or {}).get("scripts") or {}
        for target in scripts.values():
            if isinstance(target, str) and ":" in target:
                mod, func = target.split(":", 1)
                return mod.strip(), func.strip()
    return None


def resolve_invoker(app_dir: Path) -> list[str]:
    """The argv prefix that runs the app; acceptance args are appended to it.
    Accepts BOTH styles: `python -m todo` when a runnable module exists, else a
    console-script entry point (`todo = pkg.cli:fn`) invoked via a `python -c`
    shim that sets argv and calls the function. A faithful build can ship either."""
    probe = subprocess.run(
        [sys.executable, "-m", "todo"],
        cwd=str(app_dir),
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if "No module named todo.__main__" not in probe.stderr:
        return [sys.executable, "-m", "todo"]
    ep = _console_entry(app_dir)
    if ep:
        mod, func = ep
        shim = (
            f"import sys; sys.argv=['todo']+sys.argv[1:]; "
            f"from {mod} import {func} as _entry; _entry()"
        )
        return [sys.executable, "-c", shim]
    return [sys.executable, "-m", "todo"]


def _run(invoker: list[str], ws: Path, *args: str, timeout: float = 30.0):
    return subprocess.run(
        [*invoker, *args],
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_acceptance(workspace: Path) -> AcceptanceResult:
    workspace = resolve_app_dir(Path(workspace))
    invoker = resolve_invoker(workspace)
    # deterministic start: drop any tasks.json the build left behind
    store = workspace / "tasks.json"
    if store.exists():
        store.unlink()

    res = AcceptanceResult()

    r = _run(invoker, workspace, "add", "buy milk")
    res.app_runs = r.returncode == 0
    res.checks.append(CheckResult("add_first", r.returncode == 0, r.stderr[:200]))

    ok2 = (
        _run(invoker, workspace, "add", "pay rent").returncode == 0
        and _run(invoker, workspace, "add", "call mom").returncode == 0
    )
    res.checks.append(CheckResult("add_rest", ok2))

    out = _run(invoker, workspace, "list").stdout
    all_three = all(t in out for t in ("buy milk", "pay rent", "call mom"))
    res.checks.append(CheckResult("list_shows_all_three", all_three, out[:200]))

    res.checks.append(
        CheckResult("done_first", _run(invoker, workspace, "done", "1").returncode == 0)
    )

    out = _run(invoker, workspace, "list").stdout
    done_line = next((ln for ln in out.splitlines() if "buy milk" in ln), "")
    open_lines = [ln for ln in out.splitlines() if ("pay rent" in ln or "call mom" in ln)]
    # the done task must show a marker AND the still-open tasks must NOT — this
    # rejects an app that prints a constant hint like "(toggle with: done <id>)".
    done_marked = _is_marked(done_line) and not any(_is_marked(ln) for ln in open_lines)
    res.checks.append(CheckResult("done_marker_shown", done_marked, done_line[:200]))

    # fresh process again — persistence (in-memory apps already failed above)
    out = _run(invoker, workspace, "list").stdout
    persisted = all(t in out for t in ("buy milk", "call mom")) and ("buy milk" in out)
    res.checks.append(CheckResult("persists_across_processes", persisted, out[:200]))

    _run(invoker, workspace, "rm", "2")
    out = _run(invoker, workspace, "list").stdout
    removed_only_two = ("pay rent" not in out) and ("buy milk" in out) and ("call mom" in out)
    res.checks.append(CheckResult("rm_removes_only_target", removed_only_two, out[:200]))

    return res
