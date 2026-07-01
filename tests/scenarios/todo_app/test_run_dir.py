"""Persistent run-dir layout."""

import json
from pathlib import Path

from flowbench.runner.run_dir import prepare_run_dir, write_outputs, write_run_md

CASE = Path(__file__).parents[3] / "scenarios/coding_workflow/cases/todo_app/case"


def test_prepare_copies_case_and_makes_workspace(tmp_path):
    rd = prepare_run_dir(tmp_path, "run-001", CASE)
    assert rd.root == tmp_path / "run-001"
    assert (rd.case / "envisioned-shape.md").exists()  # case copied in
    assert rd.workspace.is_dir()  # workspace ready


def test_write_outputs_and_run_md(tmp_path):
    rd = prepare_run_dir(tmp_path, "run-002", CASE)
    write_outputs(
        rd,
        normalized={"sut": "claude"},
        acceptance={"score": 1.0},
        judge={"shape_fit": 0.9},
        scorecard={"acceptance": 1.0},
    )
    assert json.loads((rd.root / "normalized.json").read_text())["sut"] == "claude"
    assert json.loads((rd.root / "scorecard.json").read_text())["acceptance"] == 1.0
    write_run_md(rd, {"acceptance": 1.0, "phases": {"spec_written": True}})
    md = (rd.root / "run.md").read_text()
    assert "acceptance" in md and "spec_written" in md
