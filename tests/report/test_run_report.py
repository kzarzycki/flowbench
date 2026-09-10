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


def test_md_to_html_headers_close_lists_and_numbered_items():
    from flowbench.report.run_report import md_to_html

    out = md_to_html("- one\n- two\n## Head\n1. first\n2. second\n\ntext")
    assert out.split("\n") == [
        "<ul>",
        "<li>one</li>",
        "<li>two</li>",
        "</ul>",
        "<h4>Head</h4>",
        "<ul>",
        "<li>1. first</li>",
        "<li>2. second</li>",
        "</ul>",
        "<p>text</p>",
    ]


def test_flow_card_falls_back_to_session_json_without_flow_stats(tmp_path):
    from flowbench.report.run_report import flow_card

    d = tmp_path / "plain"
    d.mkdir()
    (d / "session.json").write_text(
        json.dumps({"exit_status": "idle", "turns": 3, "duration_s": 12.4, "context_tokens": 1500})
    )
    (d / "plan.md").write_text("# Plan\n\n- step\n")
    (d / "transcript.md").write_text("# Transcript\n\n## user\n\nhi\n")
    meta = {"models": {"plain": "opus"}, "reasoning_effort": {}}  # pre-flow_stats run.json
    card = flow_card("plain", tmp_path, False, meta)
    assert card["exit"] == "idle" and card["turns"] == 3 and card["duration"] == "12s"
    assert card["tokens"] == "1,500" and card["effort"] == "?"
    assert card["deliverable_lines"] == 3  # None in the fallback -> counted from plan.md


def test_flow_card_reads_artifact_lines_from_flow_stats(tmp_path):
    from flowbench.report.run_report import flow_card

    d = tmp_path / "plain"
    d.mkdir()
    (d / "plan.md").write_text("# Plan\n\n- step\n- another\n")
    (d / "transcript.md").write_text("# Transcript\n\n## user\n\nhi\n")
    meta = {
        "models": {"plain": "opus"},
        "reasoning_effort": {"plain": "xhigh"},
        "flow_stats": {
            "plain": {
                "exit_status": "idle",
                "turns": 1,
                "duration_s": 5.0,
                "artifact_lines": 4,
                "context_tokens": 100,
            }
        },
    }
    card = flow_card("plain", tmp_path, False, meta)
    assert card["deliverable_lines"] == 4  # picked up from flow_stats.artifact_lines


def test_flow_card_no_plan_md_returns_empty_instead_of_raising(tmp_path):
    from flowbench.report.run_report import flow_card

    d = tmp_path / "plain"
    d.mkdir()
    (d / "session.json").write_text(
        json.dumps({"exit_status": "idle", "turns": 1, "duration_s": 5.0, "context_tokens": 100})
    )
    (d / "transcript.md").write_text("# Transcript\n\n## user\n\nhi\n")
    meta = {"models": {"plain": "opus"}, "reasoning_effort": {}}  # pre-flow_stats run.json
    card = flow_card("plain", tmp_path, False, meta)
    assert card["deliverable_lines"] == 0
    assert card["deliverable_html"] == ""


# --- the declared deliverable ------------------------------------------------

TRANSCRIPT = "# Transcript\n\n## user\n\nhi\n"


def _flow_meta(*, stats=None, **extra):
    """run.json as the renderer reads it for a single flow `plain`; `deliverable`
    (and its absence) comes in through **extra."""
    return {
        "models": {"plain": "opus"},
        "reasoning_effort": {"plain": "xhigh"},
        "flow_stats": {
            "plain": {
                "exit_status": "idle",
                "turns": 1,
                "duration_s": 5.0,
                "context_tokens": 100,
                **(stats or {}),
            }
        },
        **extra,
    }


def _flow_dir(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "transcript.md").write_text(TRANSCRIPT)
    return d


def test_flow_card_reads_the_declared_deliverable(tmp_path):
    from flowbench.report.run_report import flow_card

    d = _flow_dir(tmp_path)
    (d / "port.sql").write_text("-- ported\nselect 1\n")
    (d / "plan.md").write_text("# a plan nobody declared\n")

    card = flow_card(
        "plain", tmp_path, False, _flow_meta(deliverable="port.sql", stats={"artifact_lines": 2})
    )

    assert card["deliverable_name"] == "port.sql"
    assert card["deliverable_lines"] == 2
    assert "ported" in card["deliverable_html"]
    assert "nobody declared" not in card["deliverable_html"]


def test_flow_card_directory_deliverable_lists_its_files(tmp_path):
    from flowbench.report.run_report import flow_card

    d = _flow_dir(tmp_path)
    (d / "port" / "sub").mkdir(parents=True)
    (d / "port" / "a.py").write_text("x\n")
    (d / "port" / "sub" / "b.py").write_text("y\n")

    card = flow_card(
        "plain",
        tmp_path,
        False,
        # a directory has no artifact_text, so run.json records 0 lines for it
        _flow_meta(deliverable="port", stats={"artifact_lines": 0, "deliverable_path": "port"}),
    )

    assert card["deliverable_name"] == "port"
    assert card["deliverable_lines"] == 3  # header + 2 files
    assert "(port/ — 2 files)" in card["deliverable_html"]
    assert "a.py" in card["deliverable_html"] and "sub/b.py" in card["deliverable_html"]


def test_flow_card_finds_a_directory_the_agent_left_nested(tmp_path):
    from flowbench.report.run_report import flow_card

    d = _flow_dir(tmp_path)
    (d / "work" / "port").mkdir(parents=True)
    (d / "work" / "port" / "a.py").write_text("x\n")

    card = flow_card(
        "plain",
        tmp_path,
        False,
        _flow_meta(
            deliverable="port", stats={"artifact_lines": 0, "deliverable_path": "work/port"}
        ),
    )

    assert card["deliverable_lines"] == 2  # header + 1 file
    assert "(port/ — 1 files)" in card["deliverable_html"]  # labelled by the declared name
    assert "a.py" in card["deliverable_html"]


def test_flow_card_empty_file_deliverable_is_zero_lines_but_named(tmp_path):
    from flowbench.report.run_report import flow_card

    d = _flow_dir(tmp_path)
    (d / "plan.md").write_text("")

    card = flow_card(
        "plain", tmp_path, False, _flow_meta(deliverable="plan.md", stats={"artifact_lines": 0})
    )

    assert card["deliverable_name"] == "plan.md"  # present, so still named
    assert card["deliverable_lines"] == 0
    assert card["deliverable_html"] == ""


def test_flow_card_missing_deliverable_is_zero_lines(tmp_path):
    from flowbench.report.run_report import flow_card

    _flow_dir(tmp_path)  # the flow never wrote port.sql

    card = flow_card(
        "plain", tmp_path, False, _flow_meta(deliverable="port.sql", stats={"artifact_lines": 0})
    )

    assert card["deliverable_name"] == "port.sql"
    assert card["deliverable_lines"] == 0
    assert card["deliverable_html"] == ""


def test_flow_card_with_a_null_deliverable_has_no_panel(tmp_path):
    from flowbench.report.run_report import flow_card

    d = _flow_dir(tmp_path)
    (d / "plan.md").write_text("# not declared, not rendered\n")

    card = flow_card("plain", tmp_path, False, _flow_meta(deliverable=None))

    assert card["deliverable_name"] is None
    assert card["deliverable_lines"] is None  # no line count to show
    assert card["deliverable_html"] == ""


def test_flow_card_without_a_deliverable_key_falls_back_to_plan_md(tmp_path):
    from flowbench.report.run_report import flow_card

    d = _flow_dir(tmp_path)
    (d / "plan.md").write_text("# Plan\n\n- step\n")

    card = flow_card("plain", tmp_path, False, _flow_meta())  # run.json written before this change

    assert card["deliverable_name"] == "plan.md"
    assert card["deliverable_lines"] == 3
    assert "<h3>Plan</h3>" in card["deliverable_html"]  # md_to_html shifts headings by two


def test_report_renders_a_case_without_a_deliverable(tmp_path):
    from flowbench.report.run_report import render_report

    root = tmp_path / "run"
    for name in ("plain", "superpowers"):
        d = root / name
        d.mkdir(parents=True)
        (d / "transcript.md").write_text(TRANSCRIPT)
        (d / "plan.md").write_text("# undeclared\n")
    (root / "judge.md").write_text("# Verdict\n\nWinner: A\n")
    (root / "run.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "case": "todo_app",
                "deliverable": None,
                "labels": {"A": "plain", "B": "superpowers"},
                "winner": "a",
                "models": {"plain": "opus", "superpowers": "opus"},
                "reasoning_effort": {"plain": "high", "superpowers": "high"},
                "flow_stats": {
                    "plain": {"exit_status": "idle", "turns": 2, "duration_s": 3.0},
                    "superpowers": {"exit_status": "idle", "turns": 4, "duration_s": 9.0},
                },
            }
        )
    )

    text = render_report(root).read_text()

    assert "Winner: plain (flow A)" in text
    assert "undeclared" not in text  # no panel for a deliverable the case never declared
    assert "lines)</summary>" not in text
    assert "None" not in text
    assert "scenario" not in text  # the subtitle clause is gone
