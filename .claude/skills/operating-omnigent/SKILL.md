---
name: operating-omnigent
description: "Operate a local Omnigent install — crashes, blank UI, restarts, session attach/resume/dispose, process topology — and drive other agents via the sys_* MCP tools."
when_to_use: "Any omnigent operational question or when spawning/monitoring other agents from inside a turn."
---

# Operating Omnigent

Omnigent runs as **one server (control plane) + N runners (one per open session)** on the user's machine. Most "is it broken?" questions are answered by hitting the server's `/health` and `/v1/sessions` — not by killing processes or reading source. Use the HTTP API and the `omnigent` CLI; reach for `kill` only as a last resort (auto-mode blocks raw kills, and killing a runner orphans it rather than disposing the session).

## Topology (what's running and why)

| Piece | Process / how to find | Notes |
|---|---|---|
| **Server** (API + web UI) | `omnigent.cli server`, binds `127.0.0.1:6767` | FastAPI/uvicorn. DB = `~/.omnigent/chat.db`, artifacts = `~/.omnigent/artifacts`. One per machine. |
| **Runner** (one per session) | `omnigent.runner._entry`, ~1 PID per open chat | Idle-reaps after **1h** (`runner.idle_timeout_s`, default 3600s). Each also spawns its own `tmux` + `claude`/`codex` terminal — that's why `ps | grep omnigent` looks crowded. |
| **Logs** | server: `~/.omnigent/logs/server/local-server-*.log`; runner: `~/.omnigent/logs/host-runner/runner-<id>.log`; cli: `~/.omnigent/logs/cli-*.log` | Log *files* accumulate one-per-session-ever — they are NOT live processes. Count `omnigent.runner._entry` PIDs for the real number. |

Probe with `python3` urllib or the `omnigent` CLI — **`curl` is often not on PATH** in non-login shells here.

## Diagnose "can't open omnigent" / `{"detail":"Not Found"}`

```python
import urllib.request, json
g = lambda p: urllib.request.urlopen("http://127.0.0.1:6767"+p, timeout=5)
print(g("/health").read())          # {"status":"ok"}  -> server is ALIVE
g("/docs"); g("/openapi.json")      # API up
```

- **`/health` ok but `/` returns `{"detail":"Not Found"}`** → server is fine; the **web SPA isn't mounted**. The SPA is mounted **once at startup** (`omnigent/server/app.py`, `_WEB_UI_DIST = .../server/static/web-ui`) only if `web-ui/index.html` exists *at boot*. If the server booted **before** the frontend was built (common with editable/dev installs that rebuild the UI later), `/` 404s for every fresh page load until restart. An already-open tab keeps working over its websocket; only **new** tabs fetch `/` and break.
  - **Verify:** server start time (`ps -o lstart -p <pid>`) vs `web-ui/index.html` mtime. UI built after boot ⇒ this is it.
  - **Fix:** restart the server (see below). It re-evaluates the mount.
- **`/health` unreachable** → server is actually down. `omnigent server start`.

## Sessions via the API

```python
s = json.load(g("/v1/sessions"))            # {object, data:[...], has_more, first_id, last_id}
# each item: id (conv_...), agent_name, status (running|idle|failed), title,
#            runner_id, workspace, external_session_id, archived
json.load(g("/v1/sessions/conv_xxx"))       # full detail: items, todos, llm_model, parent_session_id, ...
```

Map a **runner PID → session**: find its log via `lsof -p <pid> | grep host-runner`, then `grep -oE 'conv_[0-9a-f]{32}' <log>` and cross-ref `/v1/sessions`.

## Spawn & drive agents (MCP `sys_*`, from inside a turn)

Available when an Omnigent turn advertises the `sys_*` tools. This is the runtime delegation path — launch an **already-registered** agent and drive it; no files. (Authoring a *new* agent type is a separate skill, `build-omnigent`: write a `config.yaml` dir, then launch with `config_path=` below.)

| Step | Tool | Notes |
|---|---|---|
| Find agents | `sys_agent_list` | returns `agent_id`s. Builtins: `claude-native-ui` (full Claude Code coding harness), `codex-native-ui`, `polly` (delegating orchestrator), `debby` (Claude+GPT brainstorm). |
| Spawn | `sys_session_create(agent_id, message?, title?)` | runs **async**, returns `conversation_id`. **Children only** — no top-level/sibling sessions. **`message=` set → it queues a turn that auto-notifies + delivers to your inbox on completion** (same as `send`; no polling needed). **`message=` omitted → idle session, no turn, so nothing ever notifies** — you must `sys_session_send` to give it work, or poll `get_info`. `config_path=` instead of `agent_id` uploads + launches a fresh agent from a local YAML/dir/.tar.gz. |
| Drive / delegate more | `sys_session_send(session_id, args)` | posts a turn to a child. **Dispatches async** — returns a `launching` handle immediately (there is NO synchronous/blocking variant); the result lands in the inbox and a completion notification auto-fires into your next turn. Don't poll in a `sleep` loop — just wait for the notification, then `sys_read_inbox`. Parallel fan-out: emit several calls in one response. Sending to an already-**running** child queues an override that supersedes at the next turn boundary — this is the lever for redirecting a child mid-run (see Gotchas). |
| Monitor | `sys_session_get_info(session_id)` | poll `status`: `running` → `idle` = turn done. `failed` ≠ empty — it **may still hold a complete result** (codex-native flips to `failed` right after emitting its final message); always read `get_history` before concluding it produced nothing. Metadata only. |
| Collect | `sys_session_get_history(conversation_id, tail_items)` | transcript tail (≤50). Global read — any session you can access, not just your children. |
| Non-blocking fan-out | `sys_call_async` + `sys_read_inbox` | dispatch background work; completions auto-deliver to the inbox. |

**Simplest procedure (harness-agnostic — codex-native, claude-native, any registered agent). Two tool calls, no polling, no `sleep`:**

1. `sys_session_create(agent_id, message="…task…", title="…")` — one call, create + queue the task together. Returns `conversation_id`, status `running`.
2. Wait. The runtime auto-injects a `[System: sub-agent … finished (completed) — N results waiting in inbox]` message into your next turn — you do nothing to earn it.
3. `sys_read_inbox()` — one call, returns the child's full final text.

Follow-up turns: `sys_session_send(session_id, args="…")` → wait for the next auto-notification → `sys_read_inbox`. Conversation context persists across turns.

There is **no synchronous/blocking tool** — the substrate is async-only by design (`tool_dispatch.py`: `send`/`create` "returns a launching handle immediately … completion pushed into the parent's `sys_read_inbox` queue"; `sys_read_inbox` is a *non-blocking* drain). Async is the only mode; the push-notification is what makes it feel seamless. **Don't** replicate the clunky pattern of `sleep` + repeated `get_info`/`get_history` — that's only for debugging a session that won't start. For a throwaway helper on *your own* model, your native subagent/`Agent` tool is genuinely synchronous and simpler than an omnigent child session; reach for omnigent sessions when you need a *different* harness (codex-native etc.) or a durable, independently-visible session.

**Don't hand-roll multi-agent coding.** `polly` already plans a goal → delegates to Claude/Codex/Pi sub-agents in parallel worktrees → routes each diff to a different-vendor reviewer. Launch it: `sys_session_create(agent_id=<polly>, message=<goal>)`.

## Commands & endpoints (no exploration needed)

| Action | How |
|---|---|
| Restart server | `omnigent stop && omnigent server start` (`server status` to check). **Drops every websocket — all live tabs/sessions reconnect; mid-turn work is interrupted.** Sessions persist (sqlite). |
| Attach to a LIVE session | `omnigent attach conv_xxx` — joins & streams I/O, starts nothing. Interactive REPL → run in a real terminal (or `!`-prefix), not headless. |
| Reopen a stored session | `omnigent resume conv_xxx` (claude-native lands in `omnigent claude`). |
| **Dispose** a chat (hard) | `DELETE /v1/sessions/conv_xxx` → tears down tasks/terminals/files/conv row. **Irreversible.** Owner-level. Does **NOT** kill the runner process — it orphans it (reaps on idle timeout). |
| Archive (reversible) | `PATCH /v1/sessions/conv_xxx` body `{"archived": true}` — hides it, keeps transcript. |

## Gotchas

- **Editable/dev install:** `omnigent` may be an editable install from a clone (e.g. `/Users/zarz/dev/ext/omnigent`). `omnigent` is a **namespace package** — `omnigent.__file__` is `None`; resolve source with `list(omnigent.__path__)` or `importlib.util.find_spec("omnigent.cli").origin`. Don't delete/move the clone or switch its branch — it breaks the running install.
- **You may be running INSIDE omnigent.** If `OMNIGENT_RUNNER_ID` is set, this session IS an omnigent runner — restarting the server kills your own session. Prefer telling the user to restart from a normal terminal.
- **`DELETE` ≠ kill.** Deleting a session removes it from the DB/UI but leaves the runner OS process running (orphaned); it self-reaps within the idle timeout (~1h). To stop it *now*, the user must approve a `kill <pid>` (auto-mode blocks the agent from killing processes it only identified from internal output).
- **`sys_session_close` (MCP) is narrow.** It only tombstones `sys_session_send`-style *named* sub-agents in your spawn tree — returns `session_out_of_tree` for independent top-level chats and `session_not_a_sub_agent` for sessions you made with `sys_session_create`. Don't rely on it for cleanup: spawned runners idle-reap in ~1h anyway, or use HTTP `DELETE`/`PATCH` to dispose/archive now.
- **CLI path fallback:** if `omnigent` isn't on PATH, the uv-tool interpreter runs everything: `~/.local/share/uv/tools/omnigent/bin/python3 -m omnigent.cli ...`.
- **Don't trust stale counts.** "~50 sessions" in notes usually means 50 *log files*, not live runners. Always recount live `omnigent.runner._entry` PIDs.
- **Stopping a RUNNING child turn — `sys_cancel_task` IS a real mid-turn hard-kill, with one catch.** `sys_cancel_task(child_conv_id)` force-cancels the runner's in-flight turn task immediately (for claude-native children it hard-kills the worker tmux pane via a `stop_session` event) — it does *not* wait for a turn boundary (`tool_dispatch.py:5296-5364`). BUT it only fires if the child is a **non-terminal sub-agent registered under the calling session**. `sys_session_send`/`sys_call_async` register that work entry; a session spawned with bare `sys_session_create` may not be — so cancel returns `no in-flight task`, which means *"not your tracked child / already terminal,"* NOT *"conv ids are unsupported."* When that happens the reliable fallback is the HTTP event API: `POST /v1/sessions/{id}/events {"type":"interrupt"}` (force-cancels the turn task, `routes/sessions.py:16660`) or `{"type":"stop_session"}` (owner-only, kills the live session). Caveat: **codex-native cancellation is best-effort** — no runner-side hard-stop is wired, so the child may keep running.
  - **Not stops:** `sys_session_close` only tombstones (returns `sub_agent_busy` mid-turn); `sys_cancel_async` only cancels local `sys_call_async` tasks; HTTP `DELETE /v1/sessions/{id}` only frees resources + deletes the row — **the turn keeps running** (it calls runner `cleanup_session_resources`, not the turn-cancelling path).
  - Sending an override via `sys_session_send` still works to *redirect* a child (lands at the next turn boundary) — but that's a course-correction, not a stop.
- **Native-TUI child sessions hang on startup after a plugin/marketplace sync.** `codex-native` (and other `--remote` TUI harnesses) cold-start a real TUI whose thread-creation is what the runner waits ~30s for. If the user's plugin hooks changed (e.g. a marketplace auto-synced), the TUI freezes on codex's interactive **"Hooks need review — N hooks new/changed"** trust gate and never creates a thread → session goes `running` → `failed`, and `get_info` shows **`model: null`** (the fast tell vs. a healthy start, which shows the real model like `gpt-5.5`). Fix is user-side: run `codex` once and pick "Trust all", or update codex — then new child sessions start clean. Not a bug in your spawn call; retrying the same call won't help until the hooks are trusted.
- **The auto-mode classifier vets the brief you spawn with — not just your own tool calls.** A `sys_session_create`/`sys_session_send` whose *prompt* instructs an outward or unauthorized action — push to a default branch, reuse a credential from another project, etc. — is **denied at spawn time**, before the child starts. Keep delegated briefs to in-scope, authorized actions: gate pushes/PRs/secret use behind the user (e.g. "commit to a local branch, do NOT push"), or the spawn itself fails.
