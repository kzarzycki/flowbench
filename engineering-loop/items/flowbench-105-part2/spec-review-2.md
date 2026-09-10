1. **[omnigent.py:486](/Users/zarz/dev/agents/flowbench--s025p2/src/flowbench/driver/omnigent.py:486): label-read timeout changes from 60 to 600 seconds.** Confirmed through real SDK request extensions. `_context_tokens()` has no outer ceiling, so a stalled read can delay capture by nine additional minutes. `_resend_allowed()` inherits this change within its turn ceiling. Preserve the previous failure bound; the SDK constructor’s `timeout` argument is ignored.

2. **[state.lock](/Users/zarz/dev/agents/flowbench--s025p2/state.lock): remove the unrelated tracked empty file.** Added by `9fc7eaa`; violates the explicit scope restriction. Empty file has no line number.

3. **[omnigent.py:259](/Users/zarz/dev/agents/flowbench--s025p2/src/flowbench/driver/omnigent.py:259): correct “raises on non-2xx.”** SDK `_errors.py` accepts statuses below 400. Matching test-helper descriptions also overstate the guarantee.

I withdraw the prior requirement for strict redirect-status checking. `require_json_object` rejects empty/HTML bodies; `Session.from_dict` requires session fields. A complete-Session 3xx remains a theoretical divergence, without evidence of a realistic producer for this endpoint. No extra status request is justified. `sessions.get()` exposes no response status.

Otherwise, standards and spec checks pass: dictionary labels retain the same server field; every pre-existing assertion remains unchanged; fakes target `sessions.get`; A1–A3 pass. Reverting the import fails the start test as required. R1 POST, R3 helpers, watchdog GET, and concurrent engine regions remain untouched.

Verification: redirect test **1 passed**, driver tests **74 passed**, full suite **299 passed, 1 skipped**, Ruff and timeout probe **exit 0**. Import mutation **exit 1**, expected. A4 live run excluded; worktree unchanged.

REVISE
