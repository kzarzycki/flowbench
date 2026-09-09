"""Generic DONE-token turn loop: drive an AgentDriver to completion, with a
simulator model supplying the user side each idle turn. The SUT going idle = the
ball is in the user's court; the simulator LLM either replies as the user or emits
the DONE token. Wall-clock deadline + max-turns are backstops."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from flowbench.runner.driver import AgentDriver


def render_tail(convo: list[tuple[str, str]], *, n: int = 8) -> str:
    """Render the last `n` exchanges so the simulator sees CONTEXT, not just the
    agent's latest line. Without this the simulator loses the thread and
    re-introduces the task or emits chatty filler."""
    return "\n".join(f"[{role}] {text}" for role, text in convo[-n:])


def prime_prompt(simulator_system: str, convo: list[tuple[str, str]]) -> str:
    """The simulator's FIRST prompt: persona + conversation so far. Sent once —
    the simulator is a stateful session, so later turns relay only the delta
    (relay_prompt). Re-sending system+tail every turn cost quadratic tokens."""
    return (
        f"{simulator_system}\n\n--- CONVERSATION SO FAR (you are [user]) ---\n"
        f"{render_tail(convo)}\n\n--- YOUR REPLY (as the user) ---"
    )


def relay_prompt(convo: list[tuple[str, str]], since: int) -> str:
    """Every later prompt: just what happened since the simulator's last reply,
    labelled like the prime. Usually a single [assistant] message."""
    delta = "\n".join(f"[{role}] {text}" for role, text in convo[since:])
    return delta or "(the agent went idle without saying anything — reply as the user)"


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
    artifact_grace_s: float = 60.0,
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
        sim_seen = 0  # convo index up to which the simulator has been relayed
        while turns < max_turns and (time.monotonic() - start) < deadline_s:
            # Only an `idle` turn is a clean boundary where the agent awaits the
            # user. `failed`/`timeout`/`running` (per-turn cap hit) -> stop and
            # score whatever was built, rather than inject into a non-ready agent.
            if result.status != "idle":
                break
            # Stateful simulator: prime once with persona+context, then relay
            # only the delta — a normal dialog, not a re-sent transcript. (The
            # driver already waits out the agent's own busy sub-agents, so every
            # idle turn here is a real hand-over to the user.)
            prompt = (
                prime_prompt(simulator_system, convo)
                if sim_seen == 0
                else relay_prompt(convo, sim_seen)
            )
            out = await user_model.generate(prompt)
            reply = (out.completion or "").strip()
            if _is_done(reply, done_token):
                # DONE claimed with no artifact on disk: the agent may have
                # announced completion while its Write was still flushing
                # (seen live: plan.md landed a minute after capture). Grace-
                # poll before capturing.
                grace = time.monotonic() + artifact_grace_s
                while driver.artifact_path() is None and time.monotonic() < grace:
                    await asyncio.sleep(2.0)
                break
            result = await driver.send(reply)
            convo.append(("user", reply))
            sim_seen = len(convo)  # the sim knows everything incl. its own reply
            if result.assistant_text:
                convo.append(("assistant", result.assistant_text))
            turns += 1
        session = await driver.capture_session()
        # Why the loop stopped — a timeout here is otherwise invisible in the
        # captured session (live-001 shipped an unfinished plan silently).
        session["exit_status"] = result.status
        session["turns"] = turns
        if result.status == "stalled":
            session["stall_reason"] = result.stall_reason
            session["pane_tail"] = result.pane_tail
        return session
    finally:
        await driver.close()
