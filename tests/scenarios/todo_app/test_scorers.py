"""Phase detection + judge parsing + scorer wrappers — offline."""

from scenarios.coding_workflow.cases.todo_app import scorers
from scenarios.coding_workflow.cases.todo_app.fixtures import sessions


def _workspace_with(tmp_path, *, spec=False, plan=False, app=False, tests=False):
    ws = tmp_path / "ws"
    ws.mkdir()
    if spec:
        d = ws / "docs/superpowers/specs"
        d.mkdir(parents=True)
        (d / "s.md").write_text("x")
    if plan:
        d = ws / "docs/superpowers/plans"
        d.mkdir(parents=True)
        (d / "p.md").write_text("x")
    if app:
        d = ws / "todo"
        d.mkdir()
        (d / "__main__.py").write_text("print('hi')")
    if tests:
        d = ws / "tests"
        d.mkdir()
        (d / "test_todo.py").write_text("def test_x(): pass")
    return ws


def test_detect_phases_full(tmp_path):
    ws = _workspace_with(tmp_path, spec=True, plan=True, app=True, tests=True)
    ph = scorers.detect_phases(ws, sessions.FULL_WORKFLOW, app_runs=True)
    assert ph["spec_written"] and ph["plan_written"]
    assert ph["implemented"] and ph["verified"]
    assert ph["brainstormed"] and ph["reviewed"]


def test_detect_phases_skipped(tmp_path):
    ws = _workspace_with(tmp_path)  # nothing on disk
    ph = scorers.detect_phases(ws, sessions.SKIPPED_PHASES, app_runs=False)
    assert not ph["spec_written"] and not ph["plan_written"]
    assert not ph["reviewed"] and not ph["implemented"]


def test_parse_judge_valid():
    v = scorers.parse_judge_json(
        'prose {"shape_fit":0.9,"clarifying_quality":0.8,'
        '"workflow_adherence":1.0,"rationale":"good"} tail'
    )
    assert v["shape_fit"] == 0.9 and v["rationale"] == "good"


def test_parse_judge_unparseable_is_none():
    assert scorers.parse_judge_json("no json here") is None
    assert scorers.parse_judge_json('{"shape_fit": "NaN-ish"}') is None  # non-numeric


class _StubGrader:
    def __init__(self, reply):
        self.reply, self.seen = reply, None

    async def generate(self, prompt):
        self.seen = prompt

        class _Out:
            completion = self.reply

        return _Out()


async def test_judge_build_returns_scores():
    stub = _StubGrader(
        '{"shape_fit":0.9,"clarifying_quality":0.7,"workflow_adherence":0.8,"rationale":"solid"}'
    )
    v, reason = await scorers.judge_build(
        shape="SHAPE",
        code="THECODE",
        acceptance={"score": 1.0},
        transcript="THETRANSCRIPT",
        grader_model=stub,
    )
    assert v["shape_fit"] == 0.9 and "solid" in reason
    # the judge must see BOTH the real code and the full transcript (BUG-J fix)
    assert "SHAPE" in stub.seen and "THECODE" in stub.seen and "THETRANSCRIPT" in stub.seen


async def test_judge_build_unparseable_is_unscored():
    stub = _StubGrader("looks fine")
    v, reason = await scorers.judge_build(
        shape="S", code="C", acceptance={}, transcript="", grader_model=stub
    )
    assert v is None and "unparseable" in reason


class _SeqGrader:
    """Returns a different completion per call (to exercise retries)."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    async def generate(self, prompt):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1

        class _Out:
            completion = reply

        return _Out()


async def test_judge_build_retries_past_an_empty_completion():
    # the throttling case: the grader returns "" once (no API error, so Inspect's own
    # retry never fires), then a valid object. We must recover, not silently nan.
    grader = _SeqGrader(
        ["", '{"shape_fit":0.8,"clarifying_quality":0.6,"workflow_adherence":0.7,"rationale":"ok"}']
    )
    v, reason = await scorers.judge_build(
        shape="S", code="C", acceptance={}, transcript="", grader_model=grader, attempts=3
    )
    assert v is not None and v["shape_fit"] == 0.8
    assert grader.calls == 2  # one empty, one good


async def test_judge_build_reports_empty_completion_after_all_attempts():
    grader = _SeqGrader([""])  # always empty
    v, reason = await scorers.judge_build(
        shape="S", code="C", acceptance={}, transcript="", grader_model=grader, attempts=3
    )
    assert v is None and reason == "empty_grader_completion"
    assert grader.calls == 3  # exhausted the retries, labeled the failure


def test_skills_invoked_scrapes_skill_tool_calls():
    # the SUT's Skill tool calls are captured as function_call items; this is the
    # ground-truth proof the superpowers workflow loaded.
    used = scorers.skills_invoked(sessions.FULL_WORKFLOW)
    assert used == ["superpowers:brainstorming", "superpowers:writing-plans"]
    assert scorers.skills_invoked(sessions.SKIPPED_PHASES) == []


def test_skills_report_flags_superpowers_and_brainstorming():
    r = scorers.skills_report(sessions.FULL_WORKFLOW)
    assert r["superpowers_used"] is True and r["brainstorming_used"] is True
    assert r["invoked"] == ["superpowers:brainstorming", "superpowers:writing-plans"]
    skipped = scorers.skills_report(sessions.SKIPPED_PHASES)
    assert skipped["superpowers_used"] is False and skipped["brainstorming_used"] is False


def test_detect_phases_trusts_brainstorming_skill_call(tmp_path):
    # brainstormed must be True purely from the Skill call, even if the agent asked
    # no literal "?" question and wrote no spec yet.
    ws = tmp_path / "ws"
    ws.mkdir()
    session = {
        "items": [
            {
                "type": "function_call",
                "name": "Skill",
                "arguments": '{"skill":"superpowers:brainstorming"}',
            },
            {"type": "message", "role": "assistant", "content": "Let me think about this."},
        ]
    }
    ph = scorers.detect_phases(ws, session, app_runs=False)
    assert ph["brainstormed"] is True


def test_transcript_dedups_and_keeps_early_turns():
    # omnigent echoes each message twice; dedup must collapse it, and the early
    # clarifying turn must survive into the judge transcript (BUG-J / BUG-P2).
    session = {
        "items": [
            {"type": "message", "role": "user", "content": "build a todo app"},
            {"type": "message", "role": "user", "content": "build a todo app"},  # echo
            {"type": "message", "role": "assistant", "content": "Where should tasks be stored?"},
            {"type": "message", "role": "assistant", "content": "Where should tasks be stored?"},
        ]
    }
    msgs = scorers._messages(session)
    assert len(msgs) == 2  # dedup collapsed both echoes
    judge_txt = scorers.transcript_for_judge(session)
    assert "Where should tasks be stored?" in judge_txt  # early clarifying kept


def test_messages_skips_task_notification_injections():
    # Fix D: Claude Code surfaces sub-agent completions as role=user
    # `<task-notification>` items; they're harness control, not conversation, and
    # must not reach the judge transcript or be counted as user turns.
    session = {
        "items": [
            {"type": "message", "role": "user", "content": "build a todo app"},
            {
                "type": "message",
                "role": "user",
                "content": "<task-notification>subagent finished</task-notification>",
            },
            {"type": "message", "role": "assistant", "content": "done"},
        ]
    }
    msgs = scorers._messages(session)
    assert [r for r, _ in msgs] == ["user", "assistant"]
    assert all("task-notification" not in t for _, t in msgs)
    assert "task-notification" not in scorers.transcript_for_judge(session)


def test_implemented_true_for_single_module_app(tmp_path):
    # run2 regression: a single todo.py (no __main__.py) is a valid implementation.
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "todo.py").write_text("print('hi')")
    ph = scorers.detect_phases(ws, {"items": []}, app_runs=True)
    assert ph["implemented"] is True


def test_clarifying_coverage_counts_asked_topics():
    from scenarios.coding_workflow.cases.todo_app import task

    # the SUT asked about storage and persistence, nothing else.
    session = {
        "items": [
            {
                "type": "message",
                "role": "assistant",
                "content": "Where should tasks be stored — a JSON file or sqlite?",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": "Should they persist across runs or just in memory?",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": "Here is the finished app.",
            },  # statement, not a question
        ]
    }
    cov = scorers.clarifying_coverage(session, task.UNDERSPECIFIED_TOPICS)
    assert cov["asked"]["storage_format"] is True
    assert cov["asked"]["persistence"] is True
    assert cov["asked"]["done_handling"] is False  # never asked
    assert 0.0 < cov["score"] < 1.0


def test_clarifying_coverage_uses_word_boundaries_not_substrings():
    from scenarios.coding_workflow.cases.todo_app import task

    # the live false-positive: a `list`-behaviour question that says "incomplete"
    # must NOT count as asking about done-handling (keyword "complete"). Likewise a
    # word like "performance" must not trip "form" anywhere.
    session = {
        "items": [
            {
                "type": "message",
                "role": "assistant",
                "content": "Should `list` show all items (done + incomplete), or something else?",
            },
        ]
    }
    cov = scorers.clarifying_coverage(session, task.UNDERSPECIFIED_TOPICS)
    assert cov["asked"]["done_handling"] is False, (
        "'complete' inside 'incomplete' must not count as a done-handling question"
    )
    # but the genuine whole word does count
    session2 = {
        "items": [
            {
                "type": "message",
                "role": "assistant",
                "content": "Should `done` mark an item complete, or delete it?",
            },
        ]
    }
    assert (
        scorers.clarifying_coverage(session2, task.UNDERSPECIFIED_TOPICS)["asked"]["done_handling"]
        is True
    )


def test_clarifying_coverage_zero_when_no_questions():
    from scenarios.coding_workflow.cases.todo_app import task

    session = {
        "items": [
            {
                "type": "message",
                "role": "assistant",
                "content": "Done. Built it with JSON storage.",
            },
        ]
    }
    cov = scorers.clarifying_coverage(session, task.UNDERSPECIFIED_TOPICS)
    assert cov["score"] == 0.0  # asserting in a statement is not asking


def test_collect_code_reads_sources(tmp_path):
    ws = tmp_path / "ws"
    (ws / "todo").mkdir(parents=True)
    (ws / "todo" / "__main__.py").write_text("MAIN_MARKER = 1")
    code = scorers.collect_code(ws)
    assert "MAIN_MARKER = 1" in code and "__main__.py" in code
