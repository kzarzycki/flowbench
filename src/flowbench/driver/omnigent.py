"""The ONE module that knows omnigent exists.

`OmnigentDriver` owns the session lifecycle: starting a local server's session,
pinning the subscription model, disabling the interactive question card, the
status-driven turn boundary, reading the structured transcript, and teardown.
The solver depends only on `AgentDriver` (`.base`), so swapping omnigent for
another REPL driver (or a fake, in tests) changes nothing upstream. What the
flow's agent is *configured* with lives in `.bundle`.

The recipe here is exactly what the live probe proved (subscription-billed,
multi-turn, artifact written). Three hard-won settings:
- model pinned (the user's own CLI default may be an unavailable model);
- `--disallowedTools AskUserQuestion` (the interactive card blocks the tmux
  input prompt, deadlocking follow-up turns);
- `--permission-mode bypassPermissions` for every flow (#52): a permission
  prompt has no one to answer it and stalls the turn until the cap.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flowbench.driver import bundle
from flowbench.driver.base import AgentDriver
from flowbench.transcript import (
    dedup_items,
    last_assistant_text,
    n_assistant_messages,
    new_assistant_text,
    to_jsonable,
)
from flowbench.types import TurnResult, TurnStatus

# raw-session fields that mean "the agent is waiting on a human"
# Signals that a human is being asked something. NOT `pending_inputs`: omnigent
# documents that as "un-consumed web-composer user messages" — i.e. OUR posted
# message queued behind a running turn (todo-app-005 stalled on its own inject).
_PROMPT_KEYS = ("pending_elicitations", "terminal_pending")
_PAGE = 200  # server-side max page for GET /v1/sessions/{id}/items
# The SDK's httpx client ignores the constructor `timeout` and reads with the 600 s
# SSE budget; a label read that hangs must fail in the 60 s the raw client had.
_LABEL_READ_S = 60.0
_now = time.monotonic  # clock seam: the budget tests drive a fake one; never patch
# time.monotonic itself (asyncio uses it)


def git_init_repo(path: Path) -> None:
    """Init a git repo with an initial commit so the workflow can branch/commit."""
    import subprocess

    path.mkdir(parents=True, exist_ok=True)

    def run(*a: str):
        # scrub GIT_* (a git hook calling us exports GIT_DIR/GIT_WORK_TREE/... that
        # would redirect this nested git at the outer repo, #49)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.run(
            ["git", "-C", str(path), *a], check=True, capture_output=True, text=True, env=env
        )

    run("init", "-q")
    # local identity so commits don't depend on global git config
    run("config", "user.email", "agent-eval@example.com")
    run("config", "user.name", "agent-eval")
    (path / ".gitkeep").write_text("")
    run("add", "-A")
    run("commit", "-q", "-m", "chore: initial commit (agent-eval run-dir)")


@dataclass
class OmnigentDriver(AgentDriver):
    """Drives a real `claude` REPL via a local omnigent server.

    :param run_dir: absolute cwd the agent writes into (artifact lands here).
    :param artifact_name: the file the task asks for (existence check).
    :param server_url: omnigent server base URL.
    :param model: subscription model id/alias to pin (e.g. "sonnet").
    """

    run_dir: Path
    artifact_name: str = "__none__"  # unused by run_case/omni_factories now (S02.4 Task A);
    # dropped along with the rest of the artifact concern in Task B.
    server_url: str = field(
        default_factory=lambda: os.environ.get("OMNIGENT_SERVER", "http://127.0.0.1:6767")
    )
    model: str = field(default_factory=lambda: os.environ.get("OMNIGENT_PROBE_MODEL", "sonnet"))
    reasoning_effort: str | None = None
    agent_name: str = "claude_code"
    agent_prompt: str | None = None
    agent_description: str = (
        "Vanilla Claude Code under test (subscription; system prompt untouched)."
    )
    git_init: bool = False
    turn_timeout_s: float = 240.0
    # Stall watchdog (#54, #61): a `TurnStatus.RUNNING` session waiting on a human
    # (any of _PROMPT_KEYS set) or with no heartbeat for stall_s ends the turn as
    # TurnStatus.STALLED instead of burning the whole turn cap. Bites
    # only under a turn cap longer than itself (run.py sets 1800 s).
    stall_s: float = 300.0
    # After the last busy child clears, omnigent injects a task-notification and
    # the main agent runs again a few seconds later. Reporting idle in that gap
    # queued our inject behind the wake-up turn (todo-app-005). Wait for the
    # wake-up (status running) or this many seconds, whichever comes first.
    child_wake_s: float = 20.0
    # TurnStatus.IDLE can be observed before the runner picks the turn up (fresh
    # session), before the reply item persists, or while the agent is still
    # MID-TURN (bridge race seen live: injecting then hits a busy terminal and
    # the run dies). An idle turn is trusted only once a NEW assistant message
    # has landed; settling draws on the one send-wide budget (`deadline`).
    # Expiry -> TurnStatus.TIMEOUT, never a stale reply.
    settle_poll_s: float = 2.0
    # FAILED with no new assistant message (rows 1/3, docs/design/runner.md): the
    # inject likely never landed (busy terminal behind a lying idle, seen live
    # twice) — wait `send_retry_wait_s`, re-send the same text, at most
    # `send_retry_attempts` times, only while the send's budget still covers the
    # wait. FAILED with a new assistant message is a flaked idle, never re-sent.
    send_retry_attempts: int = 3
    send_retry_wait_s: float = 30.0
    # Per-flow bundle inputs (see runner.flow.Flow). Defaults reproduce the vanilla
    # baseline: claude-native, host skills visible, nothing added to the bundle.
    harness: str = "claude-native"
    skills: str | list[str] = "all"  # -> config.yaml top-level skills:
    skill_dirs: list[Path] = field(default_factory=list)
    mcp_files: list[Path] = field(default_factory=list)
    # Web-UI grouping/labelling (both optional; unset leaves the server default).
    # `session_title` is a short human title (e.g. "flow: superpowers", "judge")
    # instead of the kickoff-text default; `project` groups a run's sessions into
    # one sidebar folder via the `omni_project` label the UI groups on.
    session_title: str | None = None
    project: str | None = None

    # internal state
    _started: float = 0.0
    _captured: list[dict] = field(default_factory=list)
    _closed: bool = False
    _http: Any = None
    _client: Any = None
    _chat: Any = None
    _runner_id: str | None = None

    # Thin delegates to `.bundle` — the pure functions are the canonical form
    # (S03.1 calls them off a `Flow`); these keep the driver's own surface.
    def render_config(self) -> str:
        return bundle.render_config(self)

    def _build_bundle(self) -> bytes:
        return bundle.build_bundle(self)

    def _create_metadata(self) -> dict[str, Any]:
        return bundle.session_metadata(self)

    async def start(self) -> None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is set — would defeat subscription billing.")
        import httpx

        # UPSTREAM: https://github.com/omnigent-ai/omnigent/issues/6822 — the SDK has no hosts/runners
        # namespace; these are the `omnigent host` CLI's helpers (inventory R3).
        from omnigent.host.daemon_launch import (
            launch_or_reuse_daemon_runner,
            wait_for_runner_online,
        )
        from omnigent_client import OmnigentClient, SessionsChat

        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.git_init and not (self.run_dir / ".git").exists():
            git_init_repo(self.run_dir)
        self._started = time.monotonic()
        self._http = httpx.AsyncClient(base_url=self.server_url, timeout=60.0)
        self._client = OmnigentClient(base_url=self.server_url)

        host_id = await self._resolve_claude_host()
        agent_bundle = self._build_bundle()

        # Create with --disallowedTools so claude asks in plain text (the card
        # otherwise blocks the tmux prompt and deadlocks turn 2+).
        # UPSTREAM: https://github.com/omnigent-ai/omnigent/issues/6822 — `sessions.create()` cannot
        # send `terminal_launch_args`; raw POST until the SDK carries it (inventory R1).
        resp = await self._client.sessions._http.post(
            f"{self._client.sessions._base}/v1/sessions",
            data={"metadata": json.dumps(self._create_metadata())},
            files={"bundle": ("agent.tar.gz", agent_bundle, "application/gzip")},
        )
        resp.raise_for_status()
        session_id = str(resp.json()["session_id"])
        session = await self._client.sessions.get(session_id)
        self._chat = SessionsChat(
            namespace=self._client.sessions,
            files_uploader=None,
            files_getter=None,
            session=session,
        )
        await self._client.sessions.set_model_override(
            session_id,
            model_override=self.model,
            silent=True,
        )
        if self.reasoning_effort:
            await self._client.sessions.set_reasoning_effort(
                session_id,
                reasoning_effort=self.reasoning_effort,
            )
        self._runner_id = await launch_or_reuse_daemon_runner(
            self._http,
            host_id=host_id,
            session_id=session_id,
            workspace=str(self.run_dir),
        )
        await wait_for_runner_online(self._http, self._runner_id, timeout_s=90)

    async def _resolve_claude_host(self) -> str:
        resp = await self._http.get(f"{self.server_url}/v1/hosts")
        resp.raise_for_status()
        for h in resp.json().get("hosts", []):
            if h.get("status") == "online" and h.get("configured_harnesses", {}).get(
                "claude-native"
            ):
                return h["host_id"]
        raise RuntimeError("no online host with claude-native configured")

    async def send(self, text: str) -> TurnResult:
        # ONE wall-clock budget per send: the soft checks below pre-empt every wait
        # against `deadline`; the timer cancels whatever server call, back-off or
        # retry sleep is still in flight when the same instant passes. A cancelled
        # inject is the unknown-delivery state TIMEOUT names — never re-sent.
        deadline = _now() + self.turn_timeout_s
        try:
            async with asyncio.timeout(self.turn_timeout_s):
                result = await self._send_once(text, deadline)
                for _ in range(self.send_retry_attempts):
                    if (
                        result.status != TurnStatus.FAILED  # rows 2, 4, 5: never re-sent
                        or deadline - _now() <= self.send_retry_wait_s  # no budget to wait for it
                        or not await self._resend_allowed()
                    ):
                        return result
                    # rows 1/3: failed and no new text — the inject (likely) never landed
                    await asyncio.sleep(self.send_retry_wait_s)
                    result = await self._send_once(text, deadline)
                return result
        except TimeoutError:
            return self._timed_out()

    def _timed_out(self) -> TurnResult:
        # nothing is read at expiry; artifact_exists=False means "not observed"
        return TurnResult(TurnStatus.TIMEOUT, "", False)

    async def _resend_allowed(self) -> bool:
        """Rows 1/3 (docs/design/runner.md): whether a FAILED turn with no new
        assistant text is safe to re-send. True when no error label is set (sim/
        judge sessions set none, #39 — row 3) or the label says the injection
        itself never landed (row 1). False for any other present code (e.g.
        `model_error` — a delivered failure; re-sending could double-deliver) and
        False when the label read itself fails (unknown is not "no label")."""
        try:
            # `sessions.get` raises on >= 400 and on any body that is not a Session
            # (a redirect, the web UI's HTML 200) — all land here, not in row 3
            async with asyncio.timeout(_LABEL_READ_S):
                labels = (await self._client.sessions.get(self._chat.session_id)).labels or {}
        except Exception:
            return False
        code = labels.get("omnigent.last_task_error_code")
        if not code:
            return True  # row 3
        return code == "runner_error" and (
            "not delivered" in labels.get("omnigent.last_task_error_message", "")
        )  # row 1

    async def _send_once(self, text: str, deadline: float) -> TurnResult:
        n_before = n_assistant_messages(await self._list_items())
        self._stall = None
        if _now() >= deadline:
            return self._timed_out()  # budget gone before the inject
        async for ev in self._chat.send(text):  # inject; envelope completes fast
            self._captured.append(to_jsonable(ev))
        status = await self._wait_idle(deadline)
        items = await self._list_items()
        # Settle: an idle status with no NEW assistant message is either the
        # pickup/persist race (a live judge returned an empty verdict this way) or
        # the agent still mid-turn behind a lying idle (todo-003: plan being
        # written) — keep polling until the reply lands or the send's budget
        # (`deadline`) expires.
        while (
            status == TurnStatus.IDLE
            and not new_assistant_text(items, n_before)
            and _now() < deadline
        ):
            await asyncio.sleep(self.settle_poll_s)
            status = await self._wait_idle(deadline)
            items = await self._list_items()
        if status == TurnStatus.IDLE and not new_assistant_text(items, n_before):
            # Idle but silent past the budget: the turn never completed. Injecting
            # now would hit a busy terminal (message lost, session failed) — fail
            # the turn honestly instead.
            status = TurnStatus.TIMEOUT
        flaked = False
        if status == TurnStatus.FAILED and new_assistant_text(items, n_before):
            # row 2: the reply landed, then the server flaked — a completed turn
            status, flaked = TurnStatus.IDLE, True
            print(
                "[flowbench] turn flaked: server said failed after the reply landed; "
                "using the emitted text",
                file=sys.stderr,
            )
        return TurnResult(
            status=status,
            assistant_text=last_assistant_text(items),
            artifact_exists=(await asyncio.to_thread(self.artifact_path)) is not None,
            flaked=flaked,
            **(self._stall or {}),
        )

    async def _read_retry(self, op, attempts: int = 4):
        """Retry a READ-ONLY server call through transient transport failures.
        A single httpx.ReadError during status/items polling killed a whole live
        run; polls are idempotent so retrying is always safe. Sends are NEVER
        retried here — a lost-then-retried inject could double-deliver."""
        import httpx

        for i in range(attempts):
            try:
                return await op()
            except httpx.HTTPError:
                if i == attempts - 1:
                    raise
                await asyncio.sleep(2.0 * (i + 1))

    async def _list_items(self) -> list[dict]:
        """The FULL item list. The server caps a page at 200; an unpaginated read
        froze the settle check once a session outgrew it (todo-app-002/004: every
        turn past item #200 burned the whole turn cap and returned 'timeout')."""
        items: list[dict] = []
        after = None
        while True:
            page = await self._read_retry(
                lambda after=after: self._client.sessions.list_items(
                    self._chat.session_id, order="asc", limit=_PAGE, after=after
                )
            )
            items.extend(page)
            if len(page) < _PAGE:
                return items
            after = page[-1]["id"]

    async def _snapshot(self) -> dict:
        """Raw `GET /v1/sessions/{id}`: status plus the stall signals. Read raw —
        the client's `Session` dataclass drops `updated_at` and the pending
        elicitations, which made the watchdog blind in its first live run."""
        resp = await self._http.get(f"/v1/sessions/{self._chat.session_id}")
        resp.raise_for_status()
        snap = resp.json()
        if snap.get("status") == TurnStatus.IDLE:
            # An idle main agent whose dispatched sub-agent is still running is
            # parked on its OWN work, not awaiting the user: omnigent wakes it with
            # a task-notification when the child finishes. Read the children live
            # (the event stream races the session end and can miss the settle).
            snap["busy_children"] = [
                c.get("updated_at") for c in await self._children() if c.get("busy")
            ]
        return snap

    async def _children(self) -> list[dict]:
        """All child sessions, paged (the endpoint is newest-first with a small
        default page; an old, still-busy child must not hide behind idle ones)."""
        out: list[dict] = []
        after = None
        while True:
            url = f"/v1/sessions/{self._chat.session_id}/child_sessions?limit={_PAGE}"
            resp = await self._http.get(url + (f"&after={after}" if after else ""))
            resp.raise_for_status()
            body = resp.json()
            out.extend(body.get("data", []))
            if not body.get("has_more"):
                return out
            after = body.get("last_id") or out[-1]["id"]

    async def _wait_idle(self, deadline: float, min_wait: float = 4.0) -> TurnStatus | str:
        """Poll the raw session status until a turn boundary, or until `deadline`
        (the send's single wall-clock budget) passes. Every documented omnigent
        status (`idle`/`running`/`failed`) and every flowbench-derived one
        (`timeout`/`stalled`) returns as a `TurnStatus`; an undocumented server
        status passes through verbatim (decisions #7) — no coercion, no
        fallback, no new control flow."""
        start, seen_running = _now(), False
        heartbeat, last_beat = None, start
        st, prompt_polls = None, 0
        had_children, cleared_at = False, None
        while _now() < deadline:
            snap = await self._read_retry(self._snapshot)
            st = snap.get("status")
            busy_children = snap.get("busy_children") or []
            if st == TurnStatus.IDLE and busy_children:
                st = TurnStatus.RUNNING  # parked on its own sub-agent: still this turn
                had_children, cleared_at = True, None
            elif st == TurnStatus.IDLE and had_children:
                # children just finished: arm the wake-up wait once per clearing
                had_children, cleared_at = False, _now()
            elif st == TurnStatus.RUNNING:
                had_children, cleared_at = False, None  # the wake-up turn ran
            if st == TurnStatus.RUNNING:
                seen_running = True
                # any prompt nobody can answer: a policy/permission elicitation
                # or the terminal itself waiting (trust dialog, login) — #61. Two
                # consecutive polls: a real dialog persists across 1.5 s, a
                # one-poll flicker does not.
                prompt_polls = prompt_polls + 1 if any(snap.get(k) for k in _PROMPT_KEYS) else 0
                if prompt_polls >= 2:
                    return await self._stalled("prompt")
                beat = (snap.get("updated_at"), *busy_children)
                if beat != heartbeat:
                    heartbeat, last_beat = beat, _now()
                elif _now() - last_beat >= self.stall_s:
                    return await self._stalled("no_progress")
            if st == TurnStatus.FAILED:
                return TurnStatus.FAILED
            settled = seen_running or _now() - start >= min_wait
            woke = cleared_at is None or _now() - cleared_at >= self.child_wake_s
            if st == TurnStatus.IDLE and settled and woke:
                return TurnStatus.IDLE
            await asyncio.sleep(1.5)
        # Cap hit. An idle here was withheld on purpose (unsettled, or wake-up
        # pending) — report it as the unfinished turn it is, never as idle.
        return TurnStatus.TIMEOUT if not st or st == TurnStatus.IDLE else st

    async def _stalled(self, reason: str) -> TurnStatus:
        self._stall = {"stall_reason": reason, "pane_tail": await self._pane_tail()}
        return TurnStatus.STALLED

    async def _capture_pane(self, meta: dict) -> bytes:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "-S",
            meta["tmux_socket"],
            "capture-pane",
            "-p",
            "-t",
            meta["tmux_target"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out

    async def _pane_tail(self, lines: int = 40) -> str | None:
        """What the agent's terminal shows right now — the question it is stuck
        on. Best effort: None when the runner is offline or tmux is gone."""
        try:
            resp = await self._http.get(f"/v1/sessions/{self._chat.session_id}/resources")
            term = next(r for r in resp.json()["data"] if r.get("type") == "terminal")
            meta = term["metadata"]
            # a wedged tmux server must not wedge the watchdog: 5 s, then None
            out = await asyncio.wait_for(self._capture_pane(meta), 5)
            return "\n".join(out.decode(errors="replace").rstrip().splitlines()[-lines:])
        except Exception:
            return None

    def artifact_path(self) -> Path | None:
        cand = self.run_dir / self.artifact_name
        if cand.exists():
            return cand
        hits = list(self.run_dir.rglob(self.artifact_name))
        return hits[0] if hits else None

    def _conversation_id(self) -> str | None:
        """The `conv_…` id (carried on every streamed event) used by the omnigent
        web UI route. Survives the run, so it's the handle for browsing AND for
        jumping into the live session as a human."""
        for ev in self._captured:
            cid = ev.get("conversation_id") if isinstance(ev, dict) else None
            if cid:
                return cid
        return None

    def conversation_url(self) -> str | None:
        cid = self._conversation_id()
        return f"{self.server_url}/c/{cid}" if cid else None

    async def _context_tokens(self) -> int | None:
        """Final context size from the session labels — the cost signal a
        comparison needs next to the verdict (a win at 2x the tokens is a
        different result). None when the label is absent/unreadable."""
        if self._chat is None:
            return None
        try:
            async with asyncio.timeout(_LABEL_READ_S):
                labels = (await self._client.sessions.get(self._chat.session_id)).labels or {}
            raw = labels.get("omnigent.last_context_tokens")
            return int(raw) if raw else None
        except Exception:
            return None

    async def capture_session(self) -> dict[str, Any]:
        items = await self._list_items()
        items = dedup_items(items)  # clean: drop capture-doubles + control injections
        artifact = self.artifact_path()
        return {
            "context_tokens": await self._context_tokens(),
            "items": items,
            "events": self._captured,
            "duration_s": round(time.monotonic() - self._started, 1),
            "artifact_exists": artifact is not None,
            "artifact_path": str(artifact) if artifact else None,
            "artifact_text": artifact.read_text() if artifact else None,
            "model": self.model,
            "driver": "omnigent",
            # Handles for resuming the SUT after the run (the session is left alive
            # on purpose — see close()).
            "session_id": self._chat.session_id if self._chat else None,
            "conversation_id": self._conversation_id(),
            "conversation_url": self.conversation_url(),
        }

    async def close(self) -> None:
        # Closes only our HTTP clients. The omnigent session, its daemon runner, and
        # the detached tmux/claude process are LEFT ALIVE on purpose — so a human can
        # open conversation_url() and continue the SUT session the simulator drove.
        # (Clean up leftover sessions later with `just clean-tmux`.)
        if self._closed:
            return
        self._closed = True
        for closer in (self._http, self._client):
            try:
                if closer is not None:
                    await closer.aclose()
            except Exception:
                pass
