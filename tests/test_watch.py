import json
import os
from pathlib import Path

import pytest

from flowbench.types import TurnStatus
from flowbench.watch import RunWatch, follow


def _runs_root(tmp_path, case: str = "todo_app", run_id: str = "todo-x") -> Path:
    """`<runs_root>/<case>/<run_id>` — the layout `RunWatch.locate` reads a run id
    in, and the one it derives the `omni_project` label from."""
    root = tmp_path / "runs"
    (root / case / run_id).mkdir(parents=True)
    return root


def test_run_watch_tick_events(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("boot line\n")
    runs_root = _runs_root(tmp_path)
    run_root = runs_root / "todo_app" / "todo-x"
    w = RunWatch("todo-x", runs_root=runs_root, server_log=log)
    w._last_assistant_text = lambda sid: ""  # keep the suite off the network (#131 read)
    w._run_sessions = lambda: [
        {
            "id": "conv_aaa",
            "status": TurnStatus.RUNNING,
            "title": "flow: plain",
            "labels": {"omni_project": "todo_app/todo-x"},
        },
    ]
    assert w.tick() == []  # baseline: pre-existing log ignored, all healthy

    # a permission prompt for the run's session + an unrelated warning
    with log.open("a") as f:
        f.write("POST /v1/sessions/conv_aaa/hooks/permission-request 200\n")
        f.write("WARNING something about conv_zzz\n")
    events = w.tick()
    assert len(events) == 1 and events[0].startswith("PERMISSION PROMPT (RUN)")

    # session flips to failed -> one event, not repeated
    w._run_sessions = lambda: [
        {
            "id": "conv_aaa",
            "status": TurnStatus.FAILED,
            "title": "flow: plain",
            "labels": {"omni_project": "todo_app/todo-x"},
        },
    ]
    assert any(e.startswith("SESSION FAILED") for e in w.tick())
    assert w.tick() == []

    # trial completion fires once; run completion via run_complete()
    trial = run_root / "trial-01"
    trial.mkdir()
    (trial / "run.json").write_text(json.dumps({"winner_flow": "plain", "artifact_missing": []}))
    events = w.tick()
    assert any(e == "TRIAL DONE: trial-01 winner=plain missing=[]" for e in events)
    assert w.tick() == []

    # a case with no artifact_missing key (artifact_name=None) omits the segment
    trial2 = run_root / "trial-02"
    trial2.mkdir()
    (trial2 / "run.json").write_text(json.dumps({"winner_flow": "plain"}))
    events = w.tick()
    assert any(e == "TRIAL DONE: trial-02 winner=plain" and "missing=" not in e for e in events)

    assert w.run_complete() is None
    (run_root / "run.json").write_text("{}")
    assert w.run_complete() is not None


def test_run_watch_log_sources_missing_and_rotated(tmp_path):
    log = tmp_path / "server.log"  # does not exist yet
    w = RunWatch("r", runs_root=_runs_root(tmp_path, "s", "r"), server_log=log)
    assert w._new_log_lines() == []
    log.write_text("a\nb\n")
    assert w._new_log_lines() == ["a", "b"]
    log.write_text("c\n")  # shorter than the last position -> rotated, re-read from 0
    assert w._new_log_lines() == ["c"]


def test_run_watch_sessions_filters_by_project_and_survives_server_errors(
    tmp_path, monkeypatch, caplog
):
    import http.client
    import io
    import logging
    import urllib.request

    from flowbench import watch as watch_mod

    w = RunWatch("r", runs_root=_runs_root(tmp_path, "s", "r"), server_log=watch_mod.SERVER_LOG)
    payload = {
        "data": [
            {"id": "a", "labels": {"omni_project": "s/r"}},
            {"id": "b", "labels": {"omni_project": "other/r"}},
            {"id": "c"},
        ]
    }

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout: _Resp(json.dumps(payload).encode())
    )
    assert [s["id"] for s in w._run_sessions()] == ["a"]

    def _boom(url, timeout):
        raise OSError("down")

    caplog.set_level(logging.DEBUG, logger="flowbench.watch")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert w._run_sessions() == []
    records = [
        r for r in caplog.records if r.name == "flowbench.watch" and r.levelno == logging.DEBUG
    ]
    assert len(records) == 1
    assert "down" in records[0].getMessage()

    def _http_boom(url, timeout):
        raise http.client.HTTPException("bad status line")

    monkeypatch.setattr(urllib.request, "urlopen", _http_boom)
    assert w._run_sessions() == []  # HTTPException

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: _Resp(b"<html>"))
    assert w._run_sessions() == []  # not JSON: json.load raises ValueError

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: _Resp(b"[]"))
    assert w._run_sessions() == []  # a JSON list: .get raises AttributeError

    def _foreign_boom(url, timeout):
        raise RuntimeError("driver bug")

    monkeypatch.setattr(urllib.request, "urlopen", _foreign_boom)
    with pytest.raises(RuntimeError, match="driver bug"):
        w._run_sessions()


def test_run_watch_reports_server_errors_touching_run_sessions(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("")
    w = RunWatch("r", runs_root=_runs_root(tmp_path, "s", "r"), server_log=log)
    w._last_assistant_text = lambda sid: ""  # offline
    w._run_sessions = lambda: [{"id": "conv_1", "status": TurnStatus.RUNNING, "title": "flow: x"}]
    log.write_text("ERROR runner conv_1 exploded\nERROR unrelated conv_9\n")
    events = w.tick()
    assert len(events) == 1 and events[0].startswith("SERVER ERROR runner conv_1")


def test_run_watch_reports_stalls_once_per_transition(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.watch.time.time", lambda: 1000.0)
    w = RunWatch(
        "r",
        runs_root=_runs_root(tmp_path, "s", "r"),
        server_log=tmp_path / "none.log",
        stall_s=300,
    )
    sess = {"id": "c1", "status": TurnStatus.RUNNING, "title": "flow: x", "updated_at": 900}
    w._run_sessions = lambda: [sess]
    w._last_assistant_text = lambda sid: ""  # offline
    assert w.tick() == []  # fresh heartbeat, no prompt

    sess["pending_elicitations_count"] = 1
    assert w.tick() == ["STALLED (prompt): flow: x (c1)"]
    assert w.tick() == []  # unchanged: no repeat

    sess["pending_elicitations_count"] = 0
    sess["updated_at"] = 600  # 400 s silent while running
    assert w.tick() == []  # still stalled, reason changed but no new transition
    sess["status"] = TurnStatus.IDLE
    assert w.tick() == []  # recovered
    sess["status"] = TurnStatus.RUNNING
    assert w.tick() == ["STALLED (no progress 400s): flow: x (c1)"]


_BANNER = "You've hit your session limit · resets 6:40pm (Europe/Zurich)"  # s025p2-620b16b


def _watch(tmp_path, last_text):
    log = tmp_path / "server.log"
    log.write_text("")
    runs_root = _runs_root(tmp_path, "todo_app", "r1")
    w = RunWatch("r1", runs_root=runs_root, server_log=log)
    w._run_sessions = lambda: [
        {
            "id": "conv_q",
            "status": TurnStatus.FAILED,
            "title": "flow: superpowers",
            "labels": {"omni_project": "todo_app/r1"},
        },
    ]
    w._last_assistant_text = lambda sid: last_text
    return w


def test_run_watch_quota_banner_once(tmp_path):
    # #131: one QUOTA line per session carrying the banner, not one per tick
    w = _watch(tmp_path, _BANNER)
    events = w.tick()
    quota = [e for e in events if e.startswith("QUOTA:")]
    assert quota == [f"QUOTA: flow: superpowers (conv_q) {_BANNER}"]
    assert not any(e.startswith("QUOTA:") for e in w.tick())


def test_run_watch_reads_items_only_when_the_session_moved(tmp_path):
    # the item read is one HTTP call per session per CHANGE, not per tick
    reads = []
    w = _watch(tmp_path, "WINNER: B")
    sess = w._run_sessions()[0]
    sess["updated_at"] = 900
    w._run_sessions = lambda: [sess]
    w._last_assistant_text = lambda sid: reads.append(sid) or "WINNER: B"
    w.tick()
    w.tick()
    assert reads == ["conv_q"]
    sess["updated_at"] = 950
    w.tick()
    assert reads == ["conv_q", "conv_q"]


@pytest.mark.parametrize("last_text", ["WINNER: B", ""])
def test_run_watch_no_quota_for_replies_or_unreadable_items(tmp_path, last_text):
    w = _watch(tmp_path, last_text)
    assert not any(e.startswith("QUOTA:") for e in w.tick())


class _Resp:
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _watch_plain(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("")
    runs_root = _runs_root(tmp_path, "todo_app", "r1")
    return RunWatch("r1", runs_root=runs_root, server_log=log)


@pytest.mark.parametrize(
    "item, expected",
    [
        (
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": _BANNER}],
            },
            _BANNER,
        ),
        ({"type": "message", "role": "user", "content": _BANNER}, ""),  # the sim's inject
        ({"type": "function_call", "name": "Bash"}, ""),
    ],
)
def test_last_assistant_text_reads_only_an_assistant_message(tmp_path, monkeypatch, item, expected):
    urls = []

    def fake_urlopen(url, timeout=None):
        urls.append(url)
        return _Resp({"object": "list", "data": [item]})

    monkeypatch.setattr("flowbench.watch.urllib.request.urlopen", fake_urlopen)
    assert _watch_plain(tmp_path)._last_assistant_text("conv_q") == expected
    assert urls == ["http://127.0.0.1:6767/v1/sessions/conv_q/items?limit=1&order=desc"]


def test_last_assistant_text_read_failure_is_empty(tmp_path, monkeypatch):
    def failing_urlopen(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("flowbench.watch.urllib.request.urlopen", failing_urlopen)
    assert _watch_plain(tmp_path)._last_assistant_text("conv_q") == ""


# --- locating a run by id ---------------------------------------------------


def test_run_watch_locates_the_run_and_derives_the_project(tmp_path):
    runs_root = _runs_root(tmp_path, "feature_flag_service", "r1")
    (runs_root / "other_case" / "r2").mkdir(parents=True)  # a neighbour, same root

    located = RunWatch.locate("r1", runs_root)

    assert located == runs_root / "feature_flag_service" / "r1"
    w = RunWatch("r1", runs_root=runs_root, server_log=tmp_path / "none.log")
    assert w.run_root == located
    # the label every writer of the run uses, read back off the located path
    assert w.project == "feature_flag_service/r1"


def test_run_watch_locate_rejects_missing_and_ambiguous(tmp_path):
    runs_root = _runs_root(tmp_path, "case_a", "r1")

    with pytest.raises(ValueError, match=r"no run dir") as missing:
        RunWatch.locate("nope", runs_root)
    assert str(runs_root / "*" / "nope") in str(missing.value)

    (runs_root / "case_b" / "r1").mkdir(parents=True)
    with pytest.raises(ValueError, match=r"matches 2 cases") as ambiguous:
        RunWatch("r1", runs_root=runs_root, server_log=tmp_path / "none.log")
    for case in ("case_a", "case_b"):
        assert str(runs_root / case / "r1") in str(ambiguous.value)


# --- follow -----------------------------------------------------------------


class _FakeWatch:
    """A watch whose ticks and completion are scripted: `follow`'s loop under test
    without a run dir or a server."""

    def __init__(self, run_root, ticks, complete_after: int | None = None):
        self.run_root = run_root
        self._ticks = list(ticks)
        self._complete_after = complete_after
        self.calls = 0

    def tick(self):
        self.calls += 1
        return self._ticks.pop(0) if self._ticks else []

    def run_complete(self):
        if self._complete_after is not None and self.calls >= self._complete_after:
            return self.run_root / "run.json"
        return None


def test_follow_prints_events_then_exits_on_run_json(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("flowbench.watch.time.sleep", slept.append)
    run_root = tmp_path / "runs" / "case_a" / "r1"
    run_root.mkdir(parents=True)
    (run_root / "run.json").write_text('{"winner": "A"}')
    lines = []
    w = _FakeWatch(run_root, [["SESSION FAILED: flow: plain (c1)"], []], complete_after=2)

    # a live pid is not an exit condition: the loop waits for the run.json
    follow(w, pid=os.getpid(), interval=7.0, out=lines.append)

    assert lines == [
        "SESSION FAILED: flow: plain (c1)",
        'RUN COMPLETE: {"winner": "A"}',
    ]
    assert slept == [7.0]  # one wait between the two ticks, none after the last


@pytest.mark.parametrize("launch_log", [True, False])
def test_follow_exits_when_the_runner_pid_is_gone(tmp_path, monkeypatch, launch_log):
    def _dead(pid, sig):
        raise OSError("no such process")

    monkeypatch.setattr("flowbench.watch.os.kill", _dead)
    monkeypatch.setattr("flowbench.watch.time.sleep", lambda s: pytest.fail("must not wait"))
    run_root = tmp_path / "runs" / "case_a" / "r1"
    run_root.mkdir(parents=True)
    if launch_log:
        (run_root.parent / "r1.launch.log").write_text("Traceback: boom\n")
    lines = []

    follow(_FakeWatch(run_root, []), pid=4242, out=lines.append)

    assert len(lines) == 1
    assert lines[0].startswith("RUNNER EXITED without run.json")
    assert ("Traceback: boom" if launch_log else "(no launch log)") in lines[0]
