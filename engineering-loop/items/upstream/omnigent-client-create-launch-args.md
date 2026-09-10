# Upstream draft — omnigent-client: `sessions.create()` cannot send `terminal_launch_args` / `host_id`

Filed 2026-09-09 as https://github.com/omnigent-ai/omnigent/issues/6822.
Target: omnigent-ai/omnigent (kzarzycki/omnigent is a fork with issues disabled).
Checked against upstream `main` @ `cd041834` (2026-09-09): gap present. Duplicate search on
omnigent-ai/omnigent issues + PRs (`terminal_launch_args`, `SessionsNamespace`, `sessions_chat`,
`python-client create`): none; nearest are #5561 (client drops `has_more`) and #5666 (SDK fork
exposure). Shape: issue first; the change is small and additive (client-only, server already accepts
the fields), so a PR can follow if maintainers want one.

---

**Title:** [Feature] python-client: `SessionsNamespace.create()` drops `terminal_launch_args` and `host_id` that the server already accepts

**Body:**

`POST /v1/sessions` (multipart) accepts `terminal_launch_args`, `host_id` and `workspace` in
its `metadata` part — `SessionCreateMetadata` in `omnigent/server/schemas.py` has carried them
since 0.2.0, and `_parse_session_create_metadata` bounds-checks the launch args at HEAD. The
Python SDK cannot send two of them: `SessionsNamespace.create()` builds the metadata dict from
`title` / `labels` / `reasoning_effort` / `workspace` (plus `host_type` / `sandbox_provider`
at HEAD) and nothing else, and `SessionsChat.create()` / `OmnigentClient.sessions_chat()`
route through it.

For a native-harness session driven headlessly, the launch args are the whole point:
`["--disallowedTools", "AskUserQuestion", "--permission-mode", "bypassPermissions"]` on
claude-native, `["--ask-for-approval", "never", "--sandbox", "workspace-write"]` on
codex-native. Without them a native TUI that decides to prompt (a permission card, an
`AskUserQuestion`) blocks in a pane nobody is watching — flowbench hit exactly that on
claude-native before adding the flags (its turn 2+ deadlocked on the AskUserQuestion card).
Today the only way from Python is to bypass the SDK:

```python
resp = await client.sessions._http.post(
    f"{client.sessions._base}/v1/sessions",
    data={"metadata": json.dumps({"terminal_launch_args": [...]})},
    files={"bundle": ("agent.tar.gz", bundle, "application/gzip")},
)
session = await client.sessions.get(resp.json()["session_id"])
chat = SessionsChat(namespace=client.sessions, files_uploader=None, files_getter=None, session=session)
```

and then spawn the runner with `omnigent.host.daemon_launch.launch_or_reuse_daemon_runner`,
which is the `omnigent host` CLI's internal, not the SDK's.

Ask: forward the fields the server already validates —

- `SessionsNamespace.create(..., terminal_launch_args: list[str] | None = None,
  host_id: str | None = None)` (with `workspace`, which is already there); and
- `SessionsChat.create()` / `OmnigentClient.sessions_chat()` forwarding the create metadata
  they currently drop — today they pass only `bundle` and `filename` to `namespace.create()`
  (`_sessions_chat.py`), so `title`, `labels`, `reasoning_effort`, `workspace` and the new
  fields all need to ride through for the helper to be usable without hand-wrapping.

No server change; the request schema is unchanged. Happy to send the PR (client + one test
each) if that is the preferred shape.

Context: flowbench drives claude-native / codex-native sessions through the SDK as a
benchmark meta-harness; inventory of every reach-in this forces is at
kzarzycki/flowbench#105.
