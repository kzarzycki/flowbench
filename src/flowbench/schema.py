"""The on-disk run schema: its version, its two manifest shapes, the per-flow
outcome vocabulary, and the reader rules every reader shares.

The executable copy of `docs/design/run-schema.md`. Imported by the writers
(`flowbench.run`) and the readers (`flowbench.report`, `flowbench.watch`); it
imports none of them.
"""

from __future__ import annotations

from enum import StrEnum

from flowbench.types import TurnStatus

SCHEMA_VERSION = 1


class RunKind(StrEnum):
    """Which manifest shape a `run.json` is: one trial, or the aggregate over `n`
    of them. `StrEnum` so `meta["kind"]` serializes as the plain string."""

    TRIAL = "trial"
    AGGREGATE = "aggregate"


class FlowOutcome(StrEnum):
    """How one flow ended, in precedence order: a flow that never started cannot
    also be missing a deliverable, and a scorer that raised outranks the card it
    never produced. `OK` is the absence of all four."""

    NO_START = "no_start"  # zero turns and the session did not settle
    NO_DELIVERABLE = "no_deliverable"  # ran, but the declared artifact is absent
    SCORER_FAILED = "scorer_failed"  # `case.score` raised
    DEGENERATE = "degenerate"  # the card declares itself unrankable
    OK = "ok"


class SchemaVersionError(ValueError):
    """A document written by a newer flowbench than this one can read."""


def schema_version_of(doc: dict) -> int:
    """The document's version; a missing `schema_version` is version 0. A document
    that is not a mapping at all is version 0 too — `compare` reads whatever JSON a
    run dir happens to hold and must degrade on it, never raise."""
    if not isinstance(doc, dict):
        return 0
    try:
        return int(doc.get("schema_version", 0))
    except (TypeError, ValueError):
        return 0


def require_version(doc: dict, path) -> int:
    """The document's version, or `SchemaVersionError` when it is too new."""
    version = schema_version_of(doc)
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{path}: schema_version {version}, this flowbench reads 0..{SCHEMA_VERSION}"
        )
    return version


def flow_outcome(
    *,
    session: dict,
    has_deliverable: bool,
    score_error: str | None,
    card: dict | None,
) -> FlowOutcome:
    """One flow's outcome, first match wins (see `FlowOutcome`)."""
    if (session.get("turns") or 0) == 0 and session.get("exit_status") != TurnStatus.IDLE:
        return FlowOutcome.NO_START
    if has_deliverable and not session.get("artifact_exists"):
        return FlowOutcome.NO_DELIVERABLE
    if score_error is not None:
        return FlowOutcome.SCORER_FAILED
    if isinstance(card, dict) and card.get("degenerate") is True:
        return FlowOutcome.DEGENERATE
    return FlowOutcome.OK


def run_kind(meta: dict) -> RunKind | None:
    """The manifest's shape. v1 declares it; a v0 manifest (no `schema_version`)
    is inferred from the key only that shape carries."""
    if schema_version_of(meta) >= 1:
        kind = meta.get("kind")
        return RunKind(kind) if kind in tuple(RunKind) else None
    if "trials" in meta:
        return RunKind.AGGREGATE
    if "flow_stats" in meta:
        return RunKind.TRIAL
    return None


_REQUIRED = {
    RunKind.TRIAL: (
        "schema_version",
        "kind",
        "run_id",
        "case",
        "deliverable",
        "flows",
        "labels",
        "rotation",
        "winner",
        "winner_flow",
        "scores",
        "flow_stats",
        "models",
        "reasoning_effort",
        "outcomes",
        "workspace",
    ),
    RunKind.AGGREGATE: (
        "schema_version",
        "kind",
        "run_id",
        "case",
        "deliverable",
        "n",
        "flows",
        "trials",
        "counts",
        "winner",
        "score_means",
    ),
}  # `artifact_missing` is the trial shape's only optional key, in neither tuple


def validate_run_meta(meta: dict) -> RunKind:
    """The manifest's kind, or `ValueError` naming the first absent required key.
    A required key holding `None` is present; unknown keys are ignored."""
    kind = run_kind(meta)
    if kind is None:
        raise ValueError(f"run manifest declares no readable kind: {meta.get('kind')!r}")
    for key in _REQUIRED[kind]:
        if key not in meta:
            raise ValueError(f"{kind} run manifest is missing required key: {key}")
    return kind
