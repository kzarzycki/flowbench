"""One persistent directory per run, holding inputs (the case) and every output.
Nothing is torn down — the user inspects the built app afterward."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunDir:
    root: Path
    workspace: Path
    case: Path


def prepare_run_dir(base: Path, run_id: str, case_src: Path) -> RunDir:
    root = Path(base) / run_id
    root.mkdir(parents=True, exist_ok=True)
    case = root / "case"
    if not case.exists():
        shutil.copytree(case_src, case)
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return RunDir(root=root, workspace=workspace, case=case)


def write_outputs(run: RunDir, **artifacts) -> None:
    for name, obj in artifacts.items():
        (run.root / f"{name}.json").write_text(json.dumps(obj, indent=2, default=str))


def write_run_md(run: RunDir, summary: dict) -> None:
    lines = [
        "# Run summary",
        "",
        "```json",
        json.dumps(summary, indent=2, default=str),
        "```",
        "",
        f"- workspace: `{run.workspace}`",
        f"- case: `{run.case}`",
        "",
    ]
    (run.root / "run.md").write_text("\n".join(lines))
