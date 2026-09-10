"""agent_review: verdict survives a native-TUI flip-to-failed, and each
harness resolves its own model (issue #36)."""

import importlib.util
from pathlib import Path

import pytest

from flowbench.driver import TurnResult

_spec = importlib.util.spec_from_file_location(
    "agent_review", Path(__file__).resolve().parents[1] / "engineering-loop" / "agent_review.py"
)
agent_review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent_review)


def _result(status, text):
    return TurnResult(status=status, assistant_text=text)


def test_idle_returns_verdict():
    assert agent_review.verdict_from(_result("idle", "APPROVE")) == "APPROVE"


def test_failed_with_text_still_returns_verdict(capsys):
    # codex-native flips to failed right after emitting — the verdict is valid.
    assert agent_review.verdict_from(_result("failed", "REVISE: 1. ...")) == "REVISE: 1. ..."
    assert "using the emitted verdict" in capsys.readouterr().err


def test_empty_turn_exits_for_fallback():
    with pytest.raises(SystemExit):
        agent_review.verdict_from(_result("failed", "   "))


def test_codex_model_reads_the_cli_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('model = "some-flagship"\nmodel_reasoning_effort = "medium"\n')
    monkeypatch.setattr(agent_review, "CODEX_CONFIG", cfg)
    assert agent_review.codex_model() == "some-flagship"


def test_codex_model_exits_when_unset(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('model_reasoning_effort = "medium"\n')
    monkeypatch.setattr(agent_review, "CODEX_CONFIG", cfg)
    with pytest.raises(SystemExit):
        agent_review.codex_model()


def test_codex_model_exits_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_review, "CODEX_CONFIG", tmp_path / "missing.toml")
    with pytest.raises(SystemExit):
        agent_review.codex_model()


def test_codex_harness_resolves_the_cli_model(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('model = "some-flagship"\n')
    monkeypatch.setattr(agent_review, "CODEX_CONFIG", cfg)
    assert agent_review.resolve_model("codex-native") == "some-flagship"


def test_other_harnesses_take_the_harness_default():
    # No resolver → model_override=None → omnigent falls back to the agent spec.
    for harness in ("antigravity-native", "claude-native", "qwen-native"):
        assert agent_review.resolve_model(harness) is None


def test_default_harness_is_codex():
    assert agent_review.DEFAULT_HARNESS == "codex-native"
