import asyncio
import json
from pathlib import Path

from flowbench.case import Case
from flowbench.run import rescore_run, run_case
from flowbench.testing import n_run_factories

CASE_DIR = Path(__file__).parent / "fixtures" / "feature_flag_service"


def _case(score_fn=None, case_dir=CASE_DIR) -> Case:
    """The fixture case, graded by `score_fn(flow, flow_dir, session)` — what the
    retired `score_flow` keyword used to carry. No scorer means the base `Case`,
    whose `score` returns None."""
    if score_fn is None:
        return Case(case_dir)

    async def score(self, flow, flow_dir, session):
        return await score_fn(flow, flow_dir, session)

    return type("ScoredCase", (Case,), {"score": score})(case_dir)


def _write_flow(run_root: Path, name: str, *, with_session: bool = True) -> None:
    flow_dir = run_root / name
    flow_dir.mkdir(parents=True, exist_ok=True)
    (flow_dir / "transcript.md").write_text(f"# Transcript {name}\n")
    if with_session:
        (flow_dir / "session.json").write_text(
            json.dumps({"exit_status": "idle", "turns": 1, "items": []})
        )
    (flow_dir / "scorecard.json").write_text(json.dumps({"stale": True}))


def _write_run_json(run_root: Path, flows: list[str], flow_stats: dict) -> None:
    meta = {
        "run_id": run_root.name,
        "flows": flows,
        "flow_stats": flow_stats,
    }
    (run_root / "run.json").write_text(json.dumps(meta, indent=2))


def test_rescore_run_success_clears_stale_error_and_rewrites_scorecards(tmp_path):
    run_root = tmp_path / "run-1"
    _write_flow(run_root, "superpowers")
    _write_flow(run_root, "plain")
    _write_run_json(
        run_root,
        ["superpowers", "plain"],
        {"superpowers": {"score_error": "OldError: boom"}, "plain": {}},
    )
    original_session = (run_root / "superpowers" / "session.json").read_bytes()
    original_transcript = (run_root / "superpowers" / "transcript.md").read_bytes()

    async def score_flow(flow, flow_dir, session):
        return {"flow": flow["name"], "objective": {"acceptance": 1.0}}

    result = asyncio.run(rescore_run(_case(score_flow), run_root))

    assert result == {"superpowers": "ok", "plain": "ok"}
    for name in ("superpowers", "plain"):
        card = json.loads((run_root / name / "scorecard.json").read_text())
        assert card == {"flow": name, "objective": {"acceptance": 1.0}}
    meta = json.loads((run_root / "run.json").read_text())
    assert "score_error" not in meta["flow_stats"]["superpowers"]
    # rescore never touches transcripts or session.json
    assert (run_root / "superpowers" / "session.json").read_bytes() == original_session
    assert (run_root / "superpowers" / "transcript.md").read_bytes() == original_transcript


def test_rescore_run_isolates_one_flows_failure(tmp_path):
    run_root = tmp_path / "run-2"
    _write_flow(run_root, "superpowers")
    _write_flow(run_root, "plain")
    _write_run_json(run_root, ["superpowers", "plain"], {"superpowers": {}, "plain": {}})

    async def score_flow(flow, flow_dir, session):
        if flow["name"] == "superpowers":
            raise RuntimeError("boom")
        return {"flow": flow["name"]}

    result = asyncio.run(rescore_run(_case(score_flow), run_root))

    assert result["superpowers"] == "RuntimeError: boom"
    assert result["plain"] == "ok"
    sp_card = json.loads((run_root / "superpowers" / "scorecard.json").read_text())
    assert sp_card == {"error": "RuntimeError: boom"}
    plain_card = json.loads((run_root / "plain" / "scorecard.json").read_text())
    assert plain_card == {"flow": "plain"}
    meta = json.loads((run_root / "run.json").read_text())
    assert meta["flow_stats"]["superpowers"]["score_error"] == "RuntimeError: boom"


def test_rescore_run_n_gt_1_layout_keys_by_trial(tmp_path):
    run_root = tmp_path / "run-3"
    run_root.mkdir()
    for trial in ("trial-01", "trial-02"):
        trial_dir = run_root / trial
        _write_flow(trial_dir, "superpowers")
        _write_flow(trial_dir, "plain")
        _write_run_json(trial_dir, ["superpowers", "plain"], {"superpowers": {}, "plain": {}})
    # a trial dir the run never got to write a run.json for (killed mid-run):
    # skipped, not a crash and not in the result map
    (run_root / "trial-03").mkdir()
    # aggregate run.json has no flow_stats -> untouched
    aggregate = {"run_id": "run-3", "n": 2, "flows": ["superpowers", "plain"]}
    (run_root / "run.json").write_text(json.dumps(aggregate))

    async def score_flow(flow, flow_dir, session):
        return {"flow": flow["name"]}

    result = asyncio.run(rescore_run(_case(score_flow), run_root))

    assert result == {
        "trial-01/superpowers": "ok",
        "trial-01/plain": "ok",
        "trial-02/superpowers": "ok",
        "trial-02/plain": "ok",
    }
    assert json.loads((run_root / "run.json").read_text()) == aggregate


def test_rescore_run_skips_flow_with_no_session(tmp_path):
    run_root = tmp_path / "run-4"
    _write_flow(run_root, "superpowers", with_session=False)
    _write_flow(run_root, "plain")
    _write_run_json(run_root, ["superpowers", "plain"], {"superpowers": {}, "plain": {}})
    stale_card = (run_root / "superpowers" / "scorecard.json").read_bytes()

    async def score_flow(flow, flow_dir, session):
        return {"flow": flow["name"]}

    result = asyncio.run(rescore_run(_case(score_flow), run_root))

    assert result == {"plain": "ok"}
    assert (run_root / "superpowers" / "scorecard.json").read_bytes() == stale_card


def test_rescore_run_flow_absent_from_flows_yaml_is_keyerror(tmp_path):
    run_root = tmp_path / "run-5"
    _write_flow(run_root, "superpowers")
    _write_flow(run_root, "plain")
    _write_flow(run_root, "ghost")
    _write_run_json(
        run_root,
        ["superpowers", "plain", "ghost"],
        {"superpowers": {}, "plain": {}, "ghost": {}},
    )

    async def score_flow(flow, flow_dir, session):
        return {"flow": flow["name"]}

    result = asyncio.run(rescore_run(_case(score_flow), run_root))

    assert result["superpowers"] == "ok"
    assert result["plain"] == "ok"
    assert result["ghost"].startswith("KeyError")
    ghost_card = json.loads((run_root / "ghost" / "scorecard.json").read_text())
    assert ghost_card == {"error": result["ghost"]}
    meta = json.loads((run_root / "run.json").read_text())
    assert meta["flow_stats"]["ghost"]["score_error"] == result["ghost"]


# --- over a run dir the orchestrator wrote -----------------------------------


async def _orchestrated_run(tmp_path, run_id: str) -> Path:
    """A real run dir: `rescore_run` reads `flow_stats`, which only a run writes."""
    mfd, ms, rj = n_run_factories(["A"])

    async def score_flow(flow, flow_dir, session):
        return {"flow": flow["name"], "pass": 1}

    result = await run_case(
        _case(score_flow),
        run_id=run_id,
        make_flow_driver=mfd,
        make_simulator=ms,
        run_judge=rj,
        runs_root=tmp_path,
    )
    return Path(result["run_root"])


async def test_rescore_hands_the_scorer_an_absolute_flow_dir(tmp_path, monkeypatch):
    """A scorer may start its own omnigent grader off `flow_dir` (todo_app does),
    and the server rejects a workspace that is not absolute (#155). So a relative
    run root has to be resolved before `case.score` sees it."""
    run_root = await _orchestrated_run(tmp_path, "rel-rescore")
    monkeypatch.chdir(tmp_path)
    seen: list[Path] = []

    async def score_flow(flow, flow_dir, session):
        seen.append(Path(flow_dir))
        return {"flow": flow["name"], "pass": 1}

    result = await rescore_run(_case(score_flow), run_root.relative_to(tmp_path))

    assert result == {"superpowers": "ok", "plain": "ok"}
    assert seen and all(d.is_absolute() for d in seen), seen


async def test_rescore_rewrites_from_disk_without_touching_sessions(tmp_path):
    run_root = await _orchestrated_run(tmp_path, "orchestrated")
    before = {
        name: (run_root / name / "session.json").read_bytes() for name in ("superpowers", "plain")
    }

    async def score_flow(flow, flow_dir, session):
        # what is on disk is the whole input: the session dict came from session.json
        return {"flow": flow["name"], "pass": 2, "turns": session["turns"]}

    result = await rescore_run(_case(score_flow), run_root)

    assert result == {"superpowers": "ok", "plain": "ok"}
    for name in ("superpowers", "plain"):
        card = json.loads((run_root / name / "scorecard.json").read_text())
        assert card == {"flow": name, "pass": 2, "turns": 0}
        assert (run_root / name / "session.json").read_bytes() == before[name]
    assert json.loads((run_root / "run.json").read_text())["flow_stats"]["plain"]


async def test_rescore_deletes_a_stale_scorecard_when_score_returns_none(tmp_path):
    run_root = await _orchestrated_run(tmp_path, "then-ungraded")
    assert (run_root / "plain" / "scorecard.json").is_file()

    result = await rescore_run(_case(), run_root)  # nothing grades this case any more

    assert result == {"superpowers": "ok", "plain": "ok"}
    for name in ("superpowers", "plain"):
        assert not (run_root / name / "scorecard.json").exists()
