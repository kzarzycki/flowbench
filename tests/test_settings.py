"""Settings precedence: init kwarg > FLOWBENCH_* env > .env > [tool.flowbench] > default."""

from pathlib import Path

import pytest

from flowbench.settings import Settings

# (field, env var, cast) — every precedence test runs over all three, so a rung
# wired for one field cannot pass for the others.
FIELDS = [
    ("runs_root", "FLOWBENCH_RUNS_ROOT", Path),
    ("sim_model", "FLOWBENCH_SIM_MODEL", str),
    ("judge_model", "FLOWBENCH_JUDGE_MODEL", str),
]


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Both file sources read the cwd; the real environment must not leak in."""
    for _, env_var, _cast in FIELDS:
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_dotenv(d: Path, **values: str) -> None:
    (d / ".env").write_text("".join(f"FLOWBENCH_{k.upper()}={v}\n" for k, v in values.items()))


def _write_pyproject(d: Path, table: str = "tool.flowbench", **values: str) -> None:
    body = "".join(f'{k} = "{v}"\n' for k, v in values.items())
    (d / "pyproject.toml").write_text(f"[{table}]\n{body}")


def test_defaults():
    s = Settings()
    assert s.runs_root.is_absolute()
    assert s.sim_model == "opus"
    assert s.judge_model == "opus"


def _checkout(d: Path, name: str, *, worktree: bool = False) -> Path:
    """A checkout shape: `.git` is a directory in a clone, a file in a worktree."""
    repo = d / name
    repo.mkdir()
    if worktree:
        (repo / ".git").write_text(f"gitdir: {d / 'clone' / '.git' / 'worktrees' / name}\n")
    else:
        (repo / ".git").mkdir()
    return repo


def test_the_default_runs_root_sits_beside_a_normal_checkout(_isolated_cwd, monkeypatch):
    monkeypatch.chdir(_checkout(_isolated_cwd, "clone"))
    assert Settings().runs_root == _isolated_cwd / "flowbench-runs"


def test_the_default_runs_root_of_a_worktree_is_the_checkouts(_isolated_cwd, monkeypatch):
    """A loop worktree is a sibling of its checkout, so both land in one run root —
    which is why `git worktree remove` cannot take the live-gate evidence (#166)."""
    monkeypatch.chdir(_checkout(_isolated_cwd, "clone"))
    from_clone = Settings().runs_root
    monkeypatch.chdir(_checkout(_isolated_cwd, "clone--issue-1", worktree=True))
    assert Settings().runs_root == from_clone == _isolated_cwd / "flowbench-runs"


def test_the_default_is_the_checkouts_not_the_cwds(_isolated_cwd, monkeypatch):
    repo = _checkout(_isolated_cwd, "clone")
    deep = repo / "scenarios" / "smoke"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    runs_root = Settings().runs_root
    assert runs_root == _isolated_cwd / "flowbench-runs"
    assert repo not in runs_root.parents  # never inside the checkout


def test_the_default_falls_back_to_the_cwd_with_no_checkout(_isolated_cwd, monkeypatch):
    loose = _isolated_cwd / "loose"
    loose.mkdir()
    monkeypatch.chdir(loose)
    assert Settings().runs_root == _isolated_cwd / "flowbench-runs"


def test_the_ignore_file_does_not_hide_runs_in_the_checkout():
    """Nothing writes to `<checkout>/runs/` any more, so nothing ignores it (#166)."""
    ignore = Path(__file__).parents[1] / ".gitignore"  # the fixture has chdir'd away
    assert "/runs/" not in ignore.read_text().split()


@pytest.mark.parametrize(("field", "env_var", "cast"), FIELDS)
def test_pyproject_beats_default(_isolated_cwd, field, env_var, cast):
    _write_pyproject(_isolated_cwd, **{field: "from-pyproject"})
    assert getattr(Settings(), field) == cast("from-pyproject")


@pytest.mark.parametrize(("field", "env_var", "cast"), FIELDS)
def test_dotenv_beats_pyproject(_isolated_cwd, field, env_var, cast):
    _write_pyproject(_isolated_cwd, **{field: "from-pyproject"})
    _write_dotenv(_isolated_cwd, **{field: "from-dotenv"})
    assert getattr(Settings(), field) == cast("from-dotenv")


@pytest.mark.parametrize(("field", "env_var", "cast"), FIELDS)
def test_env_beats_dotenv(_isolated_cwd, monkeypatch, field, env_var, cast):
    _write_dotenv(_isolated_cwd, **{field: "from-dotenv"})
    monkeypatch.setenv(env_var, "from-env")
    assert getattr(Settings(), field) == cast("from-env")


@pytest.mark.parametrize(("field", "env_var", "cast"), FIELDS)
def test_init_kwargs_beat_env(monkeypatch, field, env_var, cast):
    monkeypatch.setenv(env_var, "from-env")
    assert getattr(Settings(**{field: "from-init"}), field) == cast("from-init")


def test_other_tool_tables_are_ignored(_isolated_cwd):
    _write_pyproject(_isolated_cwd, table="tool.somethingelse", sim_model="not-ours")
    assert Settings().sim_model == "opus"


def test_unknown_dotenv_keys_are_ignored(_isolated_cwd):
    # the scenarios repo's .env carries Teradata keys; they must not raise.
    (_isolated_cwd / ".env").write_text(
        "TD_HOST=host.example\nTD_PASSWORD=not-a-real-password\nFLOWBENCH_SIM_MODEL=sonnet\n"
    )
    assert Settings().sim_model == "sonnet"


def test_compare_is_still_a_subcommand():
    """Dropping python-dotenv must not drop a command or an option.

    Asserted against the registered click command rather than `--help` output:
    the rendered help wraps and truncates to the terminal, so a string search
    there passes or fails on the width of whoever runs it (it failed on CI and
    passed on every local width).
    """
    import typer.main

    from flowbench.cli import app

    compare = typer.main.get_command(app).commands["compare"]
    assert {p.name for p in compare.params} >= {"run_base", "run_id"}
