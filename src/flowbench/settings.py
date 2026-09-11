# src/flowbench/settings.py
"""Engine settings, layered: init kwarg > FLOWBENCH_* env > .env > [tool.flowbench] > default."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
)


def default_runs_root() -> Path:
    """Beside the checkout that launches the run: `<checkout>/../flowbench-runs`.

    The checkout is the nearest ancestor of the cwd holding a `.git` entry — a directory
    in a normal checkout, a file in a worktree — so a loop worktree
    (`../flowbench--issue-N`) and the checkout it branched from share one run root, and
    `git worktree remove` cannot take a run dir with it (#166). Anchoring on the cwd
    instead would put the run dir back inside the checkout whenever the cwd is one level
    in. With no checkout above the cwd (an installed wheel) the cwd is the anchor.
    """
    cwd = Path.cwd()
    checkout = next((p for p in (cwd, *cwd.parents) if (p / ".git").exists()), cwd)
    return checkout.parent / "flowbench-runs"


class Settings(BaseSettings):
    runs_root: Path = Field(default_factory=default_runs_root)
    sim_model: str = "opus"
    judge_model: str = "opus"

    model_config = SettingsConfigDict(
        env_prefix="FLOWBENCH_",
        env_file=".env",
        extra="ignore",
        pyproject_toml_table_header=("tool", "flowbench"),
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Highest precedence first."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PyprojectTomlConfigSettingsSource(settings_cls),
        )
