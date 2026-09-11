"""Driver config: custom prompt override works, but the DEFAULT is a neutral
vanilla-Claude-Code prompt with NO behavioural steering (bug-3 fix)."""

import flowbench.driver
import flowbench.runner.driver
from flowbench.driver import OmnigentDriver


def test_render_config_embeds_custom_prompt(tmp_path):
    d = OmnigentDriver(
        run_dir=tmp_path,
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
    d = OmnigentDriver(run_dir=tmp_path)
    assert d.agent_name == "claude_code" != "account_summarizer"
    assert d.agent_prompt is None
    cfg = d.render_config()
    assert "prompt:" not in cfg


def test_git_init_repo_is_gone():
    """The workspace is the case's declaration now (#158): nothing in the driver
    inits a repo, and no caller reaches the old helper through either path."""
    assert not hasattr(flowbench.driver, "git_init_repo")
    assert not hasattr(flowbench.runner.driver, "git_init_repo")


def test_driver_accepts_reasoning_effort():
    from pathlib import Path

    d = OmnigentDriver(run_dir=Path("/tmp/x"))
    assert d.reasoning_effort is None  # default: unset, base behavior unchanged
    d2 = OmnigentDriver(run_dir=Path("/tmp/x"), reasoning_effort="xhigh")
    assert d2.reasoning_effort == "xhigh"


def test_create_metadata_omits_title_and_project_by_default(tmp_path):
    # Defaults unset -> only launch args, no title / labels (server default kept).
    d = OmnigentDriver(run_dir=tmp_path)
    meta = d._create_metadata()
    args = meta["terminal_launch_args"]
    assert args[:2] == ["--disallowedTools", "AskUserQuestion"]
    assert args[2:] == ["--permission-mode", "bypassPermissions"]
    assert "title" not in meta
    assert "labels" not in meta


def test_create_metadata_includes_title_and_project_when_set(tmp_path):
    d = OmnigentDriver(
        run_dir=tmp_path,
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
    d = OmnigentDriver(run_dir=tmp_path, harness="codex-native")
    args = d._create_metadata()["terminal_launch_args"]
    assert args == ["--ask-for-approval", "never", "--sandbox", "workspace-write"]


def test_create_metadata_unknown_harness_gets_no_flags(tmp_path):
    # No foreign flags for harnesses we haven't mapped: empty is the safe default.
    d = OmnigentDriver(run_dir=tmp_path, harness="qwen-native")
    assert d._create_metadata()["terminal_launch_args"] == []


def test_create_metadata_claude_native_flags(tmp_path):
    # The exact flag list every claude-native flow launches with: no allowlist, no
    # prompts (#52) — identical for every flow, so comparability holds.
    d = OmnigentDriver(run_dir=tmp_path, harness="claude-native")
    args = d._create_metadata()["terminal_launch_args"]
    assert args == [
        "--disallowedTools",
        "AskUserQuestion",
        "--permission-mode",
        "bypassPermissions",
    ]
    assert "--allowedTools" not in args
