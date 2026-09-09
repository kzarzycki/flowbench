# Decision: omnigent is the meta-harness; the driver seam is how we stay free of it

**Date:** 2026-09-09. **Status:** accepted. Fulfils the deferral in
[`2026-09-03-flow-is-the-full-configuration.md`](2026-09-03-flow-is-the-full-configuration.md)
("the meta-harness … is a separate decision to be recorded in M2").

## Decision

1. **omnigent is the meta-harness** — the one thing that launches a flow's coding agent, for
   every harness we benchmark. A flow declares `harness` (`claude-native`, `codex-native`, …);
   omnigent owns the launch.
2. **Exactly one module knows that** — `src/flowbench/runner/driver.py`, behind the
   `AgentDriver` ABC (`start / send / capture_session / artifact_path / close`). Everything
   upstream of that seam is omnigent-free at import time, and the offline suite runs against
   `flowbench.testing` doubles through the same seam.
3. **herdr is not adopted**, and neither is a per-harness CLI driver of our own. Both are
   re-evaluated against the triggers below; the seam in (2) is the swap point, so either can
   be added later as a second `AgentDriver` implementation without touching a scenario.

## Why

The benchmark's whole claim is that two columns of a comparison differ **only** in the fields
the flow declares. Four capabilities are what make that claim defensible, and omnigent is the
only thing to hand that has all four:

- **Per-flow bundle injection.** The driver builds an `agent.tar.gz` per flow — `config.yaml`
  (harness, permission mode, host-skill filter), `skills/<name>/SKILL.md`, `tools/mcp/*.yaml` —
  POSTs it with the session, and the agent loads those skills from the bundle
  (`--plugin-dir`), with the host's `~/.claude` skills hidden when the flow says
  `skills: none`. **That is the comparability mechanism**: a flow is identical on any machine,
  and a baseline is the same picture with an empty `skills/`. Without it, "add superpowers to
  this flow" means mutating the operator's own `~/.claude` — the one asymmetry the benchmark
  must not have.
- **A normalized transcript.** `GET /v1/sessions/{id}/items` returns typed message items for
  any harness, plus a streamed event log (including per-sub-agent `busy` state, which the loop
  reads to nudge a self-waiting agent instead of burning a simulated-user turn). Scoring,
  transcript rendering and the DONE-token loop all read that shape — not a scraped TUI.
- **Signals a benchmark needs, not just a chat.** Typed session `status`, an `updated_at`
  heartbeat, explicit "waiting on a human" fields (`pending_elicitations`, `pending_inputs`,
  `terminal_pending`), the runner's tmux socket/target for a pane capture, and a
  `last_context_tokens` label. The stall watchdog (#54/#61) exists because those are readable:
  a run that would otherwise sit on an unanswerable permission dialog until its cap ends the
  turn as `stalled` with the question captured. A win at twice the tokens is a different
  result, and the label is how we say so.
- **The product under test, unmodified.** The agent is a vanilla `claude` CLI in a tmux pane on
  subscription billing, reading the host config — not an SDK reimplementation of it. The
  session survives the run (`conversation_url`), so a human can resume the exact conversation
  the simulator drove.

## Alternatives considered

### herdr (terminal workspace manager for coding agents)

Probed 2026-09-09 against the installed binary: a socket API with a published JSON schema,
22 agent kinds, `agent start <name> --kind <kind> --pane <id> [-- <agent-args>]`,
`agent prompt <target> --wait --until <status>`, `agent read --source visible|recent|detection`,
and lifecycle states `idle|working|blocked|done|unknown`. Genuinely close on turn-taking —
`--until blocked` covers part of what our watchdog does, and it drives more harnesses than we
do. Rejected for this job on three counts:

1. **No per-flow bundle.** `agent start` passes CLI args to an existing pane; skills and MCPs
   would have to come from the host's own agent config. That is exactly the hidden asymmetry
   above, and it is the capability the benchmark is built on.
2. **Pane text, not a transcript.** Its API carries visible/recent pane text plus a *reference*
   to the harness's own session file (`AgentSessionInfo{source, agent, kind, value}`). We would
   own a per-harness transcript parser, and the comparison's inputs would depend on terminal
   width.
3. **A TUI-derived state machine, and it says so.** `unknown` "does not prove completion";
   `idle` vs `done` depends on whether a human has *seen* the tab in the focused UI. herdr's own
   operating guidance also tells a caller not to control a session from outside a herdr-managed
   pane (`HERDR_ENV=1`) — a policy, not an API gate: the socket answers `agent list` from a plain
   shell. omnigent's status plus the three pending-prompt fields are server state, and the
   watchdog needed server state to be trustworthy.

### Driving each CLI directly (`claude -p` / `--resume`, or an SDK)

Cheapest to start, and it drops a whole daemon+tmux operational surface. Rejected: it buys the
launch and nothing else. One adapter per harness to write and keep current (the flow field
`harness` is the point of the design), transcript shapes to normalize per vendor, no
bundle/plugin-dir injection short of writing config into the host, and no session state to base
a watchdog on. `claude -p` also is not the interactive product — the thing being benchmarked is
Claude Code as a developer runs it, and print mode is a different program with different
defaults.

## Costs accepted

- **Private-API reach-ins.** `sessions._http`, `sessions._base`, a hand-built `SessionsChat`,
  `omnigent.host.daemon_launch` internals — the session-create reach-in exists because the
  public `sessions.create()` cannot express `terminal_launch_args`, which is where the
  AskUserQuestion/permission flags ride. Tracked as E02 S02.5 (migrate or upstream; do not
  "simplify" to the public call before it carries metadata).
- **A version split.** The `live` extra pins an old published client while the server runs from
  a much newer source checkout. Documented in [`../../onboarding.md`](../../onboarding.md) §2;
  the pin bump is S02.5's.
- **An operational surface** — server, host daemon, runner, tmux, and a subscription's quota —
  which is why live validation is a named gate in the engineering loop rather than a unit test.
- **A single vendor of record.** Mitigated only by (2): the seam is the deliverable, not the
  vendor.

## Reconsider triggers

- omnigent cannot express a harness we need to benchmark (the flow-field promise breaks).
- herdr grows per-session bundle injection **and** a normalized transcript — then it is a
  second `AgentDriver`, and running both on one case is the honest way to measure the
  meta-harness's own contribution.
- Keeping up with omnigent's internals costs more than a direct driver would (the reach-in list
  in `roadmap/current-state.md` #5 stops shrinking after S02.5).
- We need runs on hardware we do not operate: the server/host/tmux model is local-first.

## Consequences

- Nothing outside `runner/driver.py` may import omnigent; a new capability arrives as a method
  on `AgentDriver`, not as an omnigent call at the call site.
- `TurnResult` and the captured-session dict are the vendor boundary — new omnigent signals
  become fields there (as `stall_reason` / `pane_tail` did) or they do not exist upstream.
- Adding a harness is a flow field plus, at most, a `launch_args` branch in
  `_create_metadata` — not a new driver.
- Live validation stays a gate: this decision puts real infrastructure in the measurement path.
