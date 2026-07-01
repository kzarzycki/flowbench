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


def load_scorecards(run_base: str | Path, run_id: str) -> dict[str, dict | None]:
    """{arm_name: scorecard_dict | None}. None = the flow's scorecard.json is
    missing or unreadable (the flow failed to produce a result)."""
    run_root = Path(run_base) / run_id
    cards: dict[str, dict | None] = {}
    for sc_path in sorted(run_root.glob("*/scorecard.json")):
        flow = sc_path.parent.name
        try:
            cards[flow] = json.loads(sc_path.read_text())
        except (OSError, ValueError):
            cards[flow] = None
    return cards


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


def compare_table(cards: dict[str, dict | None]) -> str:
    """Markdown table: rows = metrics, columns = flows (failed flows marked)."""
    if not cards:
        return "_no flow scorecards found_\n"
    flows = list(cards)
    header = "| metric | " + " | ".join(flows) + " |"
    sep = "| --- | " + " | ".join("---" for _ in flows) + " |"
    lines = [header, sep]
    # a whole-flow failure gets its own banner row so the FAILED columns are read
    # as "flow did not run", not "this one metric failed".
    failed = [a for a, c in cards.items() if c is None]
    if failed:
        lines.append(
            "| _status_ | " + " | ".join("FAILED" if a in failed else "ok" for a in flows) + " |"
        )
    for label, path in _METRICS:
        row = [_cell(cards[a], path) for a in flows]
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def render_compare(run_base: str | Path, run_id: str) -> str:
    cards = load_scorecards(run_base, run_id)
    return f"# Flow comparison — {run_id}\n\n" + compare_table(cards)
