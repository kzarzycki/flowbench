"""The run-schema vocabulary: outcome precedence, manifest validation, versions."""

import pytest

from flowbench.schema import (
    FlowOutcome,
    RunKind,
    SchemaVersionError,
    flow_outcome,
    require_version,
    run_kind,
    schema_version_of,
    validate_run_meta,
)
from flowbench.types import TurnStatus


def _trial_meta(**over):
    meta = {
        "schema_version": 1,
        "kind": "trial",
        "run_id": "r",
        "case": "c",
        "deliverable": None,
        "flows": ["plain"],
        "labels": {},
        "rotation": [],
        "winner": None,
        "winner_flow": None,
        "scores": {},
        "flow_stats": {},
        "models": {},
        "reasoning_effort": {},
        "outcomes": {},
        "workspace": None,
    }
    meta.update(over)
    return meta


def _aggregate_meta(**over):
    meta = {
        "schema_version": 1,
        "kind": "aggregate",
        "run_id": "r",
        "case": "c",
        "deliverable": None,
        "n": 3,
        "flows": ["plain"],
        "trials": [],
        "counts": {},
        "winner": None,
        "score_means": {},
    }
    meta.update(over)
    return meta


def test_no_start_outranks_no_deliverable_but_needs_a_non_idle_status():
    assert (
        flow_outcome(
            session={"turns": 0, "exit_status": "failed"},
            has_deliverable=True,
            score_error=None,
            card=None,
        )
        is FlowOutcome.NO_START
    )
    assert (
        flow_outcome(
            session={"turns": 0, "exit_status": "failed"},
            has_deliverable=False,
            score_error=None,
            card=None,
        )
        is FlowOutcome.NO_START
    )
    for idle in ("idle", TurnStatus.IDLE):
        assert (
            flow_outcome(
                session={"turns": 0, "exit_status": idle, "artifact_exists": False},
                has_deliverable=True,
                score_error=None,
                card=None,
            )
            is FlowOutcome.NO_DELIVERABLE
        )
        assert (
            flow_outcome(
                session={"turns": 0, "exit_status": idle},
                has_deliverable=False,
                score_error=None,
                card=None,
            )
            is FlowOutcome.OK
        )


def test_a_started_flow_with_no_artifact_is_no_deliverable():
    assert (
        flow_outcome(
            session={"turns": 3, "exit_status": "idle", "artifact_exists": False},
            has_deliverable=True,
            score_error=None,
            card=None,
        )
        is FlowOutcome.NO_DELIVERABLE
    )


def test_a_raising_scorer_outranks_a_delivered_artifact():
    assert (
        flow_outcome(
            session={"turns": 3, "exit_status": "idle", "artifact_exists": True},
            has_deliverable=True,
            score_error="KeyError: x",
            card=None,
        )
        is FlowOutcome.SCORER_FAILED
    )


def test_degenerate_is_the_cards_own_flag():
    session = {"turns": 3, "exit_status": "idle", "artifact_exists": True}
    assert (
        flow_outcome(
            session=session, has_deliverable=True, score_error=None, card={"degenerate": True}
        )
        is FlowOutcome.DEGENERATE
    )
    assert (
        flow_outcome(
            session=session, has_deliverable=True, score_error=None, card={"degenerate": False}
        )
        is FlowOutcome.OK
    )
    assert (
        flow_outcome(session=session, has_deliverable=True, score_error=None, card=None)
        is FlowOutcome.OK
    )


def test_validate_run_meta_returns_the_kind_and_names_the_first_absent_key():
    assert validate_run_meta(_trial_meta()) is RunKind.TRIAL
    assert validate_run_meta(_aggregate_meta()) is RunKind.AGGREGATE

    trial = _trial_meta()
    del trial["flow_stats"]
    with pytest.raises(ValueError, match="flow_stats"):
        validate_run_meta(trial)

    aggregate = _aggregate_meta()
    del aggregate["trials"]
    with pytest.raises(ValueError, match="trials"):
        validate_run_meta(aggregate)

    assert validate_run_meta(_trial_meta(a_future_key=1)) is RunKind.TRIAL

    assert validate_run_meta(_trial_meta(workspace=None)) is RunKind.TRIAL
    no_workspace = _trial_meta()
    del no_workspace["workspace"]
    with pytest.raises(ValueError, match="workspace"):
        validate_run_meta(no_workspace)


def test_require_version_names_the_file_and_both_versions():
    with pytest.raises(SchemaVersionError) as exc:
        require_version({"schema_version": 2}, "p")
    message = str(exc.value)
    assert "p" in message
    assert "2" in message
    assert "0..1" in message

    assert require_version({}, "p") == 0
    assert require_version({"schema_version": 1}, "p") == 1


def test_run_kind_reads_v1_and_infers_v0():
    assert run_kind(_trial_meta()) is RunKind.TRIAL
    assert run_kind(_aggregate_meta()) is RunKind.AGGREGATE
    assert run_kind({"trials": []}) is RunKind.AGGREGATE
    assert run_kind({"flow_stats": {}}) is RunKind.TRIAL
    assert run_kind({}) is None


def test_a_document_that_is_not_a_mapping_is_version_0():
    """`compare` reads any JSON a run dir holds; a `[]` or `null` run.json must
    degrade to v0, not raise, or the isolation rule breaks on one bad file."""
    for doc in ([], None, "1", 7):
        assert schema_version_of(doc) == 0
