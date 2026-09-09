# Omnigent private-API inventory (E02 S02.5, part 1)

What `src/flowbench/driver/omnigent.py` takes from omnigent that is not a public,
documented SDK call, and what to do about each. Written read-only against the driver at
`883e0d0`; part 2 of S02.5 applies the verdicts. Tracking issue: flowbench #105.

## Two truths, checked separately

| What | Version | Where |
|---|---|---|
| Client the driver imports (`omnigent_client`, `omnigent.host`) | `0.2.0` (pinned in `pyproject.toml`, `live` extra) | repo venv |
| Server that answers the requests | `0.13.0.dev0`, editable checkout `~/dev/ext/omnigent/omnigent` @ `8627eb9f` (fork of `omnigent-ai/omnigent`) | `~/.local/share/uv/tools/omnigent` |
| Latest on PyPI | `omnigent-client` / `omnigent` `0.12.0` (`0.13.0rc3` pre-release) | — |

A migration is "now" only when the pinned client already has the public call. The server
side of every item below was checked in both the 0.2.0 package and the running checkout.

## Reach-ins

Method: `rg '\._[a-z]' src/flowbench/` (everything that is not `self._…` is listed),
plus the `SessionsChat(` construction and the `daemon_launch` import.

| # | Line(s) | Reach-in | Why it exists | Public equivalent | Verdict |
|---|---|---|---|---|---|
| R1 | `omnigent.py:174-177` | `self._client.sessions._http.post(f"{self._client.sessions._base}/v1/sessions", data={"metadata": …}, files={"bundle": …})` | The driver must send `terminal_launch_args` in the create-time metadata (`--disallowedTools AskUserQuestion`, `--permission-mode bypassPermissions`, see `bundle.session_metadata`). `SessionsNamespace.create()` only builds `title` / `labels` / `reasoning_effort` / `workspace` (`_sessions.py:369-377`); upstream HEAD adds `host_type` / `sandbox_provider`, still no launch args. Present since the initial commit (`de6566d`). | **None in any released client.** The **server** accepts `terminal_launch_args` in `SessionCreateMetadata` since 0.2.0 (`omnigent/server/schemas.py:1271`) and validates it at HEAD (`_validate_terminal_launch_args`); only the SDK lacks the parameter. | **blocked-upstream** → draft `items/upstream/omnigent-client-create-launch-args.md`. Do NOT switch to `sessions.create()` before the SDK carries the field: the flags would silently vanish and turn 2+ deadlocks on the AskUserQuestion card (audit-verified trap, epic §S02.5). |
| R2 | `omnigent.py:160`, `:182-186` | `from omnigent_client._sessions_chat import SessionsChat`; `SessionsChat(namespace=…, files_uploader=None, files_getter=None, session=…)` | Consequence of R1: `SessionsChat.create()` / `OmnigentClient.sessions_chat()` create the session themselves via `namespace.create()`, so they cannot carry the metadata either. The driver creates raw, `GET`s the snapshot, and wraps it. | `SessionsChat` is exported from the package root (`omnigent_client/__init__.py:56`, in `__all__`) and its constructor is documented with `:param` for every argument (`_sessions_chat.py:313-321`). | **migrate-now** (import path only): `from omnigent_client import SessionsChat`. The hand construction stays until R1 is resolved; then `SessionsChat.create(namespace, bundle, …)` can replace R1+R2 together once it forwards the new parameter (part of the same upstream ask). |
| R3 | `omnigent.py:155-158`, `:198-204` | `from omnigent.host.daemon_launch import launch_or_reuse_daemon_runner, wait_for_runner_online` | After create, the runner must be spawned on the `claude-native` host and be online before the first inject. These helpers wrap `GET /v1/sessions/{id}` → `POST /v1/hosts/{host_id}/runners` → poll `GET /v1/runners/{id}/status`. | No `hosts` / `runners` namespace in `omnigent_client` (0.2.0 or HEAD: only `sessions`, `files`, `responses`). The module is not underscore-prefixed but belongs to the `omnigent host` CLI, not the SDK — the same import ten harness `main.py`s upstream use. **Server-side alternative** (untested here): `SessionCreateMetadata.host_id` + `workspace` make the server send `host.launch_runner` itself at create (`schemas.py:1241-1251`), which would retire `launch_or_reuse_daemon_runner`; `wait_for_runner_online` still needs the status poll. | **keep, `# UPSTREAM:`** the same draft asks for `host_id`/`workspace` on `create()` so R1+R3 collapse into one call. Part 2 may trial the `host_id` metadata path — needs a live run (V4), not a docs pass. |
| R4 | `omnigent.py:207` | `self._http.get("/v1/hosts")` (own httpx client) | Pick the online host with `claude-native` configured; the driver's own readiness probe (`docs/onboarding.md`). | Public REST, no SDK namespace. | **keep** (public HTTP). Same upstream ask covers a `hosts` namespace if maintainers want one; not a blocker. |

Self-attributes and non-omnigent `_`-hits in the grep (`testing.py`, `watch.py`, `model.py`,
`transcript.py:14` comment, `types.py:19` docstring reference to `_sessions.py:126-127`) are
flowbench's own and out of scope.

## Appendix — raw REST calls that bypass the SDK on purpose

Public HTTP through the driver's own `httpx.AsyncClient`, kept because the SDK's typed models
drop the fields the watchdog reads. Not private-API reach-ins; listed so part 2 can decide.

| Line(s) | Call | Why raw | SDK state |
|---|---|---|---|
| `:231`, `:309`, `:444` | `GET /v1/sessions/{id}` | Watchdog reads `updated_at`, `pending_elicitations`, `terminal_pending`, `labels.omnigent.last_task_error_*` — `Session` dataclass keeps `pending_elicitations_count` / `labels` but drops `updated_at` and `terminal_pending` (`_sessions.py:259-272`; ledger 2026-09-08, flowbench #58). | Public equivalent would need the dataclass to carry the two fields; candidate second upstream ask, low priority (raw JSON works). |
| `:328` | `GET /v1/sessions/{id}/child_sessions?limit=&after=` | Busy sub-agents gate the settle (flowbench #68). | No SDK method. |
| `:407` + `tmux capture-pane` | `GET /v1/sessions/{id}/resources` → `tmux -S <socket> capture-pane -t <target>` | Pane tail recorded on a stall (`stall_reason`, `pane_tail`). | No SDK method; relies on the host being the local machine. |
| `:296` | `sessions.list_items(session_id, order="asc", limit=200, after=)` | — | Public SDK call; fine. |
| `:188`, `:194` | `sessions.set_model_override(…, silent=True)`, `sessions.set_reasoning_effort(…)` | — | Public SDK calls; fine. |

## What part 2 can do

- **Now:** R2 import path. Add `# UPSTREAM: <issue url>` comments on R1 and R3 once filed.
- **After upstream ships** (and the `live` pin moves past it): replace R1+R2 with
  `SessionsChat.create(…, terminal_launch_args=…)`; if `host_id`/`workspace` land too, drop R3's
  launch helper and keep only the online poll. Every step here is a runtime change: V4 live run
  mandatory (`docs/roadmap/verification.md`).
- **Pin bump** is part 2's, coupled to the above: `0.2.0 → 0.12.0` is ten minor versions of a
  pre-1.0 client; bump only against a live run.
