"""Settings precedence: init kwarg > FLOWBENCH_* env > .env > [tool.flowbench] > default."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

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
    assert s.runs_root == Path("runs")
    assert s.sim_model == "opus"
    assert s.judge_model == "opus"


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
    from flowbench.cli import app

    result = CliRunner().invoke(app, ["compare", "--help"])
    assert result.exit_code == 0, result.output
    assert "--run-base" in result.output
