"""The per-flow bundle: render_config emits harness + the host-skill filter, and
_build_bundle copies each flow's skill dirs and MCP yamls into the omnigent bundle
layout the claude-native bridge reads (<bundle>/skills/<name>/, tools/mcp/)."""

import io
import tarfile
from pathlib import Path

from flowbench.runner.driver import OmnigentDriver


def _extract(bundle: bytes, dest: Path) -> Path:
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        tar.extractall(dest)
    return dest


def test_render_config_emits_harness_and_skills_filter(tmp_path):
    d = OmnigentDriver(
        run_dir=tmp_path, artifact_name="tasks.json", harness="claude-native", skills="none"
    )
    cfg = d.render_config()
    assert "harness: claude-native" in cfg
    assert "skills: none" in cfg
    assert "prompt:" not in cfg  # still no injected system prompt


def test_render_config_omits_skills_when_all(tmp_path):
    # "all" is omnigent's default, so nothing is written — baseline stays vanilla.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="tasks.json")
    assert "skills:" not in d.render_config()


def test_render_config_skills_list_is_flow_yaml(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="tasks.json", skills=["a", "b"])
    assert "skills: [a, b]" in d.render_config()


def test_build_bundle_copies_skill_dirs_and_mcp(tmp_path):
    # two fake skills (each a dir with SKILL.md) + one MCP yaml
    skills_src = tmp_path / "src"
    for name in ("brainstorming", "tdd"):
        d = skills_src / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}")
    mcp = tmp_path / "adf.yaml"
    mcp.write_text("transport: http")

    drv = OmnigentDriver(
        run_dir=tmp_path / "ws",
        artifact_name="tasks.json",
        skills="none",
        skill_dirs=[skills_src / "brainstorming", skills_src / "tdd"],
        mcp_files=[mcp],
    )
    out = _extract(drv._build_bundle(), tmp_path / "out")

    assert (out / "config.yaml").exists()
    assert (out / "skills" / "brainstorming" / "SKILL.md").read_text() == "# brainstorming"
    assert (out / "skills" / "tdd" / "SKILL.md").exists()
    assert (out / "tools" / "mcp" / "adf.yaml").read_text() == "transport: http"


def test_build_bundle_baseline_has_no_skills_dir(tmp_path):
    # the baseline flow ships an empty bundle — nothing added.
    drv = OmnigentDriver(run_dir=tmp_path / "ws", artifact_name="tasks.json")
    out = _extract(drv._build_bundle(), tmp_path / "out")
    assert (out / "config.yaml").exists()
    assert not (out / "skills").exists()
    assert not (out / "tools").exists()
