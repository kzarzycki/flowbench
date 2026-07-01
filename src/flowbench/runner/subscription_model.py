"""An Inspect model backed by the local `claude -p` CLI on the user's
subscription — no ANTHROPIC_API_KEY, no API billing.

This lets the simulator (`user` role) and the judge (`grader` role) run on the
same subscription as the agent-under-test, so the whole eval honors the
"subscription only" requirement end to end. The agent itself is driven through
omnigent; this is only for the two evaluation-infra model roles.

It is a thin ModelAPI: flatten the chat messages to a prompt, shell out to
`claude -p --model <m>`, return the stdout as the completion. Single-shot,
no tools — exactly what a simulator/judge turn needs.
"""

from __future__ import annotations

import asyncio
import os

from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    Model,
    ModelAPI,
    ModelOutput,
    get_model,
    modelapi,
)

PROVIDER = "claudesub"


def _flatten(messages: list) -> str:
    """Render chat messages as a single prompt for `claude -p`."""
    parts: list[str] = []
    for msg in messages:
        text = msg.text if hasattr(msg, "text") else str(msg)
        if isinstance(msg, ChatMessageSystem):
            parts.append(f"[system]\n{text}")
        elif isinstance(msg, ChatMessageUser):
            parts.append(text)
        elif isinstance(msg, ChatMessageAssistant):
            parts.append(f"[assistant]\n{text}")
        elif isinstance(msg, ChatMessageTool):
            parts.append(f"[tool]\n{text}")
        else:
            parts.append(text)
    return "\n\n".join(p for p in parts if p)


class ClaudeSubscriptionAPI(ModelAPI):
    """ModelAPI that runs the logged-in `claude` CLI in print mode."""

    def __init__(self, model_name: str = "sonnet", **kwargs):
        super().__init__(model_name=model_name)
        self._timeout_s = 120.0

    async def generate(self, input, tools, tool_choice, config) -> ModelOutput:
        prompt = _flatten(input)
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "--model",
            self.model_name,
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_s)
        except TimeoutError:
            proc.kill()
            return ModelOutput.from_content(
                self.model_name, "", stop_reason="unknown", error="claude -p timed out"
            )
        if proc.returncode != 0:
            return ModelOutput.from_content(
                self.model_name,
                "",
                stop_reason="unknown",
                error=f"claude -p exit {proc.returncode}: {err.decode()[:200]}",
            )
        return ModelOutput.from_content(self.model_name, out.decode().strip())


@modelapi(name=PROVIDER)
def _claudesub_provider():
    """Registry loader so `get_model("claudesub/<name>")` and the CLI flag
    `--model-role user=claudesub/sonnet` both resolve to this ModelAPI."""
    return ClaudeSubscriptionAPI


def claude_subscription_model(model_name: str = "sonnet") -> Model:
    """An Inspect Model on the subscription CLI, usable as a role instance."""
    return get_model(f"{PROVIDER}/{model_name}")
