import json

import pytest

from flowbench.types import TurnStatus
from flowbench.watch import RunWatch


def test_run_watch_tick_events(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("boot line\n")
    run_root = tmp_path / "runs" / "todo-x"
    run_root.mkdir(parents=True)
    w = RunWatch("todo-x", runs_root=tmp_path / "runs", scenario="swe_planning", server_log=log)
    w._last_assistant_text = lambda sid: ""  # keep the suite off the network (#131 read)
    w._run_sessions = lambda: [
        {
            "id": "conv_aaa",
            "status": TurnStatus.RUNNING,
            "title": "flow: plain",
            "labels": {"omni_project": "swe_planning/todo-x"},
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
            "labels": {"omni_project": "swe_planning/todo-x"},
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
    (tmp_path / "runs" / "r").mkdir(parents=True)
    w = RunWatch("r", runs_root=tmp_path / "runs", scenario="s", server_log=log)
    assert w._new_log_lines() == []
    log.write_text("a\nb\n")
    assert w._new_log_lines() == ["a", "b"]
    log.write_text("c\n")  # shorter than the last position -> rotated, re-read from 0
    assert w._new_log_lines() == ["c"]


def test_run_watch_sessions_filters_by_project_and_survives_server_errors(monkeypatch, caplog):
    import http.client
    import io
    import logging
    import urllib.request

    from flowbench import watch as watch_mod

    w = RunWatch("r", runs_root="/nonexistent", scenario="s", server_log=watch_mod.SERVER_LOG)
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
    (tmp_path / "runs" / "r").mkdir(parents=True)
    w = RunWatch("r", runs_root=tmp_path / "runs", scenario="s", server_log=log)
    w._last_assistant_text = lambda sid: ""  # offline
    w._run_sessions = lambda: [{"id": "conv_1", "status": TurnStatus.RUNNING, "title": "flow: x"}]
    log.write_text("ERROR runner conv_1 exploded\nERROR unrelated conv_9\n")
    events = w.tick()
    assert len(events) == 1 and events[0].startswith("SERVER ERROR runner conv_1")


def test_run_watch_reports_stalls_once_per_transition(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.watch.time.time", lambda: 1000.0)
    w = RunWatch(
        "r", runs_root=tmp_path, scenario="s", server_log=tmp_path / "none.log", stall_s=300
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
    (tmp_path / "runs" / "r1").mkdir(parents=True)
    w = RunWatch("r1", runs_root=tmp_path / "runs", scenario="coding_workflow", server_log=log)
    w._run_sessions = lambda: [
        {
            "id": "conv_q",
            "status": TurnStatus.FAILED,
            "title": "flow: superpowers",
            "labels": {"omni_project": "coding_workflow/r1"},
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
    return RunWatch("r1", runs_root=tmp_path / "runs", scenario="coding_workflow", server_log=log)


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
