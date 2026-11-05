"""Side-by-side comparison of flows for one task: read each flow's scorecard.json
and render a single markdown table, one column per flow.

Pure reader — no run state, no scoring. Failure is isolated: an flow whose
scorecard is missing/malformed (never ran, or the driver died) renders as a
FAILED column; every other flow still renders. A per-metric failure (e.g. the
judge couldn't be scored) renders as a FAILED cell, so the flow's objective
metrics are not thrown away with it. The benchmark never aborts on one bad flow.
"""

from __future__ import annotations

import json
from pathlib import Path

from flowbench.schema import SCHEMA_VERSION, FlowOutcome, schema_version_of

# (row label, path into the scorecard dict). Kept explicit so the report reads
# the same regardless of which optional keys a given card happens to carry.
_METRICS: list[tuple[str, tuple[str, ...]]] = [
    ("app_runs", ("objective", "app_runs")),
    ("acceptance", ("objective", "acceptance")),
    ("clarifying_coverage", ("objective", "clarifying_coverage")),
    ("superpowers_used", ("objective", "superpowers_used")),
    ("brainstorming_used", ("objective", "brainstorming_used")),
    ("judge.shape_fit", ("judge_low_confidence", "shape_fit")),
    ("judge.clarifying_quality", ("judge_low_confidence", "clarifying_quality")),
    ("judge.workflow_adherence", ("judge_low_confidence", "workflow_adherence")),
]


def load_cards_with_versions(
    run_base: str | Path, run_id: str
) -> tuple[dict[str, dict | None], dict[str, int]]:
    """({flow: card | None}, {flow: schema_version}). A card this flowbench cannot
    read (`schema_version` > ours) enters the first map as `None` — the existing
    FAILED-column path — and the second map records the version it declared, so
    the report can say WHY the column failed. A card that did not parse has no
    version at all and is absent from the second map."""
    run_root = Path(run_base) / run_id
    cards: dict[str, dict | None] = {}
    versions: dict[str, int] = {}
    for sc_path in sorted(run_root.glob("*/scorecard.json")):
        flow = sc_path.parent.name
        try:
            card = json.loads(sc_path.read_text())
        except (OSError, ValueError):
            cards[flow] = None
            continue
        versions[flow] = schema_version_of(card)
        cards[flow] = None if versions[flow] > SCHEMA_VERSION else card
    return cards, versions


def load_scorecards(run_base: str | Path, run_id: str) -> dict[str, dict | None]:
    """{arm_name: scorecard_dict | None}. None = the flow's scorecard.json is
    missing or unreadable (the flow failed to produce a result)."""
    return load_cards_with_versions(run_base, run_id)[0]


def load_outcomes(run_base: str | Path, run_id: str) -> tuple[dict[str, str], str | None]:
    """({flow: outcome}, note). The run manifest's per-flow outcomes, or `({}, None)`
    when there is no readable manifest — a run dir without one renders exactly the
    table it rendered before outcomes existed. A manifest from a newer flowbench is
    a note above the table, never an exception: the comparison degrades, the metric
    rows still render."""
    path = Path(run_base) / run_id / "run.json"
    try:
        meta = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}, None
    version = schema_version_of(meta)
    if version > SCHEMA_VERSION:
        return {}, f"unsupported schema_version {version}"
    return meta.get("outcomes") or {}, None


def _get(card: dict, path: tuple[str, ...]):
    cur = card
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _cell(card: dict | None, path: tuple[str, ...]) -> str:
    if card is None:
        return "FAILED"
    # the judge block is either the verdict or {"error": reason} — a scored flow
    # with an unscored judge shows FAILED only in the judge rows.
    if (
        path[0] == "judge_low_confidence"
        and isinstance(card.get(path[0]), dict)
        and "error" in card[path[0]]
    ):
        return f"FAILED ({card[path[0]]['error']})"
    val = _get(card, path)
    return "—" if val is None else str(val)


def compare_table(cards: dict[str, dict | None], outcomes: dict[str, str] | None = None) -> str:
    """Markdown table: rows = metrics, columns = flows (failed flows marked)."""
    if not cards:
        return "_no flow scorecards found_\n"
    flows = list(cards)
    header = "| metric | " + " | ".join(flows) + " |"
    sep = "| --- | " + " | ".join("---" for _ in flows) + " |"
    lines = [header, sep]
    # a whole-flow failure gets its own banner row so the FAILED columns are read
    # as "flow did not run", not "this one metric failed". A card is a whole-flow
    # failure either because it's missing/unreadable (None) or because score_flow
    # raised and run_case wrote {"error": ...} as the entire card.
    failed = {
        a: ("" if c is None else c.get("error"))
        for a, c in cards.items()
        if c is None or (isinstance(c, dict) and c.get("error"))
    }
    if failed:
        lines.append(
            "| _status_ | "
            + " | ".join(
                (f"FAILED ({failed[a]})" if failed.get(a) else "FAILED") if a in failed else "ok"
                for a in flows
            )
            + " |"
        )
    # outside the `if failed:` block: a run where every flow scored still has
    # outcomes worth reading (DEGENERATE is a flow that ran and scored).
    if outcomes:
        lines.append("| _outcome_ | " + " | ".join(outcomes.get(a, "—") for a in flows) + " |")
    for label, path in _METRICS:
        row = [_cell(cards[a], path) for a in flows]
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def render_compare(run_base: str | Path, run_id: str) -> str:
    cards, versions = load_cards_with_versions(run_base, run_id)
    outcomes, manifest_note = load_outcomes(run_base, run_id)
    notes = []
    if any(v == 0 for v in versions.values()):
        notes.append("_schema v0 — written before schema_version; fields read positionally._")
    notes += [
        f"_{flow}: unsupported schema_version {v}_"
        for flow, v in versions.items()
        if v > SCHEMA_VERSION
    ]
    if manifest_note is not None:
        notes.append(f"_run manifest: {manifest_note}_")
    degenerate = [f for f, o in outcomes.items() if o == FlowOutcome.DEGENERATE]
    if degenerate:
        notes.append(f"_comparison not rankable: {', '.join(degenerate)} declared degenerate_")
    head = f"# Flow comparison — {run_id}\n\n"
    if notes:
        head += "\n".join(notes) + "\n\n"
    return head + compare_table(cards, outcomes)
