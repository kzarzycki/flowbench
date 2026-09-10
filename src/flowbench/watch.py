"""Debug watcher for a live run: stream anomalies + progress.

One line per event on stdout — permission prompts, server errors/warnings
touching the run's sessions, failed-session flips, stalls, a CLI limit banner
(`QUOTA: …`, #131 — wait for the reset, nothing to debug), trial/run completion.
Exits when the run's aggregate run.json lands (or the runner pid dies).

`RunWatch` is the incremental scanner, `follow` the loop that prints its events;
`flowbench watch <run_id>` is the CLI over both. Works standalone in a terminal,
or wrapped by an agent Monitor.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import time
import urllib.request
from pathlib import Path

from flowbench.transcript import is_quota_banner, item_text
from flowbench.types import TurnStatus

log = logging.getLogger(__name__)

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
        server_log: Path = SERVER_LOG,
        server: str = SERVER,
        stall_s: float = 300.0,
    ):
        self.stall_s = stall_s
        self.run_root = self.locate(run_id, runs_root)
        self.project = f"{self.run_root.parent.name}/{run_id}"
        self.server_log = server_log
        self.server = server
        self._log_pos = server_log.stat().st_size if server_log.exists() else 0
        self._session_status: dict[str, str] = {}
        self._session_stall: dict[str, str | None] = {}
        self._session_quota: set[str] = set()
        self._session_read_at: dict[str, object] = {}  # updated_at at the last item read
        self._trials_done: set[str] = set()

    @staticmethod
    def locate(run_id: str, runs_root: Path) -> Path:
        """The one `<runs_root>/<case>/<run_id>` dir, so an operator watches a run
        by its id alone: which case wrote it is in the layout, and the session
        label (`<case>/<run_id>`) is read back off the path rather than retyped.
        Nothing found is a `FileNotFoundError` — the run has not started yet, or the
        runs root is wrong; the same id under two cases is a `ValueError` naming the
        paths, because both exist and only the operator can say which (D17)."""
        runs_root = Path(runs_root)
        found = sorted(p for p in runs_root.glob(f"*/{run_id}") if p.is_dir())
        if not found:
            raise FileNotFoundError(f"no run dir {runs_root / '*' / run_id}")
        if len(found) > 1:
            raise ValueError(
                f"run id {run_id} matches {len(found)} cases: " + ", ".join(str(p) for p in found)
            )
        return found[0]

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
        except (OSError, http.client.HTTPException, ValueError, AttributeError) as e:
            log.debug("sessions read failed, skipping tick: %r", e)
            return []  # server hiccup: skip this tick, never kill the watch
        return [s for s in data if (s.get("labels") or {}).get("omni_project") == self.project]

    def _last_assistant_text(self, session_id: str) -> str:
        """Text of the session's last item when it is an assistant message, else ""
        (a user/tool item, no items, or a failed read — the watch never dies on one)."""
        url = f"{self.server}/v1/sessions/{session_id}/items?limit=1&order=desc"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                items = json.load(r).get("data", [])
        except (OSError, http.client.HTTPException, ValueError, AttributeError) as e:
            log.debug("items read failed for %s, skipping: %r", session_id, e)
            return ""
        it = items[0] if items else {}
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "assistant":
            return item_text(it)
        return ""

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
            if prev not in (None, cur) and cur == TurnStatus.FAILED:
                events.append(f"SESSION FAILED: {s.get('title')} ({s['id']})")
            self._session_status[s["id"]] = cur
            # quota banner (#131): the session's last assistant item IS the CLI's
            # limit banner — the operator waits for the reset. Once per session, and
            # the item read happens only when the session moved (`updated_at`
            # changed) — not one HTTP round-trip per session per tick.
            at = s.get("updated_at")
            if s["id"] not in self._session_quota and self._session_read_at.get(s["id"], ...) != at:
                self._session_read_at[s["id"]] = at
                banner = self._last_assistant_text(s["id"])
                if is_quota_banner(banner):
                    self._session_quota.add(s["id"])
                    events.append(f"QUOTA: {s.get('title')} ({s['id']}) {banner.strip()}")
            # stall watchdog (#54): a pending elicitation is a prompt nobody can
            # answer (the list endpoint exposes only that count); a running
            # session with a stale heartbeat is stuck on one the server cannot
            # see. Fires once per transition, like FAILED.
            age = time.time() - (s.get("updated_at") or time.time())
            stall = (
                "prompt"
                if s.get("pending_elicitations_count")
                else f"no progress {int(age)}s"
                if cur == TurnStatus.RUNNING and age >= self.stall_s
                else None
            )
            if stall and self._session_stall.get(s["id"]) is None:
                events.append(f"STALLED ({stall}): {s.get('title')} ({s['id']})")
            self._session_stall[s["id"]] = stall

        for trial_json in sorted(self.run_root.glob("trial-*/run.json")):
            trial = trial_json.parent.name
            if trial not in self._trials_done:
                self._trials_done.add(trial)
                meta = json.loads(trial_json.read_text())
                line = f"TRIAL DONE: {trial} winner={meta.get('winner_flow')}"
                if "artifact_missing" in meta:
                    line += f" missing={meta['artifact_missing']}"
                events.append(line)
        return events

    def run_complete(self) -> Path | None:
        p = self.run_root / "run.json"
        return p if p.is_file() else None


def follow(watch: RunWatch, *, pid: int | None = None, interval: float = 15.0, out=print) -> None:
    """Print one line per event until the run ends. Two exits: the run's own
    run.json lands, or the runner pid is gone — a runner that died before writing
    one leaves nothing to poll, so the launch log's tail is the diagnosis."""
    while True:
        for event in watch.tick():
            out(event)
        done = watch.run_complete()
        if done is not None:
            out(f"RUN COMPLETE: {done.read_text()}")
            return
        if pid is not None and not _alive(pid):
            log_path = watch.run_root.parent / f"{watch.run_root.name}.launch.log"
            tail = log_path.read_text()[-1500:] if log_path.exists() else "(no launch log)"
            out(f"RUNNER EXITED without run.json — launch log tail:\n{tail}")
            return
        time.sleep(interval)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
