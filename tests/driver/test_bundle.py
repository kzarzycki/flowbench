"""The per-flow bundle: render_config emits harness + the host-skill filter, and
_build_bundle copies each flow's skill dirs and MCP yamls into the omnigent bundle
layout the claude-native bridge reads (<bundle>/skills/<name>/, tools/mcp/)."""

import hashlib
import inspect
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

from flowbench.driver import OmnigentDriver, omnigent
from flowbench.driver import bundle as bundle_mod
from flowbench.driver.bundle import BundleSpec, build_bundle, render_config, session_metadata


def _extract(bundle: bytes, dest: Path) -> Path:
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        tar.extractall(dest)
    return dest


def test_render_config_emits_harness_and_skills_filter(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, harness="claude-native", skills="none")
    cfg = d.render_config()
    assert "harness: claude-native" in cfg
    assert "skills: none" in cfg
    assert "prompt:" not in cfg  # still no injected system prompt


def test_render_config_omits_skills_when_all(tmp_path):
    # "all" is omnigent's default, so nothing is written — baseline stays vanilla.
    d = OmnigentDriver(run_dir=tmp_path)
    assert "skills:" not in d.render_config()


def test_render_config_skills_list_is_flow_yaml(tmp_path):
    d = OmnigentDriver(run_dir=tmp_path, skills=["a", "b"])
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
    drv = OmnigentDriver(run_dir=tmp_path / "ws")
    out = _extract(drv._build_bundle(), tmp_path / "out")
    assert (out / "config.yaml").exists()
    assert not (out / "skills").exists()
    assert not (out / "tools").exists()


# --- goldens (AC7): the split must not move a byte of the serialized bundle ---
# Captured from origin/master 1324132 before the split; see the item's gates.md.

_GOLDEN_CONFIG_HEAD = (
    "spec_version: 1\n"
    "name: claude_code\n"
    "description: Vanilla Claude Code under test (subscription; system prompt untouched).\n"
    "executor:\n"
    "  type: omnigent\n"
    "  config:\n"
    "    harness: claude-native\n"
    "    permission_mode: bypassPermissions\n"
    "os_env:\n"
    "  type: caller_process\n"
    "  cwd: {cwd}\n"
    "  sandbox:\n"
    "    type: none\n"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _spec(tmp_path, **kw):
    fields = {
        "run_dir": tmp_path,
        "harness": "claude-native",
        "agent_name": "claude_code",
        "agent_description": (
            "Vanilla Claude Code under test (subscription; system prompt untouched)."
        ),
        "agent_prompt": None,
        "skills": "all",
        "skill_dirs": [],
        "mcp_files": [],
        "session_title": None,
        "project": None,
    }
    fields.update(kw)
    return SimpleNamespace(**fields)


def test_golden_render_config_three_variants(tmp_path):
    head = _GOLDEN_CONFIG_HEAD.format(cwd=tmp_path)
    assert render_config(_spec(tmp_path)) == head
    assert render_config(_spec(tmp_path, skills=["a", "b"])) == head + "skills: [a, b]\n"
    assert (
        render_config(_spec(tmp_path, skills="none", agent_prompt="Be terse.\n\nTwo lines."))
        == head + "skills: none\nprompt: |\n  Be terse.\n\n  Two lines.\n"
    )


def test_golden_bundle_members_and_content_hashes(tmp_path):
    skill_md, mcp_yaml = "# brainstorming\n", "name: fetch\n"
    sk = tmp_path / "src" / "brainstorming"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(skill_md)
    mcp = tmp_path / "src" / "fetch.yaml"
    mcp.write_text(mcp_yaml)
    run_dir = tmp_path / "run"
    spec = _spec(run_dir, skills="none", skill_dirs=[sk], mcp_files=[mcp])

    with tarfile.open(fileobj=io.BytesIO(build_bundle(spec))) as tar:
        rows = sorted(
            (
                m.name,
                "dir" if m.isdir() else "file",
                hashlib.sha256(tar.extractfile(m).read()).hexdigest() if m.isfile() else "",
            )
            for m in tar.getmembers()
        )
    assert [(n, k) for n, k, _ in rows] == [
        (".", "dir"),
        ("./config.yaml", "file"),
        ("./skills", "dir"),
        ("./skills/brainstorming", "dir"),
        ("./skills/brainstorming/SKILL.md", "file"),
        ("./tools", "dir"),
        ("./tools/mcp", "dir"),
        ("./tools/mcp/fetch.yaml", "file"),
    ]
    by_name = {n: h for n, _, h in rows}
    # config.yaml's hash is run_dir-dependent, so pin it against the function
    # that produced it rather than a literal; the other two are fixed inputs.
    assert by_name["./config.yaml"] == hashlib.sha256(render_config(spec).encode()).hexdigest()
    # Each copied file's content, unchanged: the same two hashes gates.md
    # records from origin/master.
    assert by_name["./skills/brainstorming/SKILL.md"] == _sha(skill_md)
    assert by_name["./tools/mcp/fetch.yaml"] == _sha(mcp_yaml)


def test_golden_session_metadata_six_variants(tmp_path):
    claude = ["--disallowedTools", "AskUserQuestion", "--permission-mode", "bypassPermissions"]
    codex = ["--ask-for-approval", "never", "--sandbox", "workspace-write"]
    for harness, args in (("claude-native", claude), ("codex-native", codex), ("other", [])):
        assert session_metadata(_spec(tmp_path, harness=harness)) == {"terminal_launch_args": args}
        assert session_metadata(
            _spec(tmp_path, harness=harness, session_title="flow: sp", project="swe/1")
        ) == {
            "terminal_launch_args": args,
            "title": "flow: sp",
            "labels": {"omni_project": "swe/1"},
        }


def test_functions_need_only_the_bundlespec_fields(tmp_path):
    """The three are pure functions of BundleSpec — a SimpleNamespace carrying
    exactly those fields and nothing else. Reading anything more (notably
    `spec.render_config()`, the natural transcription slip when un-methoding
    `build_bundle`) raises AttributeError here, while the driver-backed tests
    above would stay green because OmnigentDriver still has that method."""
    sk = tmp_path / "s" / "k"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("x\n")
    mcp = tmp_path / "m.yaml"
    mcp.write_text("y\n")
    spec = _spec(tmp_path / "run", skills="none", skill_dirs=[sk], mcp_files=[mcp])
    assert set(vars(spec)) == set(BundleSpec.__annotations__)

    render_config(spec)
    build_bundle(spec)
    session_metadata(spec)


def test_the_bundle_functions_left_the_driver_module():
    """A copy-paste-instead-of-move implementation fails this, and so does
    re-exporting the three from the driver module: `omnigent.py` reaches them
    through the `bundle` module object, so they are not part of its surface."""
    for name in ("render_config", "build_bundle", "session_metadata"):
        assert name not in vars(omnigent), f"{name} is an attribute of driver/omnigent.py"
        fn = getattr(bundle_mod, name)
        assert Path(inspect.getsourcefile(fn)).name == "bundle.py"
