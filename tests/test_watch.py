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
