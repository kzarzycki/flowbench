"""Everything that shapes a flow's agent bundle, as pure functions.

`render_config` emits the omnigent agent `config.yaml`; `build_bundle` tars it up
with the flow's MCP files; `session_metadata` is the metadata form part that rides
the same `POST /v1/sessions`. Skills are NOT in the tarball: they are seeded into
the flow's workspace at `<flow_dir>/.claude/skills/<name>/` (`case.seed_workspace`)
and load through the harness's own project convention (#157). All three read only the
`BundleSpec` fields below, so a `Flow` (S03.1) can drive them directly instead
of going through a driver instance.
"""

from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Protocol


class BundleSpec(Protocol):
    """The `Flow`-like fields the three functions read. `OmnigentDriver`
    satisfies it structurally today; `runner.flow.Flow` will once S03.1 widens
    it. Not `runtime_checkable` — nothing isinstance-checks a spec."""

    run_dir: Path
    harness: str
    agent_name: str
    agent_description: str
    agent_prompt: str | None
    skills: str | list[str]
    mcp_files: list[Path]
    session_title: str | None
    project: str | None


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


def render_config(spec: BundleSpec) -> str:
    cfg = AGENT_CONFIG.format(
        name=spec.agent_name,
        description=spec.agent_description,
        cwd=str(spec.run_dir),
        harness=spec.harness,
    )
    # Setting-source filter: "all" is omnigent's default, so emit nothing; "none"
    # loads no sources at all; a list names specific ones. Skills live in the
    # workspace now, so this decides whether the agent ever reads them.
    if spec.skills != "all":
        if isinstance(spec.skills, (list, tuple)):
            cfg += "skills: [" + ", ".join(spec.skills) + "]\n"
        else:
            cfg += f"skills: {spec.skills}\n"
    # Emit a `prompt:` block only when explicitly set (inert for claude-native).
    if spec.agent_prompt:
        cfg += "prompt: |\n" + _indent(spec.agent_prompt, 2) + "\n"
    return cfg


def build_bundle(spec: BundleSpec) -> bytes:
    agent_dir = Path(tempfile.mkdtemp(prefix="flowbench_drv_")) / "_agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "config.yaml").write_text(render_config(spec))
    # No skills branch: `skill_dirs` is seeded into the workspace instead (#157).
    # Carrying them here too would load each skill twice under two names — once as
    # <plugin>:<name> via --plugin-dir and once bare — which contaminates the
    # `Skill`-call ground truth cases score on.
    # Per-flow MCP servers: <bundle>/tools/mcp/<name>.yaml.
    if spec.mcp_files:
        mcp_dir = agent_dir / "tools" / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        for mcp in spec.mcp_files:
            shutil.copy(Path(mcp), mcp_dir / Path(mcp).name)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(agent_dir, arcname=".")
    return buf.getvalue()


def session_metadata(spec: BundleSpec) -> dict[str, Any]:
    """Metadata form part for `POST /v1/sessions`. Launch args are gated on
    the harness — omnigent passes them verbatim to the native CLI, and codex
    rejects claude-only flags (exit 2). Adds a short `title` and an
    `omni_project` label — the field the web UI groups sessions on — only
    when set, so an unset field leaves the server default untouched."""
    if spec.harness == "claude-native":
        launch_args = [
            "--disallowedTools",
            "AskUserQuestion",
            # Permission config MUST ride CLI flags, not the workspace
            # .claude/settings.json: a flow with skills "none" launches with
            # --setting-sources "" (the bridge's host-skill filter), which
            # drops ALL settings files — todo-010's plain flow prompted for
            # Write while superpowers (skills "all") sailed. Flags survive
            # that and are identical for every flow, so comparability holds.
            # bypassPermissions for every case (decision 2026-09-08, #52): a
            # prompt nobody can answer froze todo-app-001 for the whole turn
            # cap (AskUserQuestion is off, the simulator only sees chat). The
            # run dir is isolated; `auto` was rejected because it puts a
            # second, non-deterministic model between the flow and its tools.
            "--permission-mode",
            "bypassPermissions",
        ]
        # A `skills` LIST names Claude Code's setting sources (user/project/local),
        # and flowbench has to emit the flag itself: omnigent maps a list to NOTHING
        # ("treated like all for host sources", omnigent/inner/bundle_skills.py), so
        # the host ~/.claude would stay visible. These launch args are placed BEFORE
        # omnigent's own (`augment_claude_args`), so ours is the only such flag —
        # but only while skills != "none", where omnigent appends
        # `--setting-sources ""` after us and would win. That pairing is rejected at
        # flows.yaml load time.
        if isinstance(spec.skills, (list, tuple)) and spec.skills:
            launch_args += ["--setting-sources", ",".join(spec.skills)]
    elif spec.harness == "codex-native":
        # Codex's unattended stance: never prompt, sandboxed to the workspace.
        launch_args = ["--ask-for-approval", "never", "--sandbox", "workspace-write"]
    elif spec.harness == "antigravity-native":
        # agy's unattended stance, and its ONLY pre-emptive permission control
        # (omnigent harnesses/antigravity_native/launch.py `_SKIP_PERMISSIONS_FLAG`).
        # It has to ride the launch args: omnigent's runner-owned launch — the one
        # this driver uses — passes `permission_mode=None, headless=False`, so the
        # bundle's own `permission_mode: bypassPermissions` never reaches agy.
        # Without it turn 1 of a 3-turn probe stalled for the whole `stall_s` on an
        # unanswerable `request-review` prompt: the todo-app-001 freeze shape (#149).
        launch_args = ["--dangerously-skip-permissions"]
    else:
        launch_args = []
    meta: dict[str, Any] = {"terminal_launch_args": launch_args}
    if spec.session_title is not None:
        meta["title"] = spec.session_title
    if spec.project is not None:
        meta["labels"] = {"omni_project": spec.project}
    return meta
