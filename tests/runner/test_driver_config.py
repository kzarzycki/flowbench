"""Driver config: custom prompt override works, but the DEFAULT is a neutral
vanilla-Claude-Code prompt with NO behavioural steering (bug-3 fix)."""

import subprocess

from flowbench.runner.driver import OmnigentDriver, git_init_repo


def test_render_config_embeds_custom_prompt(tmp_path):
    d = OmnigentDriver(
        run_dir=tmp_path,
        artifact_name="tasks.json",
        agent_prompt="CUSTOM-AGENT-PROMPT-XYZ",
        agent_description="builds a todo app",
    )
    cfg = d.render_config()
    assert "CUSTOM-AGENT-PROMPT-XYZ" in cfg
    assert "builds a todo app" in cfg
    assert f"cwd: {tmp_path}" in cfg
    # prompt is indented under the YAML `prompt: |` block scalar
    assert "\n  CUSTOM-AGENT-PROMPT-XYZ" in cfg


def test_default_agent_is_vanilla_no_prompt(tmp_path):
    # bug 3: the old default was the spike-1 "account_summarizer" banking persona.
    # The SUT must be vanilla Claude Code — the default carries no leftover
    # persona and emits NO system prompt at all (inert for claude-native anyway).
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="tasks.json")
    assert d.agent_name == "claude_code" != "account_summarizer"
    assert d.agent_prompt is None
    cfg = d.render_config()
    assert "prompt:" not in cfg


def test_git_init_repo_creates_repo(tmp_path):
    git_init_repo(tmp_path)
    assert (tmp_path / ".git").is_dir()
    # has an initial commit so branches/worktrees work
    out = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"], capture_output=True, text=True
    )
    assert out.returncode == 0 and out.stdout.strip()


def test_driver_accepts_reasoning_effort():
    from pathlib import Path

    d = OmnigentDriver(run_dir=Path("/tmp/x"), artifact_name="plan.md")
    assert d.reasoning_effort is None  # default: unset, base behavior unchanged
    d2 = OmnigentDriver(run_dir=Path("/tmp/x"), artifact_name="plan.md", reasoning_effort="xhigh")
    assert d2.reasoning_effort == "xhigh"


def test_create_metadata_omits_title_and_project_by_default(tmp_path):
    # Defaults unset -> only launch args, no title / labels (server default kept).
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md")
    meta = d._create_metadata()
    args = meta["terminal_launch_args"]
    assert args[:2] == ["--disallowedTools", "AskUserQuestion"]
    assert "--permission-mode" in args and "--allowedTools" in args
    assert "title" not in meta
    assert "labels" not in meta


def test_create_metadata_includes_title_and_project_when_set(tmp_path):
    d = OmnigentDriver(
        run_dir=tmp_path,
        artifact_name="plan.md",
        session_title="flow: superpowers",
        project="swe_planning/todo-004",
    )
    meta = d._create_metadata()
    # launch args always present
    assert meta["terminal_launch_args"][:2] == ["--disallowedTools", "AskUserQuestion"]
    assert meta["title"] == "flow: superpowers"
    # project groups sessions via the `omni_project` label the web UI reads
    assert meta["labels"] == {"omni_project": "swe_planning/todo-004"}


def test_create_metadata_codex_native_gets_codex_flags(tmp_path):
    # codex rejects claude-only flags (--disallowedTools etc.) with exit 2,
    # so codex-native sessions get codex's own unattended stance instead.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md", harness="codex-native")
    args = d._create_metadata()["terminal_launch_args"]
    assert args == ["--ask-for-approval", "never", "--sandbox", "workspace-write"]


def test_create_metadata_unknown_harness_gets_no_flags(tmp_path):
    # No foreign flags for harnesses we haven't mapped: empty is the safe default.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md", harness="qwen-native")
    assert d._create_metadata()["terminal_launch_args"] == []


def test_create_metadata_claude_native_flags_unchanged(tmp_path):
    # Byte-identical to the pre-change list — comparability of past runs holds.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md", harness="claude-native")
    args = d._create_metadata()["terminal_launch_args"]
    assert args[:2] == ["--disallowedTools", "AskUserQuestion"]
    assert args[2:4] == ["--permission-mode", "acceptEdits"]
    assert args[4] == "--allowedTools"
