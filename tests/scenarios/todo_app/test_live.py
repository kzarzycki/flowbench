"""Live end-to-end through run_case_n — gated on RUN_LIVE_AGENT=1.
Subscription only (no ANTHROPIC_API_KEY). Long-running: a full workflow build."""

import os
from datetime import datetime

import pytest

pytestmark = pytest.mark.live_agent
RUN = os.environ.get("RUN_LIVE_AGENT") == "1"


@pytest.mark.skipif(not RUN, reason="set RUN_LIVE_AGENT=1 to run the live build")
async def test_todo_build_live():
    import sys

    from scenarios.coding_workflow.run import main

    assert not os.environ.get("ANTHROPIC_API_KEY"), "must run on subscription"
    run_id = f"live-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    sys.argv = ["run", "--run-id", run_id]
    main()

    from scenarios.coding_workflow.run import default_runs_root

    run_root = default_runs_root() / run_id
    for flow in ("baseline", "superpowers"):
        assert (run_root / flow / "scorecard.json").is_file()
