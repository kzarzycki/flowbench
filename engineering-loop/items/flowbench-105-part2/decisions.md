# Decisions — flowbench #105 part 2
- Scope is exactly the inventory's "now" list; R1/R3/watchdog GET stay as they are (documented
  blockers). No pin bump: it needs upstream #6822 first and is a separate live-gated change.
- `sessions.get()` returns the typed `Session`, which carries `labels` in 0.2.0 (`_sessions.py:178`);
  the two call sites only read labels, so nothing is lost.
- Upstream link: #6822 was filed by the owner's instruction on 2026-09-09 (brief text saying
  "still not filed" predates that); markers use the URL, not the draft path.
- Concurrency: S02.4 and S02.6 edit other regions of the same file; rebase before PR and before
  merge, resolve by hand.
- Gate-1 objection (3xx): `omnigent_client.raise_for_status` returns for any status < 400, so
  the SDK read is not byte-for-byte the raw `raise_for_status()` it replaces. Not a live
  difference: a 3xx body is not a Session — `require_json_object` raises on non-JSON and
  `Session.from_dict` indexes `raw["id"]`/`raw["agent_id"]` — so every real redirect (and the
  web UI's HTML-200 for unknown paths) still lands in the `except` → False/None. The only input
  that diverges is a 3xx carrying a complete Session JSON, which no server emits. Pinned through
  the real SDK over `httpx.MockTransport` (`test_resend_allowed_is_false_on_a_redirect_through_the_real_sdk`)
  rather than re-adding a raw status check, which would defeat the migration.
