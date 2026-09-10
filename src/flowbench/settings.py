# src/flowbench/settings.py
"""Engine settings, layered: init kwarg > FLOWBENCH_* env > .env > [tool.flowbench] > default."""

from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    runs_root: Path = Path("runs")
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
