"""The comparative reporter: side-by-side flow table + failure isolation."""

import json
from pathlib import Path

from flowbench.report import compare


def _card(app_runs, acceptance, judge):
    return {
        "objective": {
            "app_runs": app_runs,
            "acceptance": acceptance,
            "clarifying_coverage": 0.8,
            "superpowers_used": True,
            "brainstorming_used": True,
        },
        "judge_low_confidence": judge,
    }


def _write(base: Path, run_id: str, flow: str, card: dict | str):
    d = base / run_id / flow
    d.mkdir(parents=True)
    (d / "scorecard.json").write_text(card if isinstance(card, str) else json.dumps(card))


def test_table_has_one_column_per_arm(tmp_path):
    _write(tmp_path, "r", "baseline", _card(True, 0.7, {"shape_fit": 0.6}))
    _write(tmp_path, "r", "superpowers", _card(True, 0.9, {"shape_fit": 0.85}))
    md = compare.render_compare(tmp_path, "r")
    assert "| metric | baseline | superpowers |" in md
    assert "| acceptance | 0.7 | 0.9 |" in md
    assert "| judge.shape_fit | 0.6 | 0.85 |" in md


def test_missing_scorecard_is_a_failed_column_not_an_abort(tmp_path):
    _write(tmp_path, "r", "baseline", _card(True, 0.7, {"shape_fit": 0.6}))
    _write(tmp_path, "r", "superpowers", "{ not json")  # malformed -> None
    md = compare.render_compare(tmp_path, "r")
    # the good flow still renders...
    assert "| acceptance | 0.7 | FAILED |" in md
    # ...and the failed flow is flagged as not-run in the status row
    assert "| _status_ | ok | FAILED |" in md


def test_judge_error_fails_only_the_judge_rows(tmp_path):
    # a scored flow whose judge couldn't be graded keeps its objective metrics;
    # only the judge rows read FAILED.
    _write(tmp_path, "r", "baseline", _card(True, 0.7, {"error": "empty_grader_completion"}))
    md = compare.render_compare(tmp_path, "r")
    assert "| acceptance | 0.7 |" in md  # objective survives
    assert "| judge.shape_fit | FAILED (empty_grader_completion) |" in md
    assert "_status_" not in md  # flow did run


def test_no_scorecards_found(tmp_path):
    (tmp_path / "r").mkdir()
    assert "no flow scorecards found" in compare.render_compare(tmp_path, "r")
