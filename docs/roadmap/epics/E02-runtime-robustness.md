# E02 — Runtime robustness: typed turn contract, driver split, one retry policy

Milestone M2. Depends on E01 (the modules it refactors must already live in the engine).

## Goal

The driver stops being a 600-line god-module with policy scattered across two repos.
After this epic: turn statuses are typed, the send/retry policy exists exactly once and
is documented as a table, bundle building and transcript utilities are separate modules,
and every omnigent private-API reach-in is either replaced by a public client call or
tracked by an upstream PR.

## Context

`runner/driver.py` today mixes five concerns: the `AgentDriver` ABC, transcript utilities,
bundle building (config render + tar), the omnigent session lifecycle, and the
send/settle/retry heuristics. Statuses are magic strings (`"idle"`, `"failed"`,
`"timeout"`). The driver also reaches into `omnigent_client` privates
(`sessions._http`, `sessions._base`, hand-built `SessionsChat`), which is why the dep is
pinned `==0.1.1`.

## Stories

### S02.1 `flowbench/types.py`

- `TurnStatus` str-enum (`IDLE`, `FAILED`, `TIMEOUT`), typed `TurnResult`, a
  `UserModel` Protocol (`async generate(prompt) -> obj` with `.completion`).
- Mechanical replacement across engine + tests; `status == "idle"` comparisons keep
  working during the transition (str-enum), then string literals are swept.
- Verify: `rg '"idle"|"failed"|"timeout"' src/` matches only inside `types.py`; V1, V2
  (see `../verification.md`).

### S02.2 Driver split

- `driver/bundle.py`: `render_config` (the AGENT_CONFIG template + skills/prompt
  emission) and `build_bundle` (tar of config + skill_dirs + mcp_files) as pure
  functions of a `Flow`-like spec. The existing `test_driver_bundle.py` /
  `test_driver_config.py` move with them.
- `transcript.py` (created in E01) absorbs anything transcript-shaped still in the
  driver.
- `OmnigentDriver` keeps: lifecycle (`start`/`close`), send/settle, capture, URLs.
- `runner/loop.py` relocates to `flowbench/loop.py` (the target-architecture position)
  with a `flowbench.runner.loop` compat re-export, same one-release policy as the
  driver's.
- Behavior-preserving; no policy change in this story.
- Verify: V1, V2, V4 (`verification.md` makes a live run mandatory for any change to
  `driver.py`/`loop.py`, and this story moves both); no scenario imports break
  (grep both repos for `flowbench.runner.driver` and add a compat re-export for one
  release of the loop). **Landed at `driver/omnigent.py` = 484 lines, not the ~350
  written here.** That figure predates #68 (paged `_list_items`, live `/child_sessions`)
  and #76 (wake-up wait), which added ~90 lines to the settle machinery this story is
  told to keep ("`OmnigentDriver` keeps: lifecycle, send/settle, capture, URLs").
  Reaching 350 means splitting that machinery — which S02.3 rewrites anyway, under one
  wall-clock budget. Splitting the repo's most incident-prone code twice, once
  mechanically and once for real, is the churn the epic's own Risks section warns
  against; the remainder goes with S02.3.

### S02.3b Loop hygiene — DONE (flowbench #67, ahead of E02)

Both audited bugs were removed rather than patched: the loop no longer nudges at all (the
driver reports `idle` only once no child session is busy, reading `/child_sessions` live
and paged, with a frozen child a `no_progress` stall), and `_list_items` pages past the
server's 200-item cap. Unit tests in `tests/runner/test_driver.py` / `test_loop.py` (V1);
live check todo-app-005.

### S02.4 Artifact concern out of the driver

- `artifact_name` leaves `OmnigentDriver`; `run_agent_session` takes an
  `artifact_probe: Callable[[], Path | None]` (the DONE grace-poll and
  `TurnResult.artifact_exists` are the only consumers). `run.py`'s factories build the
  probe from the flow dir; simulator/judge sessions pass no probe instead of
  `artifact_name="__none__"`.
- Verify: `rg __none__` → empty in both repos; loop tests updated; V1, V2.

### S02.5 Omnigent public-API migration

- Inventory every `_`-prefixed attribute access into `omnigent_client` /
  `omnigent.host` (`sessions._http`, `sessions._base`, `SessionsChat(...)` construction,
  `daemon_launch` internals). For each: use a public equivalent if one exists; otherwise
  open an upstream omnigent issue/PR adding one, and leave a `# UPSTREAM:` comment with
  the link. Known trap (audit-verified): the session-create reach-in exists because the
  public `sessions.create()` cannot express `terminal_launch_args` — do NOT "simplify"
  to the public call until upstream carries a metadata parameter, or the
  AskUserQuestion-deadlock protection silently disappears.
- Verify: `rg '\._[a-z]' src/flowbench/driver/` shows only self-attributes; pins bumped
  intentionally; V1, V4.

### S02.6 Error taxonomy

- The broad `except Exception` sites (`close`, `_context_tokens`,
  `_resend_allowed`, `transcript.to_jsonable`) become narrow catches with a debug log line;
  where swallowing is correct (teardown, best-effort labels), a comment says *why*
  swallowing is correct, not just that it happens.
- Verify: `ruff` BLE-style audit clean or explicitly waived per site; V1.

## Non-goals

- Event-driven turn boundaries (needs omnigent server support — tracked in the upstream
  wishlist, not buildable from this side).
- Any change to loop semantics (nudges, DONE detection) beyond parameter plumbing.

## Risks

- S02.3 touches the most incident-prone code in the repo. Mitigate: land S02.1/S02.2
  first (pure moves), then S02.3 alone with mandatory live validation; keep the old
  downstream behavior available behind the scenario until the live run passes.
- Public-API migration depends on upstream review latency; stories are ordered so
  everything else lands regardless.
