import json

from flowbench.report.run_report import render_aggregate_report


def _aggregate_dir(tmp_path, *, winner, counts, score_means, flows, trial_winner_flows):
    """Hand-built aggregate run dir: run.json only (renderer must not need more)."""
    root = tmp_path / "agg"
    root.mkdir()
    meta = {
        "run_id": "agg",
        "case": "todo_app",
        "n": len(trial_winner_flows),
        "flows": flows,
        "trials": [
            {"trial": f"trial-{k:02d}", "winner_flow": wf}
            for k, wf in enumerate(trial_winner_flows, 1)
        ],
        "counts": counts,
        "winner": winner,
        "score_means": score_means,
    }
    (root / "run.json").write_text(json.dumps(meta))
    return root


def test_aggregate_report_tie_no_scores(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="tie",
        counts={"superpowers": 1, "plain": 1, "tie": 0, "unknown": 0},
        score_means={},
        flows=["superpowers", "plain"],
        trial_winner_flows=["superpowers", "plain"],
    )
    out = render_aggregate_report(root)
    text = out.read_text()
    assert out == root / "report.html"
    assert "flowbench aggregate report" in text
    assert "Tie 1–1" in text
    assert "Score means" not in text  # both sides empty -> section omitted
    assert 'href="trial-01/report.html"' in text
    assert 'href="trial-02/report.html"' in text


def test_aggregate_report_winner_and_scores(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="superpowers",
        counts={"superpowers": 2, "plain": 0, "tie": 0, "unknown": 0},
        score_means={
            "superpowers": {"fulfillment": 5.0, "discovery": 4.5},
            "plain": {"fulfillment": 4.0, "discovery": 3.5},
        },
        flows=["superpowers", "plain"],
        trial_winner_flows=["superpowers", "superpowers"],
    )
    text = render_aggregate_report(root).read_text()
    assert "superpowers wins 2–0 (n=2)" in text
    assert "Score means" in text
    assert "4.5" in text and "3.5" in text
    assert "superpowers" in text and "plain" in text


def test_aggregate_report_shows_nonzero_tie_unknown_counts(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="superpowers",
        counts={"superpowers": 2, "plain": 1, "tie": 1, "unknown": 0},
        score_means={},
        flows=["superpowers", "plain"],
        trial_winner_flows=["superpowers", "superpowers", "plain", "tie"],
    )
    text = render_aggregate_report(root).read_text()
    assert "superpowers wins 2–1 (n=4)" in text
    assert "1 tie" in text
    assert "unknown" not in text.split("<footer>")[0]  # zero counts stay hidden


def test_aggregate_report_three_flows_no_keyerror(tmp_path):
    root = _aggregate_dir(
        tmp_path,
        winner="codex",
        counts={"superpowers": 1, "plain": 0, "codex": 2, "tie": 0, "unknown": 0},
        score_means={
            "superpowers": {"design": 3.0},
            "plain": {"design": 2.0},
            "codex": {"design": 5.0},
        },
        flows=["superpowers", "plain", "codex"],
        trial_winner_flows=["codex", "superpowers", "codex"],
    )
    text = render_aggregate_report(root).read_text()
    assert "codex wins 2–1–0 (n=3)" in text
    assert "superpowers" in text and "plain" in text and "codex" in text
