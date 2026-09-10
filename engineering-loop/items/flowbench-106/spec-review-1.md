REVISE

1. **AC2 lacks a precise malformed-body contract.** In [`_resend_allowed`](/Users/zarz/dev/agents/flowbench--s026/src/flowbench/driver/omnigent.py:254), label interpretation occurs outside the catch. Probes confirmed `labels: ["unexpected"]` raises `AttributeError`, a null error message raises `TypeError`, and `labels: []` permits retry. Changing the exception tuple cannot deliver AC2. Specify accepted shapes, validation boundaries, and expected outcomes while preserving legitimate missing-label retries.

2. **The proposed taxonomy still propagates malformed server data as a supposed programming bug.** Valid JSON containing `{"labels":{"omnigent.last_context_tokens":1e400}}` produces `OverflowError` during integer conversion. The proposed tuple excludes it; current code returns `None`. Define and test this fallback rather than claiming all garbage labels remain covered.

3. **The safety rationale and two decisions contain false premises.** [`decisions.md:24`](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/decisions.md:24) says adding status checking leaves the outcome unchanged. A probe returned `123` from a 503 response containing that token label; AC3 changes it to `None`. Also, send-path effects extend beyond `_resend_allowed`: [`_send_once`](/Users/zarz/dev/agents/flowbench--s026/src/flowbench/driver/omnigent.py:273) calls `to_jsonable`, whose newly propagated exceptions can abort sending. Correct both claims and cover the latter effect in verification.

4. **AC1 contradicts the declared exclusions.** It requires every remaining textual `except Exception` to carry the exact `--` waiver format, while preserving `run.py`’s existing single-hyphen waivers and excluding the generated-program string in `acceptance.py`. Define the audit over executable catch sites and accept existing reasoned waivers, or explicitly specify their normalization.

5. **AC5 does not verify “every site logs.”** One test for `omnigent` can pass while three of its four handlers remain silent. Require DEBUG exception assertions for each of the seven targeted catch sites; parameterization keeps this size S.

Read-only probes exited 0. The baseline BLE audit exited 1 with six unwaived findings; the seventh site is suppressed by its existing waiver.
