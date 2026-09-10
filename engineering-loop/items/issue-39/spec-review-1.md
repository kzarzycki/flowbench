Findings:

1. Blocking: AC1 is unsafe for this target. `TurnResult.assistant_text` is the latest assistant text in the whole session, not proof that this prompt got a fresh reply. In [driver.py](/Users/zarz/dev/flowbench/src/flowbench/runner/driver.py:471), `_send_once()` returns `last_assistant_text(items)`. In a persistent `OmnigentModel`, a failed injection after prior simulator/judge turns can return stale text from the previous turn. The spec’s “failed + non-empty text -> return it” rule is only safe if the driver can prove a new assistant message landed.

2. Blocking: the retry rule is not double-delivery-safe as written. `failed + empty assistant_text` does not prove non-delivery; it proves only that no assistant text was captured. The upstream driver intentionally retries only when `_injection_undelivered()` confirms “not delivered” labels in [driver.py](/Users/zarz/dev/flowbench/src/flowbench/runner/driver.py:422). Scenario-side blind resend can duplicate a delivered prompt in the same stateful simulator/judge session.

3. ACs are observable but insufficient. They encode the proposed behavior, not the correctness boundary. Missing ACs: stale prior assistant text must not be reused as the answer to a new prompt; delivered-but-silent failure must not be blindly resent; `timeout` behavior should be specified separately from `failed`.

Simpler sufficient fix: either only trust non-idle text when the driver exposes that it is new for this send, or fix/extend the driver to return delivery/fresh-reply metadata and keep retry ownership there. As a narrow scenario-side mitigation, “non-idle + non-empty text” is plausible only for a fresh one-shot session or with a new-message proof; otherwise it risks corrupting the run.

VERDICT: REVISE - prove fresh assistant text before trusting it, and do not scenario-retry failed empty turns without confirmed non-delivery.
