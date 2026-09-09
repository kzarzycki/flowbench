"""The post-checkout hook binds each worktree to one branch (`.githooks/post-checkout`)."""

import os
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".githooks"
ENV = {k: v for k, v in os.environ.items() if k not in {"GIT_REBIND", "GIT_DIR", "GIT_WORK_TREE"}}
ENV.update(
    GIT_AUTHOR_NAME="t",
    GIT_AUTHOR_EMAIL="t@t",
    GIT_COMMITTER_NAME="t",
    GIT_COMMITTER_EMAIL="t@t",
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_SYSTEM=os.devnull,
)


def git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env or ENV, capture_output=True, text=True)


def branch(cwd: Path) -> str:
    return git(cwd, "symbolic-ref", "--short", "HEAD").stdout.strip()


def sha(cwd: Path, ref: str) -> str:
    return git(cwd, "rev-parse", ref).stdout.strip()


def commit(cwd: Path, name: str) -> None:
    (cwd / name).write_text(name)
    git(cwd, "add", name)
    git(cwd, "commit", "-qm", name)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "master")
    git(r, "config", "core.hooksPath", str(HOOKS))
    commit(r, "f")
    git(r, "switch", "-q", "master")  # first branch checkout binds the main worktree
    return r


def test_main_worktree_rejects_other_branch(repo: Path):
    res = git(repo, "switch", "-c", "feat/x")
    assert res.returncode != 0
    assert "bound to 'master'" in res.stderr and "reverted to 'master'" in res.stderr
    assert branch(repo) == "master"


def test_fresh_clone_binds_default_branch_without_bootstrap(repo: Path, tmp_path: Path):
    git(repo, "branch", "feat/a")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    git(clone, "config", "core.hooksPath", str(HOOKS))
    res = git(clone, "switch", "feat/a")  # first checkout after activation
    assert res.returncode != 0 and branch(clone) == "master"


def test_linked_worktree_is_bound_to_its_branch(repo: Path, tmp_path: Path):
    wt = tmp_path / "repo--x"
    assert git(repo, "worktree", "add", "-q", str(wt), "-b", "feat/x").returncode == 0
    assert branch(wt) == "feat/x"
    res = git(wt, "switch", "-c", "feat/y")
    assert res.returncode != 0
    assert branch(wt) == "feat/x"
    assert branch(repo) == "master"  # bindings are per worktree


def test_dirty_tree_survives_the_revert(repo: Path):
    (repo / "f").write_text("edited")
    (repo / "new").write_text("untracked")
    assert git(repo, "switch", "-c", "feat/x").returncode != 0
    assert branch(repo) == "master"
    assert (repo / "f").read_text() == "edited" and (repo / "new").exists()


def test_force_reset_of_target_branch_is_restored(repo: Path):
    git(repo, "switch", "-q", "-c", "feat/b", env={**ENV, "GIT_REBIND": "1"})
    commit(repo, "work")
    tip = sha(repo, "feat/b")
    git(repo, "switch", "-q", "master", env={**ENV, "GIT_REBIND": "1"})
    res = git(repo, "checkout", "-B", "feat/b")  # would reset feat/b to master
    assert res.returncode != 0 and "restored 'feat/b'" in res.stderr
    assert branch(repo) == "master" and sha(repo, "feat/b") == tip


def test_failed_revert_tells_the_truth(repo: Path, tmp_path: Path):
    git(repo, "branch", "feat/b")
    git(repo, "checkout", "-q", "--detach")
    git(repo, "worktree", "add", "-q", str(tmp_path / "wt"), "master")  # master now taken
    res = git(repo, "switch", "feat/b")
    assert res.returncode != 0
    assert "REVERT FAILED" in res.stderr and "reverted to" not in res.stderr
    assert branch(repo) == "feat/b"


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
