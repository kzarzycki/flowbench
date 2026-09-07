from flowbench.runner.judge import (
    aggregate_scores,
    aggregate_verdicts,
    build_judge_prompt,
    last_json_object,
    parse_scores,
    parse_verdict,
)


def test_parse_verdict_reads_last_winner_and_lines():
    text = (
        "Here is an example format WINNER: A (ignore this one).\n\n"
        "B is stronger: it surfaces the negative-cache eviction.\n"
        "WINNER: B\n"
        "A: solid but missed a corner case\n"
        "B: caught the corner case and asked the question\n"
    )
    v = parse_verdict(text)
    assert v["winner"] == "b"
    assert v["assessments"]["a"] == "solid but missed a corner case"
    assert v["assessments"]["b"] == "caught the corner case and asked the question"
    assert v["prose"].startswith("Here is an example")


def test_parse_verdict_reads_last_a_b_lines_past_example_tail():
    text = (
        "WINNER: A\n"
        "A: example line\n"
        "B: example line\n\n"
        "Actual verdict follows.\n"
        "WINNER: A\n"
        "A: real reasoning for A\n"
        "B: real reasoning for B\n"
    )
    v = parse_verdict(text)
    assert v["assessments"]["a"] == "real reasoning for A"
    assert v["assessments"]["b"] == "real reasoning for B"


def test_parse_verdict_tie_and_case_insensitive():
    assert parse_verdict("blah\nwinner: TIE")["winner"] == "tie"


def test_parse_verdict_missing_tail_is_unknown():
    v = parse_verdict("Both plans look fine, no clear winner stated.")
    assert v["winner"] == "unknown"
    assert v["prose"]


def test_parse_verdict_winner_c_three_way():
    text = "Prose about three plans.\nWINNER: C\nA: ok\nB: ok\nC: best, asked the right questions\n"
    v = parse_verdict(text)
    assert v["winner"] == "c"
    assert v["assessments"]["c"] == "best, asked the right questions"


def test_parse_verdict_assessments_only_for_labels_present():
    v = parse_verdict("WINNER: A\nA: only a has a line\n")
    assert v["assessments"] == {"a": "only a has a line"}
    assert "b" not in v["assessments"]


def test_build_judge_prompt_embeds_all_plans():
    out = build_judge_prompt("JUDGE RUBRIC", [("A", "", "PLAN_A_TEXT"), ("B", "", "PLAN_B_TEXT")])
    assert "JUDGE RUBRIC" in out
    assert "PLAN A" in out and "PLAN_A_TEXT" in out
    assert "PLAN B" in out and "PLAN_B_TEXT" in out
    assert out.index("PLAN_A_TEXT") < out.index("PLAN_B_TEXT")


def test_build_judge_prompt_embeds_transcripts_before_plans():
    out = build_judge_prompt("RUBRIC", [("A", "TRANSCRIPT_A", "PA"), ("B", "TRANSCRIPT_B", "PB")])
    assert "CONVERSATION A" in out and "TRANSCRIPT_A" in out
    assert "CONVERSATION B" in out and "TRANSCRIPT_B" in out
    # rubric, then both conversations, then both plans
    assert out.index("TRANSCRIPT_A") < out.index("TRANSCRIPT_B") < out.index("PA") < out.index("PB")


def test_build_judge_prompt_three_entries_block_order():
    out = build_judge_prompt(
        "RUBRIC",
        [
            ("A", "TRANS_A", "PLAN_A"),
            ("B", "", "PLAN_B"),  # empty transcript -> no CONVERSATION B block
            ("C", "TRANS_C", "PLAN_C"),
        ],
    )
    assert "CONVERSATION A" in out
    assert "CONVERSATION B" not in out
    assert "CONVERSATION C" in out
    # all conversation blocks before all plan blocks
    assert out.index("TRANS_A") < out.index("TRANS_C") < out.index("PLAN_A")
    assert out.index("PLAN_A") < out.index("PLAN_B") < out.index("PLAN_C")


def test_parse_scores_only_present_labels():
    text = "SCORES A: fulfillment=4\nSCORES C: fulfillment=2\n"
    scores = parse_scores(text)
    assert scores == {"a": {"fulfillment": 4}, "c": {"fulfillment": 2}}
    assert "b" not in scores


def test_aggregate_verdicts_plurality_by_name():
    out = aggregate_verdicts(["superpowers", "superpowers", "plain"])
    assert out == {
        "counts": {"superpowers": 2, "plain": 1, "tie": 0, "unknown": 0},
        "winner": "superpowers",
    }


def test_aggregate_verdicts_equal_top_two_is_tie():
    assert aggregate_verdicts(["superpowers", "plain"])["winner"] == "tie"


def test_aggregate_verdicts_three_way_equal_top_is_tie():
    out = aggregate_verdicts(["a", "b", "c"])
    assert out["winner"] == "tie"
    assert out["counts"] == {"a": 1, "b": 1, "c": 1, "tie": 0, "unknown": 0}


def test_aggregate_verdicts_three_way_plurality():
    out = aggregate_verdicts(["a", "a", "b", "c"])
    assert out["winner"] == "a"
    assert out["counts"] == {"a": 2, "b": 1, "c": 1, "tie": 0, "unknown": 0}


def test_aggregate_verdicts_all_unknown_is_tie():
    out = aggregate_verdicts(["unknown", "unknown"])
    assert out == {"counts": {"tie": 0, "unknown": 2}, "winner": "tie"}


def test_aggregate_verdicts_tie_and_unknown_never_win():
    # 'tie' has the highest raw count but winner is still the name plurality
    out = aggregate_verdicts(["tie", "tie", "tie", "superpowers"])
    assert out["winner"] == "superpowers"
    assert out["counts"] == {"tie": 3, "unknown": 0, "superpowers": 1}


def test_aggregate_verdicts_empty_list_is_tie():
    assert aggregate_verdicts([]) == {"counts": {"tie": 0, "unknown": 0}, "winner": "tie"}


def test_aggregate_scores_two_keys():
    means = aggregate_scores(
        [
            {"a": {"design": 3}, "b": {"design": 4}},
            {"a": {"design": 5}, "b": {}},  # second judge omitted B scores
        ]
    )
    assert means["a"]["design"] == 4.0
    assert means["b"]["design"] == 4.0


def test_aggregate_scores_three_keys():
    means = aggregate_scores(
        [
            {"superpowers": {"design": 3}, "plain": {"design": 4}, "codex": {"design": 5}},
            {"superpowers": {"design": 5}, "codex": {"design": 3}},  # trial omitted plain
        ]
    )
    assert means == {
        "superpowers": {"design": 4.0},
        "plain": {"design": 4.0},
        "codex": {"design": 4.0},
    }


def test_parse_scores_and_aggregate():
    text = (
        "prose...\n"
        "SCORES A: fulfillment=4 discovery=5 design=3 scope=4\n"
        "SCORES B: fulfillment=4 discovery=3 design=4 scope=2\n"
        "WINNER: A\nA: ok\nB: ok\n"
    )
    v = parse_verdict(text)
    assert v["scores"]["a"] == {"fulfillment": 4, "discovery": 5, "design": 3, "scope": 4}
    assert v["scores"]["b"]["scope"] == 2
    # judges without SCORES lines stay parseable
    assert parse_verdict("WINNER: B\nA: x\nB: y")["scores"] == {}
    means = aggregate_scores(
        [
            {"a": {"design": 3}, "b": {"design": 4}},
            {"a": {"design": 5}, "b": {}},  # second judge omitted B scores
        ]
    )
    assert means["a"]["design"] == 4.0
    assert means["b"]["design"] == 4.0


def test_last_json_object_braces_in_strings():
    assert last_json_object('x {"a": "}"} y') == {"a": "}"}


def test_last_json_object_escaped_quotes_in_strings():
    assert last_json_object('{"a": "\\""}') == {"a": '"'}
    assert last_json_object('{"c\\"": ""} tail') == {'c"': ""}
    assert last_json_object('{"a": "\\\\"} {"b": "{\\"}"}') == {"b": '{"}'}


def test_last_json_object_prose_outside_strings_with_quotes():
    # a stray quote in prose (depth 0) must not open a string
    assert last_json_object('he said "hi {" then {"score": 3}') == {"score": 3}


def test_last_json_object_prose_before_object():
    assert last_json_object('some prose then {"score": 4}') == {"score": 4}
