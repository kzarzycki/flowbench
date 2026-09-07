"""Generic helpers for parsing a judge model's reply. Case-specific rubric
validation (which keys, what clamping) stays in the case's scorers."""

from __future__ import annotations

import json
import re

_WINNER = re.compile(r"WINNER:\s*([a-z]|tie)\b", re.IGNORECASE)


def _balanced_end(text: str, start: int) -> int:
    """Index just past the `}` closing the `{` at `start`, tracking JSON string
    and escape state so braces/quotes inside strings don't count; -1 if unbalanced."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def last_json_object(text: str) -> dict | None:
    """Return the last balanced top-level JSON object in `text`, or None.
    Robust to a model emitting prose, fenced code, stray braces/quotes, or an
    example object before the real `{"score": …}`: every `{` is tried as a start,
    its balanced end found with string/escape awareness (so `{"a": "}"}` and
    `{"a": "\\""}` parse), and the last span that json-parses to a dict wins.
    ponytail: O(n·k) over candidate starts; judge replies are a few KB."""
    last: dict | None = None
    i = text.find("{")
    while i != -1:
        end = _balanced_end(text, i)
        if end != -1:
            try:
                obj = json.loads(text[i:end])
            except ValueError:
                obj = None
            if isinstance(obj, dict):
                last = obj
                i = text.find("{", end)  # skip the nested starts inside a hit
                continue
        i = text.find("{", i + 1)
    return last


def _line_after(label: str, text: str) -> str:
    matches = re.findall(rf"^\s*{label}:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    return matches[-1].strip() if matches else ""


_SCORES = re.compile(r"^SCORES\s+([A-Z]):\s*(.+)$", re.M)
_SCORE_KV = re.compile(r"([a-z_]+)\s*=\s*(\d+)")
_ASSESS_LINE = re.compile(r"^\s*([A-Za-z]):\s*(.+)$", re.MULTILINE)


def parse_scores(text: str) -> dict:
    """`SCORES A: fulfillment=4 discovery=5 ...` lines -> {"a": {...}, "c": {...}}.
    Only labels PRESENT in the text get a key; callers use `.get`."""
    scores: dict[str, dict[str, int]] = {}
    for m in _SCORES.finditer(text):
        side = m.group(1).lower()
        scores[side] = {k: int(v) for k, v in _SCORE_KV.findall(m.group(2))}
    return scores


def parse_verdict(text: str) -> dict:
    """Lenient parse of the judge's tail. Winner = the LAST `WINNER:` line (a model
    may show an example first). Missing tail -> 'unknown', prose always kept."""
    matches = list(_WINNER.finditer(text))
    winner = matches[-1].group(1).lower() if matches else "unknown"
    labels = {m.group(1).upper() for m in _ASSESS_LINE.finditer(text)}
    assessments = {label.lower(): _line_after(label, text) for label in sorted(labels)}
    return {
        "winner": winner,  # single letter | "tie" | "unknown"
        "assessments": assessments,  # {"a": "...", "b": "...", ...}
        "scores": parse_scores(text),  # {"a": {criterion: 0-5}, ...}
        "prose": text.strip(),
    }


def build_judge_prompt(judge_md: str, entries: list[tuple[str, str, str]]) -> str:
    """Judge input = rubric + each flow's conversation with the user + its plan.
    entries is an ordered list of (label, transcript, plan). The transcripts
    matter: fulfillment is graded against what the user actually said in THAT
    conversation, and discovery (asked vs guessed-then-corrected) is invisible
    in the final plans alone."""
    parts = [judge_md.strip()]
    for label, transcript, _plan in entries:
        if transcript:
            parts.append(f"--- CONVERSATION {label} (flow {label} with the user) ---\n{transcript}")
    for label, _transcript, plan in entries:
        parts.append(f"--- PLAN {label} ---\n{plan}")
    return "\n\n".join(parts) + "\n"


def aggregate_verdicts(winners: list[str]) -> dict:
    """Tally per-trial winners (flow NAMES, or "tie"/"unknown"). Aggregate winner
    is the strict plurality among names; equal top counts -> "tie". tie/unknown
    trials are counted but can never win (categorical verdicts: no mean/median)."""
    counts: dict[str, int] = {"tie": 0, "unknown": 0}
    for w in winners:
        key = w if w in ("tie", "unknown") else w
        counts[key] = counts.get(key, 0) + 1
    name_counts = {k: v for k, v in counts.items() if k not in ("tie", "unknown")}
    if not name_counts:
        winner = "tie"
    else:
        top_count = max(name_counts.values())
        top = [k for k, v in name_counts.items() if v == top_count]
        winner = top[0] if len(top) == 1 else "tie"
    return {"counts": counts, "winner": winner}


def aggregate_scores(score_dicts: list[dict]) -> dict:
    """Mean per criterion per KEY over trials that emitted scores. Trials without
    scores are skipped; no scores at all -> {}. Iterates the union of keys present
    across all trials rather than a fixed set of sides."""
    sums: dict[str, dict[str, list[int]]] = {}
    for d in score_dicts:
        for key, crit_dict in (d or {}).items():
            for k, v in (crit_dict or {}).items():
                sums.setdefault(key, {}).setdefault(k, []).append(v)
    return {
        key: {k: round(sum(vs) / len(vs), 2) for k, vs in crits.items()}
        for key, crits in sums.items()
    }
