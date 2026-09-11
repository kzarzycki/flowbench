"""Generic DONE-token turn loop: drive an AgentDriver to completion, with a
simulator model supplying the user side each idle turn. The SUT going idle = the
ball is in the user's court; the simulator LLM either replies as the user or emits
the DONE token. Wall-clock deadline + max-turns are backstops."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flowbench.driver import AgentDriver
from flowbench.types import TurnStatus, UserModel

# The engine owns the done token, not the case: a persona that names its own can
# only contradict the loop's detector, and every case wants the same signal.
# `simulator.md` says what "delivered" means; END_INSTRUCTION says how to say so.
DONE_TOKEN = "<<DONE>>"
END_INSTRUCTION = (
    f"ENDING THE SESSION: reply with EXACTLY `{DONE_TOKEN}` and nothing else "
    "when — and only when — the agent has delivered what you asked for and is "
    "asking you nothing further. While it is still working, still asking "
    "questions, or has delivered something that does not match what you wanted, "
    "never write that token: reply as the user instead."
)


def render_tail(convo: list[tuple[str, str]], *, n: int = 8) -> str:
    """Render the last `n` exchanges so the simulator sees CONTEXT, not just the
    agent's latest line. Without this the simulator loses the thread and
    re-introduces the task or emits chatty filler."""
    return "\n".join(f"[{role}] {text}" for role, text in convo[-n:])


def prime_prompt(simulator_system: str, convo: list[tuple[str, str]]) -> str:
    """The simulator's FIRST prompt: persona + how to end + conversation so far.
    Sent once — the simulator is a stateful session, so later turns relay only
    the delta (relay_prompt). Re-sending system+tail every turn cost quadratic
    tokens. The end instruction follows the persona: role first, then exit."""
    return (
        f"{simulator_system}\n\n{END_INSTRUCTION}\n\n"
        f"--- CONVERSATION SO FAR (you are [user]) ---\n"
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
    user_model: UserModel,
    *,
    first_prompt: str,
    simulator_system: str,
    max_turns: int = 80,
    deadline_s: float = 1800.0,
    artifact_grace_s: float = 60.0,
    artifact_probe: Callable[[], Path | None] | None = None,
) -> dict[str, Any]:
    """`artifact_probe`, when given, is the orchestrator's answer to "which file
    proves this session delivered" — the driver knows nothing about it. On DONE
    the loop polls it until it returns a path (grace-bounded), and after capture
    it sets `artifact_exists`/`artifact_path`/`artifact_text` on the session for
    every run (False/None/None when no probe is given). The session also carries
    `ended_by` — `done`, `max_turns`, `deadline`, or the agent's terminal turn
    status."""
    start = time.monotonic()
    convo: list[tuple[str, str]] = []
    flaked = 0
    done = False
    try:
        await driver.start()
        result = await driver.send(first_prompt)
        flaked += result.flaked
        convo.append(("user", first_prompt))
        if result.assistant_text:
            convo.append(("assistant", result.assistant_text))
        turns = 0
        sim_seen = 0  # convo index up to which the simulator has been relayed
        while turns < max_turns and (time.monotonic() - start) < deadline_s:
            # Only an `idle` turn is a clean boundary where the agent awaits the
            # user. `failed` here means no reply after the driver's bounded
            # re-sends; `timeout`/`running` (per-turn cap hit) -> stop and score
            # whatever was built, rather than inject into a non-ready agent;
            # `quota` (#131): the CLI hit its limit — the banner is not relayed to
            # the simulator, the session ends and `exit_status` says why.
            if result.status != TurnStatus.IDLE:
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
            if _is_done(reply, DONE_TOKEN):
                done = True
                # DONE claimed with no artifact on disk: the agent may have
                # announced completion while its Write was still flushing
                # (seen live: plan.md landed a minute after capture). Grace-
                # poll before capturing. No probe (case declares no artifact)
                # -> nothing to wait for.
                if artifact_probe is not None:
                    try:
                        async with asyncio.timeout(artifact_grace_s):
                            while await asyncio.to_thread(artifact_probe) is None:
                                await asyncio.sleep(2.0)
                    except TimeoutError:
                        pass  # grace spent (or a hung filesystem): capture what is there
                break
            result = await driver.send(reply)
            flaked += result.flaked
            convo.append(("user", reply))
            sim_seen = len(convo)  # the sim knows everything incl. its own reply
            if result.assistant_text:
                convo.append(("assistant", result.assistant_text))
            turns += 1
        session = await driver.capture_session()
        artifact = await asyncio.to_thread(artifact_probe) if artifact_probe else None
        session["artifact_exists"] = artifact is not None
        session["artifact_path"] = str(artifact) if artifact else None
        # A deliverable can be a directory (a ported project): presence is the
        # probe's answer, text only exists for a file. `.read_text()` on a
        # directory raised IsADirectoryError right after DONE.
        session["artifact_text"] = artifact.read_text() if artifact and artifact.is_file() else None
        # Why the loop stopped — a timeout here is otherwise invisible in the
        # captured session (live-001 shipped an unfinished plan silently).
        session["exit_status"] = result.status
        # `exit_status` is the agent's last turn; `ended_by` is what ended the
        # session. `idle` answered neither question: 50 of 69 recorded sessions
        # ended `idle` and the record could not say whether the simulator or the
        # cap stopped them. A non-idle terminal status is checked first — a
        # crashed session is not a completed one, whatever the simulator said.
        # Today that ordering cannot actually be exercised: the loop breaks on a
        # non-idle turn before consulting the simulator, so `done` implies the
        # last turn was `idle` and the two branches never compete. It is the
        # guard for a loop that one day re-sends after a done claim, not a
        # precedence the current control flow reaches. Being `TurnStatus | str`,
        # the status is compared with `!=` and stringified with `str()` so an
        # undocumented server status passes through verbatim.
        if result.status != TurnStatus.IDLE:
            session["ended_by"] = str(result.status)
        elif done:
            session["ended_by"] = "done"
        elif turns >= max_turns:
            session["ended_by"] = "max_turns"
        else:
            session["ended_by"] = "deadline"  # idle, uncapped, no token: the clock
        session["turns"] = turns
        session["flaked_turns"] = flaked
        if result.status == TurnStatus.STALLED:
            session["stall_reason"] = result.stall_reason
            session["pane_tail"] = result.pane_tail
        return session
    finally:
        await driver.close()
