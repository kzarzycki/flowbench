import json

from flowbench.watch import RunWatch


def test_run_watch_tick_events(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("boot line\n")
    run_root = tmp_path / "runs" / "todo-x"
    run_root.mkdir(parents=True)
    w = RunWatch("todo-x", runs_root=tmp_path / "runs", scenario="swe_planning", server_log=log)
    w._run_sessions = lambda: [
        {
            "id": "conv_aaa",
            "status": "running",
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
            "status": "failed",
            "title": "flow: plain",
            "labels": {"omni_project": "swe_planning/todo-x"},
        },
    ]
    assert any(e.startswith("SESSION FAILED") for e in w.tick())
    assert w.tick() == []

    # trial completion fires once; run completion via run_complete()
    trial = run_root / "trial-01"
    trial.mkdir()
    (trial / "run.json").write_text(json.dumps({"winner_flow": "plain", "plans_missing": []}))
    assert any(e.startswith("TRIAL DONE: trial-01 winner=plain") for e in w.tick())
    assert w.tick() == []
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


def test_run_watch_sessions_filters_by_project_and_survives_server_errors(monkeypatch):
    import io
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

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert w._run_sessions() == []


def test_run_watch_reports_server_errors_touching_run_sessions(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("")
    (tmp_path / "runs" / "r").mkdir(parents=True)
    w = RunWatch("r", runs_root=tmp_path / "runs", scenario="s", server_log=log)
    w._run_sessions = lambda: [{"id": "conv_1", "status": "running", "title": "flow: x"}]
    log.write_text("ERROR runner conv_1 exploded\nERROR unrelated conv_9\n")
    events = w.tick()
    assert len(events) == 1 and events[0].startswith("SERVER ERROR runner conv_1")


def test_run_watch_reports_stalls_once_per_transition(tmp_path, monkeypatch):
    monkeypatch.setattr("flowbench.watch.time.time", lambda: 1000.0)
    w = RunWatch(
        "r", runs_root=tmp_path, scenario="s", server_log=tmp_path / "none.log", stall_s=300
    )
    sess = {"id": "c1", "status": "running", "title": "flow: x", "updated_at": 900}
    w._run_sessions = lambda: [sess]
    assert w.tick() == []  # fresh heartbeat, no prompt

    sess["pending_elicitations_count"] = 1
    assert w.tick() == ["STALLED (elicitation): flow: x (c1)"]
    assert w.tick() == []  # unchanged: no repeat

    sess["pending_elicitations_count"] = 0
    sess["updated_at"] = 600  # 400 s silent while running
    assert w.tick() == []  # still stalled, reason changed but no new transition
    sess["status"] = "idle"
    assert w.tick() == []  # recovered
    sess["status"] = "running"
    assert w.tick() == ["STALLED (no progress 400s): flow: x (c1)"]
