# Decision: completion is engine-owned; a case describes delivery, it does not name the token

**Date:** 2026-09-10. **Status:** accepted. Supersedes the per-case `done_token` parameter of
`run_case` and the token text that lived in each case's `simulator.md`.

## Decision

1. **One token, owned by the engine.** `flowbench.loop.DONE_TOKEN = "<<DONE>>"`. `Case` has no
   token field and `run_case` has no `done_token` parameter. `<<DONE>>` cannot occur in natural
   prose; the other token in play, `PLAN_COMPLETE`, described one case's shape and would have to
   be re-chosen per case for no gain.
2. **The instruction is appended to the simulator's prime prompt** — `prime_prompt`, the one place
   the persona is sent: reply with exactly the token and nothing else, once the agent has delivered
   what was asked and is asking nothing further; never while it is still working, still asking, or
   has delivered something else. Persona first, then exit.
3. **`simulator.md` describes only what "delivered" means** for its case, in its own words ("the
   plan is written and the agent says it is complete"). It never names the token, so a persona
   cannot contradict the loop's detector.
4. **`session.json` records `ended_by`**, with this precedence: a non-`idle` final turn status
   wins and is recorded verbatim (a crashed session is not a completed one, whatever the simulator
   said); else the token → `done`; else `turns >= max_turns` → `max_turns`; else `deadline`.
   `exit_status` stays what it was — the agent's last turn — and answers a different question.
5. **The detector is unchanged.** `_is_done` still accepts the token anywhere in a short reply,
   because `claude -p` wraps it ("Looks good. `<<DONE>>`").
6. **A stronger completion signal is deferred** — a file the simulator writes, or an MCP tool it
   calls — until `ended_by` shows the phrase misfiring in real runs. That is now a measurement,
   not a guess.

## Why

A token in the case was configuration that every case wanted the same value for, and a persona
that names its own token can only disagree with the loop.

The recorded exit was worse: **50 of 69 real sessions ended `idle`**, and the record could not say
whether the simulator had ended them or a budget had. `exit_status: "idle"` answers "what was the
agent doing" — it cannot answer "why did this stop", which is the question a scorecard reader
actually has. `ended_by` answers it, and it is also the evidence needed before spending anything
on a heavier completion protocol.

## What stays locked

- The simulator is the only thing that ends a session cleanly; the loop never nudges and never
  answers a prompt on the agent's behalf.
- `max_turns` and `deadline_s` remain backstops, and they are the case's (`Case`), not the CLI's.
- Cases stay text: what counts as delivered is prose in `simulator.md`, not code.

## Consequences

- `flowbench.testing.StubSim` emits `DONE_TOKEN`; nothing scenario-side may define one.
- The case `simulator.md` files lost their token paragraph — no case folder names a token.
- `ended_by` is a `session.json` key readers can rely on; `run.json`'s `flow_stats` keeps
  `exit_status` beside it.
