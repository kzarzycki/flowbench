"""Debug watcher for a live run: stream anomalies + progress.

One line per event on stdout — permission prompts, server errors/warnings
touching the run's sessions, failed-session flips, trial/run completion.
Exits when the run's aggregate run.json lands (or the runner pid dies).

Works standalone in a terminal, or wrapped by an agent Monitor.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SERVER = "http://127.0.0.1:6767"
SERVER_LOG = Path.home() / ".omnigent" / "logs" / "launchd-omnigent.out.log"


class RunWatch:
    """Incremental scanner: each tick() returns NEW events since the last one.

    Pure-ish (filesystem + HTTP reads only) so tests can drive tick() with a
    fake log file and runs dir.
    """

    def __init__(
        self,
        run_id: str,
        *,
        runs_root: Path,
        scenario: str,
        server_log: Path = SERVER_LOG,
        server: str = SERVER,
    ):
        self.run_root = Path(runs_root) / run_id
        self.project = f"{scenario}/{run_id}"
        self.server_log = server_log
        self.server = server
        self._log_pos = server_log.stat().st_size if server_log.exists() else 0
        self._session_status: dict[str, str] = {}
        self._trials_done: set[str] = set()

    # --- sources -------------------------------------------------------------

    def _new_log_lines(self) -> list[str]:
        if not self.server_log.exists():
            return []
        size = self.server_log.stat().st_size
        if size < self._log_pos:  # rotated
            self._log_pos = 0
        with self.server_log.open() as f:
            f.seek(self._log_pos)
            chunk = f.read()
            self._log_pos = f.tell()
        return chunk.splitlines()

    def _run_sessions(self) -> list[dict]:
        try:
            with urllib.request.urlopen(f"{self.server}/v1/sessions?limit=100", timeout=5) as r:
                data = json.load(r).get("data", [])
        except Exception:
            return []  # server hiccup: skip this tick, never kill the watch
        return [s for s in data if (s.get("labels") or {}).get("omni_project") == self.project]

    # --- tick ----------------------------------------------------------------

    def tick(self) -> list[str]:
        events: list[str] = []
        sessions = self._run_sessions()
        ids = {s["id"] for s in sessions}

        for line in self._new_log_lines():
            if "hooks/permission-request" in line:
                scope = "RUN" if any(i in line for i in ids) else "other session"
                events.append(f"PERMISSION PROMPT ({scope}): {line.strip()[-160:]}")
            elif ("ERROR" in line or "WARNING" in line) and any(i in line for i in ids):
                events.append(f"SERVER {line.strip()[-200:]}")

        for s in sessions:
            prev = self._session_status.get(s["id"])
            cur = s.get("status")
            if prev not in (None, cur) and cur == "failed":
                events.append(f"SESSION FAILED: {s.get('title')} ({s['id']})")
            self._session_status[s["id"]] = cur

        for trial_json in sorted(self.run_root.glob("trial-*/run.json")):
            trial = trial_json.parent.name
            if trial not in self._trials_done:
                self._trials_done.add(trial)
                meta = json.loads(trial_json.read_text())
                events.append(
                    f"TRIAL DONE: {trial} winner={meta.get('winner_flow')}"
                    f" missing={meta.get('plans_missing')}"
                )
        return events

    def run_complete(self) -> Path | None:
        p = self.run_root / "run.json"
        return p if p.is_file() else None
