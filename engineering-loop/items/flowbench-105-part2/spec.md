# flowbench #105, part 2 — migrate the reach-ins the inventory marks "now"

**Problem.** `docs/design/omnigent-api-inventory.md` (engine `e8f0c64`) lists four reach-ins
into omnigent's private surface. Three are blocked on upstream (omnigent-ai/omnigent#6822) or
have no SDK equivalent; the rest can move to public calls today without a behaviour change.

**Chosen fix** (all in `src/flowbench/driver/omnigent.py`, S02.5 region only):
1. R2: `from omnigent_client import SessionsChat` (root export, in `__all__`) instead of the
   `omnigent_client._sessions_chat` module path. Construction unchanged.
2. The two labels-only raw GETs — `_resend_allowed` and `_context_tokens` — read
   `(await self._client.sessions.get(session_id)).labels` instead of
   `self._http.get("/v1/sessions/{id}").json()["labels"]`. `sessions.get` raises
   `OmnigentError` on non-2xx, so the "HTTP error ⇒ unknown ⇒ False/None" branch is kept by the
   same `except`. The watchdog's `_snapshot` GET stays raw (0.2.0 `Session` lacks
   `updated_at`/pending signals).
3. `# UPSTREAM: https://github.com/omnigent-ai/omnigent/issues/6822` on R1 (raw create) and R3
   (`daemon_launch` import).

**Why safe.** No wire change: same endpoints, same fields read. Tests that stubbed `_http`
for the two label reads now stub `_client.sessions.get`; the start() test patches
`omnigent_client.SessionsChat` (where the driver now imports it from). Live path is touched
(session create, labels on every FAILED turn and at capture), so V4 applies.

**Acceptance.**
- A1 `rg '_sessions_chat' src/` → no hits; `rg 'UPSTREAM' src/flowbench/driver/omnigent.py` → 2 hits, both with the #6822 URL.
- A2 `rg '_http.get\(f"/v1/sessions/\{self._chat.session_id\}"\)' src/flowbench/driver/omnigent.py` → exactly 1 hit (`_snapshot`).
- A3 Existing tests for `_resend_allowed` rows 1/3, error label, read failure, and HTTP-error
  status all still pass with the SDK-backed read; `_context_tokens` tests likewise.
- A4 Offline suite green; V4: one caffeinated `todo_app` live run, both flows `idle`, scorecards
  present, no Traceback.
