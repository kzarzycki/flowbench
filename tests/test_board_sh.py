"""The loop's board contract (issue #143): `board.sh CLOSED` closes an item without
claiming a phase it never reached, and the README states the rule that says why. `gh` is
stubbed on PATH — no test touches the real Project board."""

import os
import re
import subprocess
from pathlib import Path

import pytest

LOOP = Path(__file__).resolve().parents[1] / "engineering-loop"
BOARD = LOOP / "board.sh"
# Field ids come from the script, so a re-keyed board fails loudly instead of passing on
# stale literals. The Done *option* id is anchored below: deriving it from MERGED would
# let both keywords write the same wrong status and still pass.
FIELD = dict(re.findall(r"^(STATUS|PHASE)=(\S+)$", BOARD.read_text(), re.M))
DONE = "c25c871f"
URL = "https://github.com/kzarzycki/flowbench/issues/1"

GH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_LOG"
[ "$1 $2" = "project item-add" ] && echo ITEM1
exit 0
"""


@pytest.fixture
def board(tmp_path: Path):
    """Run board.sh with a recording `gh` and no session identity (the Session field and
    the once-per-session comment are not what this file is about)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (gh := bin_dir / "gh").write_text(GH_STUB)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    env = {
        k: v for k, v in os.environ.items() if k not in {"AGENT_SESSION", "CLAUDE_CODE_SESSION_ID"}
    }
    env.update(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", GH_LOG=str(log))

    def run(phase: str) -> tuple[subprocess.CompletedProcess, list[str]]:
        res = subprocess.run(
            [str(BOARD), URL, phase], env=env, capture_output=True, text=True, cwd=tmp_path
        )
        calls = log.read_text().splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return res, calls

    return run


def edits(calls: list[str], field: str) -> list[str]:
    return [c for c in calls if c.startswith("project item-edit") and f"--field-id {field}" in c]


def test_closed_writes_status_and_leaves_phase(board):
    res, calls = board("CLOSED")
    assert res.returncode == 0, res.stderr
    all_edits = [c for c in calls if c.startswith("project item-edit")]
    assert len(all_edits) == 1
    assert all_edits == edits(calls, FIELD["STATUS"])
    assert f"--single-select-option-id {DONE}" in all_edits[0]
    assert edits(calls, FIELD["PHASE"]) == []


def test_a_real_phase_still_writes_both(board):
    res, calls = board("MERGED")
    assert res.returncode == 0, res.stderr
    fields = [
        c.split("--field-id ")[1].split()[0] for c in calls if c.startswith("project item-edit")
    ]
    assert fields == [FIELD["PHASE"], FIELD["STATUS"]]


def test_unknown_phase_exits_2_before_any_write(board):
    res, calls = board("BOGUS")
    assert res.returncode == 2
    assert "unknown phase: BOGUS" in res.stderr
    assert calls == []  # `item-add` writes too — the guard runs before it


def test_closed_output_reports_status_not_phase(board):
    res, _ = board("CLOSED")
    assert res.stdout.strip() == f"{URL} → Status=Done (Phase unchanged)"


def test_usage_comment_documents_closed():
    """Naming the keyword is not documenting it: the header must carry its meaning."""
    line = next(
        ln for ln in BOARD.read_text().split("set -euo pipefail")[0].splitlines() if "CLOSED" in ln
    )
    assert re.search(r"closed without shipping", line, re.I)
    assert re.search(r"Status Done", line, re.I)
    assert re.search(r"Phase left at the last phase", line, re.I)


def test_the_phase_rule_lives_once_in_the_phases_preamble():
    """The rule `CLOSED` exists for. Current truth once, in the doc that owns it — so
    this asserts placement and uniqueness, not just presence."""
    readme = " ".join((LOOP / "README.md").read_text().split())  # the prose is hard-wrapped
    rule = "a phase is written from the artifact that proves it"
    assert readme.count(rule) == 1
    preamble = readme.split("## Phases ", 1)[1].split("**TRIAGE.**", 1)[0]
    assert rule in preamble
    assert "CLOSED" in preamble
