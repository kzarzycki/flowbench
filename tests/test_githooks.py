"""The post-checkout hook binds each worktree to one branch (`.githooks/post-checkout`)."""

import os
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".githooks"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull,
}
ENV.pop("GIT_REBIND", None)


def git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env or ENV, capture_output=True, text=True)


def branch(cwd: Path) -> str:
    return git(cwd, "symbolic-ref", "--short", "HEAD").stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "master")
    git(r, "config", "core.hooksPath", str(HOOKS))
    (r / "f").write_text("1")
    git(r, "add", "f")
    git(r, "commit", "-qm", "init")
    git(r, "switch", "-q", "master")  # first branch checkout binds the main worktree
    return r


def test_main_worktree_rejects_other_branch(repo: Path):
    res = git(repo, "switch", "-c", "feat/x")
    assert res.returncode != 0
    assert "bound to 'master'" in res.stderr
    assert branch(repo) == "master"


def test_linked_worktree_is_bound_to_its_branch(repo: Path, tmp_path: Path):
    wt = tmp_path / "repo--x"
    assert git(repo, "worktree", "add", "-q", str(wt), "-b", "feat/x").returncode == 0
    assert branch(wt) == "feat/x"
    res = git(wt, "switch", "-c", "feat/y")
    assert res.returncode != 0
    assert branch(wt) == "feat/x"
    assert branch(repo) == "master"  # bindings are per worktree


def test_file_checkout_and_detached_head_pass(repo: Path):
    (repo / "f").write_text("2")
    assert git(repo, "checkout", "--", "f").returncode == 0
    assert git(repo, "checkout", "-q", "--detach").returncode == 0
    assert git(repo, "switch", "-q", "master").returncode == 0


def test_rebind_is_explicit(repo: Path):
    res = git(repo, "switch", "-c", "feat/x", env={**ENV, "GIT_REBIND": "1"})
    assert res.returncode == 0 and branch(repo) == "feat/x"
    assert git(repo, "switch", "master").returncode != 0
    assert branch(repo) == "feat/x"
