"""Generic DONE-token turn loop: drive an AgentDriver to completion, with a
simulator model supplying the user side each idle turn. The SUT going idle = the
ball is in the user's court; the simulator LLM either replies as the user or emits
the DONE token. Wall-clock deadline + max-turns are backstops."""

from __future__ import annotations

import time
from typing import Any

from flowbench.runner.driver import AgentDriver


def render_tail(convo: list[tuple[str, str]], *, n: int = 8) -> str:
    """Render the last `n` exchanges so the simulator sees CONTEXT, not just the
    agent's latest line. Without this the simulator loses the thread and
    re-introduces the task or emits chatty filler."""
    return "\n".join(f"[{role}] {text}" for role, text in convo[-n:])


async def next_user_message(convo_tail: str, simulator_system: str, user_model) -> str:
    prompt = (
        f"{simulator_system}\n\n--- RECENT CONVERSATION (you are [user]) ---\n"
        f"{convo_tail}\n\n--- YOUR REPLY (as the user) ---"
    )
    out = await user_model.generate(prompt)
    return (out.completion or "").strip()


_NUDGE = "Continue."

# Safety bound on consecutive free nudges. A child sub-agent that never emits its
# settling `busy=False` (capture races the session end) would otherwise look busy
# forever, so the loop would canned-nudge indefinitely and the simulator could never
# emit DONE. After this many self-wait nudges in a row, force a simulator turn so
# completion is still detected — worst case we "waste" this many polls, not the run.
_MAX_CONSEC_NUDGES = 3


def _is_self_wait(result) -> bool:
    """The agent is parked on its OWN background sub-agent: idle, a child sub-agent
    still busy, and it's not asking the user anything. Such a turn needs a nudge to
    un-park the agent, but NOT a simulated-user LLM call — the simulator would only
    say "Continue." anyway, and burning a turn polling the agent's own work is the
    wasteful loop we observed live."""
    return getattr(result, "child_busy", False) and "?" not in (result.assistant_text or "")


def _is_done(reply: str, done_token: str) -> bool:
    """Robust DONE detection: `claude -p` may wrap the token ("Looks good.
    `<<DONE>>`"). Accept the token anywhere in a short reply, not just == ."""
    r = reply.strip()
    return r == done_token or (done_token in r and len(r) <= len(done_token) + 60)


async def run_agent_session(
    driver: AgentDriver,
    user_model,
    *,
    first_prompt: str,
    simulator_system: str,
    done_token: str,
    max_turns: int = 80,
    deadline_s: float = 1800.0,
) -> dict[str, Any]:
    start = time.monotonic()
    convo: list[tuple[str, str]] = []
    try:
        await driver.start()
        result = await driver.send(first_prompt)
        convo.append(("user", first_prompt))
        if result.assistant_text:
            convo.append(("assistant", result.assistant_text))
        turns = 0
        consec_nudges = 0
        while turns < max_turns and (time.monotonic() - start) < deadline_s:
            # Only an `idle` turn is a clean boundary where the agent awaits the
            # user. `failed`/`timeout`/`running` (per-turn cap hit) -> stop and
            # score whatever was built, rather than inject into a non-ready agent.
            if result.status != "idle":
                break
            if _is_self_wait(result) and consec_nudges < _MAX_CONSEC_NUDGES:
                # Free nudge — don't spend a simulator turn polling the agent's own
                # background work. DONE is never missed: the app is delivered only
                # once no child sub-agent is busy (routes to the simulator), and the
                # consec cap forces a simulator turn even if a child looks stuck busy.
                reply = _NUDGE
                consec_nudges += 1
            else:
                reply = await next_user_message(render_tail(convo), simulator_system, user_model)
                consec_nudges = 0
                if _is_done(reply, done_token):
                    break
            result = await driver.send(reply)
            convo.append(("user", reply))
            if result.assistant_text:
                convo.append(("assistant", result.assistant_text))
            turns += 1
        return await driver.capture_session()
    finally:
        await driver.close()
