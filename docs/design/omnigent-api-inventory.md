# Omnigent private-API inventory (E02 S02.5, part 1)

What `src/flowbench/driver/omnigent.py` takes from omnigent that is not a public,
documented SDK call, and what to do about each. Written against the driver at
`883e0d0`; the migrate-now verdicts landed in `620b16b` (#129), the rest wait on upstream. Tracking issue: flowbench #105.

## Two truths, checked separately

| What | Version | Where |
|---|---|---|
| Client the driver imports (`omnigent_client`, `omnigent.host`) | `0.2.0` (pinned in `pyproject.toml`, `live` extra) | repo venv |
| Server that answers the requests | `0.13.0.dev0`, editable checkout `~/dev/ext/omnigent/omnigent` @ `8627eb9f` (fork of `omnigent-ai/omnigent`, 21 commits behind its `main` @ `cd041834`) | `~/.local/share/uv/tools/omnigent` |
| Latest on PyPI | `omnigent-client` / `omnigent` `0.12.0` (`0.13.0rc3` pre-release) | — |

A migration is "now" only when the pinned client already has the public call. "HEAD" below
means the fork checkout; every client-side claim was re-checked against `upstream/main` and
holds there too. Schema acceptance and working behaviour are stated separately where they
differ between 0.2.0 and HEAD.

## Reach-ins

Method: `rg '\._[a-z]' src/flowbench/` (everything that is not `self._…` is listed),
plus the `SessionsChat(` construction and the `daemon_launch` import.

| # | Line(s) | Reach-in | Why it exists | Public equivalent | Verdict |
|---|---|---|---|---|---|
| R1 | `omnigent.py:174-177` | `self._client.sessions._http.post(f"{self._client.sessions._base}/v1/sessions", data={"metadata": …}, files={"bundle": …})` | The driver must send `terminal_launch_args` in the create-time metadata (`--disallowedTools AskUserQuestion`, `--permission-mode bypassPermissions`, see `bundle.session_metadata`). `SessionsNamespace.create()` only builds `title` / `labels` / `reasoning_effort` / `workspace` (`_sessions.py:369-377`); HEAD adds `host_type` / `sandbox_provider`, still no launch args. Present since the initial commit (`de6566d`). | **None in any client version.** The **server** accepts `terminal_launch_args` in `SessionCreateMetadata` since 0.2.0 (`omnigent/server/schemas.py:1271`) and validates it at HEAD (`_validate_terminal_launch_args`); only the SDK lacks the parameter. | **blocked-upstream** → upstream omnigent-ai/omnigent#6822 (https://github.com/omnigent-ai/omnigent/issues/6822). Do NOT switch to `sessions.create()` before the SDK carries the field: the flags would silently vanish and turn 2+ deadlocks on the AskUserQuestion card (audit-verified trap, epic §S02.5). |
| R2 | `omnigent.py:160`, `:182-186` | `from omnigent_client._sessions_chat import SessionsChat`; `SessionsChat(namespace=…, files_uploader=None, files_getter=None, session=…)` | Consequence of R1: `SessionsChat.create()` / `OmnigentClient.sessions_chat()` create the session themselves via `namespace.create(bundle, filename=filename)` — they forward nothing else, not even `title`/`labels` (`_sessions_chat.py:409` in 0.2.0, `:422` at HEAD). The driver creates raw, `GET`s the snapshot, and wraps it. | `SessionsChat` is exported from the package root (`omnigent_client/__init__.py:56`, in `__all__`) and its constructor arguments are documented (`_sessions_chat.py:329-342`). | **done in `620b16b`** (import path): `from omnigent_client import SessionsChat`. The hand construction (create → `get` → wrap) stays until upstream forwards the full metadata (`terminal_launch_args`, `host_id`, `workspace`, `title`, `labels`) through `SessionsChat.create()`; forwarding only the first two would still lose the session title and the `omni_project` label the web UI groups on. |
| R3 | `omnigent.py:155-158`, `:198-204` | `from omnigent.host.daemon_launch import launch_or_reuse_daemon_runner, wait_for_runner_online` | After create, the runner must be spawned on the `claude-native` host and be online before the first inject. The helpers: `GET /v1/sessions/{id}` → if a bound runner is still online, reuse it, else `PATCH` the stale `runner_id` to `""` → `POST /v1/hosts/{host_id}/runners` → poll `GET /v1/runners/{id}/status` until `online` (fails fast on a reported exit). | No `hosts` / `runners` namespace in `omnigent_client` (0.2.0 or HEAD: only `sessions`, `files`, `responses`). The module is not underscore-prefixed but belongs to the `omnigent host` CLI, not the SDK — the same import 11 harness `main.py`s upstream use. **Server-side alternative:** `SessionCreateMetadata.host_id` + `workspace`. The 0.2.0 schema *accepts* both, but its multipart create handler never reads `host_id` (`routes/sessions.py:12468-12498` creates and returns); the launch on create is implemented only at HEAD (`routes/sessions/routes_core.py:834-846`, `_bind_and_launch_on_caller_host`). It would retire `launch_or_reuse_daemon_runner` on a new server; `wait_for_runner_online` still needs the status poll. | **keep, `# UPSTREAM:`** omnigent-ai/omnigent#6822 (the issue also asks for `host_id`/`workspace` on `create()`). Part 2 may trial the `host_id` metadata path against the running server — needs a live run (V4), and pins the engine to a server newer than 0.2.0. |
| R4 | `omnigent.py:207` | `self._http.get("/v1/hosts")` (own httpx client) | Pick the online host with `claude-native` configured; the driver's own readiness probe (`docs/onboarding.md`). | Public REST, no SDK namespace in any version. | **keep** (public HTTP). Not covered by the draft; file separately only if a typed call is wanted. |

Self-attributes and non-omnigent `_`-hits in the grep (`testing.py`, `watch.py`, `model.py`,
`transcript.py:14` comment, `types.py:19` docstring reference to `_sessions.py:126-127`) are
flowbench's own and out of scope.

## Appendix — raw REST calls that bypass the SDK on purpose

Public HTTP through the driver's own `httpx.AsyncClient`. Not private-API reach-ins; listed for the
record.

| Line(s) | Call | Why raw | SDK state |
|---|---|---|---|
| `:309` (`_snapshot`, the watchdog) | `GET /v1/sessions/{id}` | Reads `status`, `updated_at`, `pending_elicitations`, `terminal_pending`. The 0.2.0 `Session` dataclass (`_sessions.py:102-223`) has none of the last three (`updated_at` and `pending_elicitations_count` live on `SessionListItem`, `:228-272`, which `get()` does not return). HEAD's `Session` adds `updated_at` (`:190`) but still no pending signals. Ledger 2026-09-08, flowbench #58. | Raw stays until `Session` carries the pending signals; low-priority second upstream ask. |
| `:231` (`_injection_undelivered`), `:444` (`_context_tokens`) | `GET /v1/sessions/{id}` | Read only `labels`. | **done in `620b16b`**: both read `sessions.get(session_id).labels`, bounded at 60 s (`_LABEL_READ_S`) because the SDK's httpx client ignores its `timeout` argument and reads with the 600 s SSE budget. `raise_for_status` in the SDK lets 3xx through, but a redirect body is not a Session (`require_json_object` / `Session.from_dict` raise), so the unknown ⇒ False/None branch still holds; pinned through the real `SessionsNamespace` in `tests/driver/test_omnigent.py`. |
| `:328` (`_children`) | `GET /v1/sessions/{id}/child_sessions?limit=200&after=` | Busy sub-agents gate the settle; must traverse every page (flowbench #68). | None in 0.2.0. HEAD has `SessionsNamespace.child_sessions(session_id, *, limit=100)` (`_sessions.py:890`) — no `after`, discards `has_more` (upstream #5561 reports the same for `list_items`), so it cannot replace the exhaustive traversal. |
| `:407` + `tmux capture-pane` | `GET /v1/sessions/{id}/resources` → `tmux -S <socket> capture-pane -t <target>` | Pane tail recorded on a stall (`stall_reason`, `pane_tail`). | No SDK method; relies on the host being the local machine. |
| `:296` | `sessions.list_items(session_id, order="asc", limit=200, after=)` | — | Public SDK call; fine. |
| `:188`, `:194` | `sessions.set_model_override(…, silent=True)`, `sessions.set_reasoning_effort(…)` | — | Public SDK calls; fine. |

## What is left

- **Done (`620b16b`):** R2 import path, the two labels-only reads via `sessions.get()`,
  `# UPSTREAM:` markers on R1 and R3 pointing at omnigent-ai/omnigent#6822.
- **After upstream ships** (and the `live` pin moves past it): replace R1+R2 with
  `SessionsChat.create(…)` only if it forwards the full metadata listed under R2; if
  `host_id`/`workspace` land too, drop R3's launch helper and keep only the online poll. Every
  step here is a runtime change: V4 live run mandatory (`docs/roadmap/verification.md`).
- **Pin bump** is coupled to the above: `0.2.0 → 0.12.0` is ten minor versions of a
  pre-1.0 client; bump only against a live run.
