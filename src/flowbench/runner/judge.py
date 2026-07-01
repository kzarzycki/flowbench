"""Generic helpers for parsing a judge model's reply. Case-specific rubric
validation (which keys, what clamping) stays in the case's scorers."""

from __future__ import annotations

import json


def last_json_object(text: str) -> dict | None:
    """Return the last balanced top-level JSON object in `text`, or None.
    Robust to a model emitting prose, fenced code, or an example object before
    the real `{"score": …}` — first-`{`/last-`}` slicing breaks on those."""
    end = len(text)
    while True:
        close = text.rfind("}", 0, end)
        if close == -1:
            return None
        depth = 0
        for i in range(close, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[i : close + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        pass
                    break
        end = close
