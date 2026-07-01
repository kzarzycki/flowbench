"""Live end-to-end through the Inspect spine — gated on RUN_LIVE_AGENT=1.
Subscription only (no ANTHROPIC_API_KEY). Long-running: a full workflow build."""

import os

import pytest

pytestmark = pytest.mark.live_agent
RUN = os.environ.get("RUN_LIVE_AGENT") == "1"


@pytest.mark.skipif(not RUN, reason="set RUN_LIVE_AGENT=1 to run the live build")
async def test_todo_build_live():
    from inspect_ai import eval_async

    from flowbench.runner.subscription_model import claude_subscription_model
    from scenarios.coding_workflow.cases.todo_app.eval import todo_app_eval

    assert not os.environ.get("ANTHROPIC_API_KEY"), "must run on subscription"
    sub = claude_subscription_model("sonnet")
    logs = await eval_async(
        todo_app_eval(),
        model=sub,
        model_roles={"user": sub, "grader": sub},
        log_dir="logs/todo-live",
    )
    log = logs[0]
    assert log.status == "success", f"status={log.status}"
    obj = log.samples[0].scores["workflow_scorer"].value
    assert obj["app_runs"] == 1  # the built app actually runs
    assert obj["acceptance"] >= 0.7  # most of the contract works
    assert obj["phases_complete"] >= 0.6  # genuinely ran the workflow
