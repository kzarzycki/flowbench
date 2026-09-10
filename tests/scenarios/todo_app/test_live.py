"""Live end-to-end through `flowbench run` — gated on RUN_LIVE_AGENT=1.
Subscription only (no ANTHROPIC_API_KEY). Long-running: a full workflow build."""

import os
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowbench.cli import app
from flowbench.settings import Settings

pytestmark = pytest.mark.live_agent
RUN = os.environ.get("RUN_LIVE_AGENT") == "1"

CASE_DIR = Path(__file__).parents[3] / "scenarios" / "swe_e2e" / "cases" / "todo_app"


@pytest.mark.skipif(not RUN, reason="set RUN_LIVE_AGENT=1 to run the live build")
def test_todo_build_live():
    assert not os.environ.get("ANTHROPIC_API_KEY"), "must run on subscription"
    run_id = f"live-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    result = CliRunner().invoke(
        app, ["run", str(CASE_DIR), "--run-id", run_id], catch_exceptions=False
    )

    assert result.exit_code == 0, result.output
    # <runs_root>/<case.name>/<run_id>, the engine's layout
    run_root = Settings().runs_root / "todo_app" / run_id
    for flow in ("baseline", "superpowers"):
        assert (run_root / flow / "scorecard.json").is_file()
