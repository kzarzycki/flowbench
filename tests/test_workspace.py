"""The starting workspace: what `Workspace` declares and `seed_workspace` makes.

The empty declaration is the interesting one — the engine must create no repo a
case did not ask for — so it is tested as hard as the seeded ones."""

import os
import subprocess
from pathlib import Path

import pytest

from flowbench.case import SEED_COMMIT_DATE, Case, Workspace, seed_workspace

# Anchored, not derived: an empty seed commit is fully determined by the fixed
# identity, message and dates, so this literal is the whole pinning contract in
# one value. Captured from a real run; regenerate only when one of those changes.
EMPTY_SEED_SHA = "6f623369f6553d4da63242489bc626eda279d1b8"  # pragma: allowlist secret


def _no_git_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(flow_dir: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(flow_dir), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_no_git_env(),
    )
    return out.stdout.strip()


def _case_dir(tmp_path: Path) -> Path:
    d = tmp_path / "case"
    d.mkdir()
    return d


def _seed_tree(case_dir: Path, files: dict[str, str], name: str = "seed") -> Path:
    root = case_dir / name
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root


def test_default_declaration_is_empty_and_repoless(tmp_path):
    case_dir = _case_dir(tmp_path)
    flow_dir = tmp_path / "flow"

    assert Case(case_dir).workspace == Workspace(seed=None, git=False)

    record = seed_workspace(Workspace(), case_dir, flow_dir)

    assert record == {"seed": None, "git": False, "seed_files": 0, "seed_commit": None}
    assert list(flow_dir.iterdir()) == []


def test_git_declaration_makes_one_empty_commit(tmp_path):
    case_dir = _case_dir(tmp_path)
    flow_dir = tmp_path / "flow"

    seed_workspace(Workspace(git=True), case_dir, flow_dir)

    assert (flow_dir / ".git").is_dir()
    assert _git(flow_dir, "rev-list", "--count", "HEAD") == "1"
    # No .gitkeep and nothing else: the commit holds exactly the (empty) seed.
    assert _git(flow_dir, "show", "--name-only", "--pretty=") == ""
    assert [p.name for p in flow_dir.iterdir()] == [".git"]


def test_seed_copies_the_tree(tmp_path):
    case_dir = _case_dir(tmp_path)
    _seed_tree(case_dir, {"a.txt": "alpha", "pkg/b.py": "print('b')\n"})
    flow_dir = tmp_path / "flow"

    record = seed_workspace(Workspace(seed="seed"), case_dir, flow_dir)

    assert (flow_dir / "a.txt").read_text() == "alpha"
    assert (flow_dir / "pkg" / "b.py").read_text() == "print('b')\n"
    assert record["seed"] == "seed"
    assert record["seed_files"] == 2
    assert record["seed_commit"] is None  # git was not declared


def test_record_reports_head_when_git(tmp_path):
    case_dir = _case_dir(tmp_path)
    _seed_tree(case_dir, {"a.txt": "alpha", "pkg/b.py": "print('b')\n"})
    flow_dir = tmp_path / "flow"

    record = seed_workspace(Workspace(seed="seed", git=True), case_dir, flow_dir)

    assert record["seed_commit"] == _git(flow_dir, "rev-parse", "HEAD")
    assert sorted(_git(flow_dir, "show", "--name-only", "--pretty=").splitlines()) == [
        "a.txt",
        "pkg/b.py",
    ]


def test_seed_commit_dates_are_pinned(tmp_path):
    # The test that fails when the dates are not pinned. Stability alone cannot
    # prove it: two seedings in one test land in the same integer second, so an
    # unpinned commit reproduces its SHA anyway.
    case_dir = _case_dir(tmp_path)
    flow_dir = tmp_path / "flow"

    seed_workspace(Workspace(git=True), case_dir, flow_dir)

    assert _git(flow_dir, "log", "-1", "--format=%aI") == SEED_COMMIT_DATE
    assert _git(flow_dir, "log", "-1", "--format=%cI") == SEED_COMMIT_DATE


def test_seed_commit_sha_is_the_anchored_value(tmp_path):
    case_dir = _case_dir(tmp_path)

    record = seed_workspace(Workspace(git=True), case_dir, tmp_path / "flow")

    assert record["seed_commit"] == EMPTY_SEED_SHA


def test_seed_commit_is_stable_across_flow_dirs(tmp_path):
    case_dir = _case_dir(tmp_path)
    _seed_tree(case_dir, {"a.txt": "alpha"})
    ws = Workspace(seed="seed", git=True)

    first = seed_workspace(ws, case_dir, tmp_path / "one")
    second = seed_workspace(ws, case_dir, tmp_path / "two")

    assert first["seed_commit"] == second["seed_commit"]


@pytest.mark.parametrize(
    "seed, why",
    [("nope", "does not exist"), ("a_file.txt", "is not a directory"), ("../escape", "escapes")],
)
def test_bad_seed_raises(tmp_path, seed, why):
    case_dir = _case_dir(tmp_path)
    (case_dir / "a_file.txt").write_text("not a tree")
    (tmp_path / "escape").mkdir()

    with pytest.raises(ValueError) as e:
        seed_workspace(Workspace(seed=seed), case_dir, tmp_path / "flow")

    assert str(case_dir) in str(e.value)
    assert repr(seed) in str(e.value)
    assert why in str(e.value)


def test_seeding_ignores_inherited_git_env(tmp_path, monkeypatch):
    # bug-49: a calling process that is itself a git hook exports GIT_DIR/
    # GIT_WORK_TREE/GIT_INDEX_FILE pointing at the outer repo; without scrubbing
    # them, the nested `git -C <flow_dir> commit` gets redirected onto it.
    # GIT_INDEX_FILE in particular discriminates a full GIT_*-prefix scrub from
    # one that only special-cases GIT_DIR/GIT_WORK_TREE.
    outer = tmp_path / "outer"
    outer.mkdir()
    env = _no_git_env()
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "outer@example.com"], cwd=outer, check=True, env=env
    )
    subprocess.run(["git", "config", "user.name", "outer"], cwd=outer, check=True, env=env)
    (outer / "seed.txt").write_text("seed")
    subprocess.run(["git", "add", "-A"], cwd=outer, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "outer initial commit"], cwd=outer, check=True, env=env
    )
    outer_index = outer / ".git" / "index"
    outer_index_before = outer_index.read_bytes()

    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(outer))
    monkeypatch.setenv("GIT_INDEX_FILE", str(outer_index))

    nested = tmp_path / "nested"
    seed_workspace(Workspace(git=True), _case_dir(tmp_path), nested)

    assert (nested / ".git").is_dir()
    assert _git(nested, "rev-list", "--count", "HEAD") == "1"
    assert _git(outer, "rev-list", "--count", "HEAD") == "1"
    # A scrub that only special-cases GIT_DIR/GIT_WORK_TREE still leaks
    # GIT_INDEX_FILE: nested's add/commit then stage into the OUTER index while
    # writing blobs into nested's object store — outer's commit count stays 1,
    # but its index now references blobs outer cannot resolve.
    assert outer_index.read_bytes() == outer_index_before


def test_existing_repo_is_not_recommitted(tmp_path):
    case_dir = _case_dir(tmp_path)
    flow_dir = tmp_path / "flow"
    first = seed_workspace(Workspace(git=True), case_dir, flow_dir)

    second = seed_workspace(Workspace(git=True), case_dir, flow_dir)

    assert _git(flow_dir, "rev-list", "--count", "HEAD") == "1"
    assert second["seed_commit"] == first["seed_commit"]
