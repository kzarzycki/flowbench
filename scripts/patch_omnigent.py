#!/usr/bin/env python3
"""Apply (or restore) the one out-of-repo patch the agent-eval spike needs.

omnigent's claude-native prompt-ready detector scans only the last 5 non-empty
tmux pane lines for the `❯` input glyph. Under claude 2.1.178 the status footer
(model + ctx/limits + the user's multi-line statusLine) pushes `❯` to line 6, so
2nd+ turn injection fails with "terminal did not become ready". Bumping the scan
window to 12 fixes it. This is the only change the spike depends on that lives
outside the repo, so it travels here and survives a `uv tool upgrade omnigent`.

Idempotent. Usage:
    python scripts/patch_omnigent.py            # apply (default)
    python scripts/patch_omnigent.py --status   # report current state
    python scripts/patch_omnigent.py --restore  # revert from backup
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import sys
from pathlib import Path

OLD = "_PROMPT_SCAN_TAIL_LINES = 5"
NEW = (
    "_PROMPT_SCAN_TAIL_LINES = 12  # flowbench patch (was 5): claude 2.1.178's "
    "multi-line status footer pushes the ❯ input glyph past a 5-line window, "
    "breaking 2nd+ turn injection. See scripts/patch_omnigent.py."
)
CONST_RE = re.compile(r"^_PROMPT_SCAN_TAIL_LINES = (\d+)", re.MULTILINE)


def find_bridge() -> str:
    pats = [
        os.path.expanduser(
            "~/.local/share/uv/tools/omnigent/lib/python*/site-packages/omnigent/claude_native_bridge.py"
        ),
        # fall back to any importable omnigent on the path
    ]
    for pat in pats:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    try:
        import omnigent.claude_native_bridge as m  # type: ignore

        return m.__file__
    except Exception:
        sys.exit("could not locate omnigent claude_native_bridge.py")


def current_value(text: str) -> int | None:
    m = CONST_RE.search(text)
    return int(m.group(1)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    path = find_bridge()
    backup = path + ".flowbench-bak"
    text = Path(path).read_text(encoding="utf-8")
    val = current_value(text)

    if args.status:
        print(f"file:   {path}")
        print(f"value:  _PROMPT_SCAN_TAIL_LINES = {val}")
        print(f"backup: {'present' if os.path.exists(backup) else 'absent'}")
        print(f"state:  {'PATCHED' if val and val >= 12 else 'unpatched'}")
        return 0

    if args.restore:
        if os.path.exists(backup):
            shutil.copy2(backup, path)
            print(f"restored from {backup}")
        elif OLD not in text and val is not None:
            Path(path).write_text(
                CONST_RE.sub("_PROMPT_SCAN_TAIL_LINES = 5", text, count=1),
                encoding="utf-8",
            )
            print("restored to 5 (no backup found)")
        else:
            print("nothing to restore")
        return 0

    # apply
    if val is not None and val >= 12:
        print(f"already patched (value={val}); no change")
        return 0
    if OLD not in text:
        sys.exit(f"unexpected: '{OLD}' not found (value={val}). omnigent layout changed?")
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    Path(path).write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"patched {path}\n  _PROMPT_SCAN_TAIL_LINES 5 -> 12 (backup: {backup})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
