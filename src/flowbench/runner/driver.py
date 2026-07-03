"""The ONE module that knows omnigent exists.

Everything omnigent-specific lives here behind `AgentDriver`: starting a local
server's session, pinning the subscription model, disabling the interactive
question card, the status-driven turn boundary, reading the structured
transcript, and teardown. The solver depends only on the abstract interface, so
swapping omnigent for another REPL driver (or a fake, in tests) changes nothing
upstream.

The recipe here is exactly what the live probe proved (subscription-billed,
multi-turn, artifact written). Two hard-won settings:
- model pinned (the user's own CLI default may be an unavailable model);
- `--disallowedTools AskUserQuestion` (the interactive card blocks the tmux
  input prompt, deadlocking follow-up turns).
"""

from __future__ import annotations

import abc
import asyncio
import io
import json
import os
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TurnResult:
    status: str  # "idle" (turn settled) | "failed" | "timeout"
    assistant_text: str  # latest assistant-authored text after the turn
    artifact_exists: bool
    child_busy: bool = False  # a dispatched sub-agent is still running (agent is
    # parked on its OWN work, not awaiting the user)


class AgentDriver(abc.ABC):
    """Drive a real agent REPL over a multi-turn task. Async + teardown-safe."""

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def send(self, text: str) -> TurnResult: ...

    @abc.abstractmethod
    async def capture_session(self) -> dict[str, Any]:
        """The transcript + run fields the normalizer consumes."""

    @abc.abstractmethod
    def artifact_path(self) -> Path | None: ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down. MUST be idempotent (safe to call after a failure)."""


# --- transcript helpers (pure; shared with the normalizer's notion of text) ---


def _item_text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Same accepted part-types as normalize._message_text so the driver's
        # notion of "assistant text" can't diverge from the scorer's.
        return "".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") in (None, "text", "input_text", "output_text")
        )
    return ""


def last_assistant_text(items: list[dict]) -> str:
    for it in reversed(items):
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "assistant":
            txt = _item_text(it)
            if txt.strip():
                return txt
    return ""


def n_assistant_messages(items: list[dict]) -> int:
    return sum(
        1
        for it in items
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "assistant"
    )


# Harness control injections that are NOT part of the user/agent conversation —
# Claude Code surfaces sub-agent completions as role=user `<task-notification>`
# messages. They must not pollute the transcript or be read as conversation.
_CONTROL_PREFIXES = ("<task-notification>",)


def is_control_message(text: str) -> bool:
    return text.lstrip().startswith(_CONTROL_PREFIXES)


def any_child_busy(events: list[dict]) -> bool:
    """True when the agent has a background sub-agent still running, per the latest
    per-child `busy` state in the captured event stream. omnigent surfaces each
    sub-agent (Task dispatch) as `SessionChildSessionUpdatedEvent` carrying
    `child.busy`. An agent that dispatched a sub-agent parks at the prompt (idle)
    while it runs — it's waiting on its OWN work, not on the user, so the loop can
    nudge it forward without spending a simulated-user turn."""
    busy: dict[str, bool] = {}
    for ev in events:
        if not isinstance(ev, dict) or ev.get("__type__") != "SessionChildSessionUpdatedEvent":
            continue
        child = ev.get("child") or {}
        cid = ev.get("child_session_id") or child.get("id")
        if cid is not None:
            busy[cid] = bool(child.get("busy"))
    return any(busy.values())


def dedup_items(items: list[dict]) -> list[dict]:
    """Clean the captured conversation: drop (1) the consecutive duplicate message
    omnigent records for every injected turn, and (2) harness control injections
    (`<task-notification>`). Non-message items pass through untouched. A duplicate
    is a message whose (role, text) equals the previous KEPT message's — real
    turns are always separated by the other party's message, so this only ever
    collapses the capture artifact."""
    out: list[dict] = []
    last_key: tuple[str, str] | None = None
    for it in items:
        if not (isinstance(it, dict) and it.get("type") == "message"):
            out.append(it)
            continue
        text = _item_text(it)
        if is_control_message(text):
            continue
        key = (it.get("role", ""), text)
        if key == last_key:
            continue
        last_key = key
        out.append(it)
    return out


# --- the real driver -------------------------------------------------------

# No default system prompt on purpose: for the claude-native harness omnigent
# never passes the bundle `prompt:` to the `claude` CLI (`augment_claude_args`
# adds no --system-prompt, and there is no initial-prompt injection), so it would
# be inert anyway — and a non-empty default only confuses anyone reading the
# omnigent session into thinking the SUT is steered. The SUT runs as VANILLA
# Claude Code against the host ~/.claude config (skills included); the task is
# delivered as the first user message. Set `agent_prompt` only to deliberately
# steer a harness that DOES honour it (e.g. claude-sdk).
AGENT_CONFIG = """\
spec_version: 1
name: {name}
description: {description}
executor:
  type: omnigent
  config:
    harness: {harness}
    permission_mode: bypassPermissions
os_env:
  type: caller_process
  cwd: {cwd}
  sandbox:
    type: none
"""


def _indent(text: str, n: int = 2) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.splitlines())


def git_init_repo(path: Path) -> None:
    """Init a git repo with an initial commit so the workflow can branch/commit."""
    import subprocess

    path.mkdir(parents=True, exist_ok=True)

    def run(*a: str):
        return subprocess.run(
            ["git", "-C", str(path), *a], check=True, capture_output=True, text=True
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
    artifact_name: str
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
    # `idle` can be observed before the runner picks the turn up (fresh session),
    # before the reply item persists, or while the agent is still MID-TURN (bridge
    # race seen live: injecting then hits a busy terminal and the run dies). An
    # idle turn is trusted only once a NEW assistant message has landed; None =
    # settle for the full turn budget. Expiry -> "timeout", never a stale reply.
    settle_timeout_s: float | None = None
    settle_poll_s: float = 2.0
    # Per-flow bundle inputs (see runner.flow.Flow). Defaults reproduce the vanilla
    # baseline: claude-native, host skills visible, nothing added to the bundle.
    harness: str = "claude-native"
    skills: str | list[str] = "all"  # -> config.yaml top-level skills:
    skill_dirs: list[Path] = field(default_factory=list)
    mcp_files: list[Path] = field(default_factory=list)

    # internal state
    _started: float = 0.0
    _captured: list[dict] = field(default_factory=list)
    _closed: bool = False
    _http: Any = None
    _client: Any = None
    _chat: Any = None
    _runner_id: str | None = None

    def render_config(self) -> str:
        cfg = AGENT_CONFIG.format(
            name=self.agent_name,
            description=self.agent_description,
            cwd=str(self.run_dir),
            harness=self.harness,
        )
        # Host-skill filter: "all" is omnigent's default, so emit nothing; "none"
        # suppresses host ~/.claude skills (bundle skills still load); a list names
        # specific sources. This is the ONLY per-flow knob besides bundle contents.
        if self.skills != "all":
            if isinstance(self.skills, (list, tuple)):
                cfg += "skills: [" + ", ".join(self.skills) + "]\n"
            else:
                cfg += f"skills: {self.skills}\n"
        # Emit a `prompt:` block only when explicitly set (inert for claude-native).
        if self.agent_prompt:
            cfg += "prompt: |\n" + _indent(self.agent_prompt, 2) + "\n"
        return cfg

    def _build_bundle(self) -> bytes:
        import shutil
        import tempfile

        agent_dir = Path(tempfile.mkdtemp(prefix="flowbench_drv_")) / "_agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "config.yaml").write_text(self.render_config())
        # Per-flow skills: each entry is ONE skill dir (holds a SKILL.md) -> the
        # bridge surfaces <bundle>/skills/<name>/ via --plugin-dir, host-independent.
        for src in self.skill_dirs:
            shutil.copytree(Path(src), agent_dir / "skills" / Path(src).name)
        # Per-flow MCP servers: <bundle>/tools/mcp/<name>.yaml.
        if self.mcp_files:
            mcp_dir = agent_dir / "tools" / "mcp"
            mcp_dir.mkdir(parents=True, exist_ok=True)
            for mcp in self.mcp_files:
                shutil.copy(Path(mcp), mcp_dir / Path(mcp).name)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(agent_dir, arcname=".")
        return buf.getvalue()

    async def start(self) -> None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is set — would defeat subscription billing.")
        import httpx
        from omnigent.host.daemon_launch import (
            launch_or_reuse_daemon_runner,
            wait_for_runner_online,
        )
        from omnigent_client import OmnigentClient
        from omnigent_client._sessions_chat import SessionsChat

        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.git_init and not (self.run_dir / ".git").exists():
            git_init_repo(self.run_dir)
        self._started = time.monotonic()
        self._http = httpx.AsyncClient(base_url=self.server_url, timeout=60.0)
        self._client = OmnigentClient(base_url=self.server_url)

        host_id = await self._resolve_claude_host()
        bundle = self._build_bundle()

        # Create with --disallowedTools so claude asks in plain text (the card
        # otherwise blocks the tmux prompt and deadlocks turn 2+).
        resp = await self._client.sessions._http.post(
            f"{self._client.sessions._base}/v1/sessions",
            data={
                "metadata": json.dumps(
                    {"terminal_launch_args": ["--disallowedTools", "AskUserQuestion"]}
                )
            },
            files={"bundle": ("agent.tar.gz", bundle, "application/gzip")},
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
        n_before = n_assistant_messages(await self._list_items())
        async for ev in self._chat.send(text):  # inject; envelope completes fast
            self._captured.append(_to_jsonable(ev))
        status = await self._wait_idle()
        items = await self._list_items()
        # Settle: an idle status with no NEW assistant message is either the
        # pickup/persist race (a live judge returned an empty verdict this way) or
        # the agent still mid-turn behind a lying idle (todo-003: plan being
        # written) — keep polling until the reply lands or the budget expires.
        settle = time.monotonic() + (
            self.settle_timeout_s if self.settle_timeout_s is not None else self.turn_timeout_s
        )
        while (
            status == "idle"
            and n_assistant_messages(items) <= n_before
            and time.monotonic() < settle
        ):
            await asyncio.sleep(self.settle_poll_s)
            status = await self._wait_idle()
            items = await self._list_items()
        if status == "idle" and n_assistant_messages(items) <= n_before:
            # Idle but silent past the budget: the turn never completed. Injecting
            # now would hit a busy terminal (message lost, session failed) — fail
            # the turn honestly instead.
            status = "timeout"
        return TurnResult(
            status=status,
            assistant_text=last_assistant_text(items),
            artifact_exists=self.artifact_path() is not None,
            child_busy=any_child_busy(self._captured),
        )

    async def _list_items(self) -> list[dict]:
        return await self._client.sessions.list_items(self._chat.session_id, order="asc", limit=200)

    async def _wait_idle(self, min_wait: float = 4.0) -> str:
        start, seen_running = time.monotonic(), False
        while time.monotonic() - start < self.turn_timeout_s:
            await self._chat.refresh()
            st = self._chat.status
            if st == "running":
                seen_running = True
            if st == "failed":
                return "failed"
            if st == "idle" and (seen_running or time.monotonic() - start >= min_wait):
                return "idle"
            await asyncio.sleep(1.5)
        return self._chat.status or "timeout"

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

    async def capture_session(self) -> dict[str, Any]:
        items = await self._list_items()
        items = dedup_items(items)  # clean: drop capture-doubles + control injections
        artifact = self.artifact_path()
        return {
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


def _to_jsonable(ev: object) -> dict:
    import dataclasses

    fn = getattr(ev, "model_dump", None)
    if callable(fn):
        try:
            return {"__type__": type(ev).__name__, **fn(mode="json")}
        except Exception:
            pass
    if dataclasses.is_dataclass(ev):
        return {"__type__": type(ev).__name__, **dataclasses.asdict(ev)}
    return {"__type__": type(ev).__name__, "repr": repr(ev)[:300]}
