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
`"timeout"`). Retry policy is split: the driver retries *undelivered* injections
(label-confirmed), while downstream `SessionModel.generate` (issue #39) separately retries
*failed-with-stale-text* turns because simulator/judge sessions don't reliably set the
delivery labels. The driver also reaches into `omnigent_client` privates
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
- Behavior-preserving; no policy change in this story.
- Verify: V1, V2; `driver/omnigent.py` under ~350 lines; no scenario imports break
  (grep both repos for `flowbench.runner.driver` and add a compat re-export for one
  release of the loop).

### S02.3 One retry policy, at the driver

- Move the fresh-text rule into `send`: a turn that ends `FAILED` but produced a NEW
  assistant message (vs. the pre-send count, which `_send_once` already tracks) is a
  delivered-then-flaked turn — return it as success-with-flag rather than making every
  caller re-derive it.
- Resulting policy table (goes verbatim into `docs/design/runner.md`):

  | Observation | Meaning | Action |
  | --- | --- | --- |
  | `FAILED` + label says undelivered | injection never landed | wait, re-send same text (bounded) |
  | `FAILED` + new assistant text | turn completed, then flaked | trust the text, no retry |
  | `FAILED`, no label, no new text | unknown; likely undelivered | bounded re-send (the #39 behavior, generalized) |
  | `TIMEOUT` | may be mid-turn after delivery | NEVER retry (injecting into a busy terminal kills sessions) |
  | `IDLE` + no new text past settle budget | lying idle | report `TIMEOUT` |

- `SessionModel.generate` shrinks to: send, raise on `TIMEOUT`/no-text, wrap completion.
  Its downstream tests move/port with it.
- **One wall-clock budget per send** (audited bug): today `_send_once` stacks a full
  `turn_timeout_s` in `_wait_idle` plus a second `turn_timeout_s` settle window whose
  iterations call `_wait_idle` again — a single turn can eat ~8–9 min of a 30-min run.
  The send gets one ceiling that all inner waits and retry sleeps draw down.
- Verify: the S00.3 regression tests plus new ones covering each table row (V1); V4 is
  MANDATORY here — this is the code path that killed runs #30/#34/#39.

### S02.3b Loop hygiene (audited bugs, small PR)

- Harness `Continue.` nudges are appended to `convo` and later relayed to the simulator
  as `[user]` messages it never authored — a stateful dialog agent gets words put in its
  mouth. Nudges stay out of the simulator's relay window (they remain in the captured
  transcript, flagged as harness turns).
- `any_child_busy` folds the cumulative event stream: one child whose settling
  `busy=False` is never captured poisons `child_busy` for every subsequent turn. Track
  per-turn (or timestamp-bounded) child state instead; the `_MAX_CONSEC_NUDGES` cap stays
  as the backstop.
- Verify: loop unit tests for both (V1); V4 alongside S02.3's.

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
- Upstream the `_PROMPT_SCAN_TAIL_LINES` fix; when a release carries it, delete
  `scripts/patch_omnigent.py` and its README mention, and bump the pin. Until then, fix
  the patch script's search path: it only patches the uv-tool install, while the `live`
  extra installs omnigent as a venv dependency — the copy the driver actually imports.
- Verify: `rg '\._[a-z]' src/flowbench/driver/` shows only self-attributes; pins bumped
  intentionally; V1, V4.

### S02.6 Error taxonomy

- The broad `except Exception` sites (`close`, `_context_tokens`,
  `_injection_undelivered`, `_to_jsonable`) become narrow catches with a debug log line;
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
