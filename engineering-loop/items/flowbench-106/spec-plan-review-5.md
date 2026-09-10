REVISE

At the supplied paths, the documents still describe raw HTTP reads and base `f4cb85e`. The SDK rewrite described in the request is absent.

1. **[spec] The exception tuple would regress expected fallbacks.** [Spec line 20](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/spec.md:20) omits `OmnigentError`, `KeyError`, and `TimeoutError`. Reading the installed SDK and probing it confirmed: 503/non-JSON/non-object responses raise SDK errors; incomplete session objects raise `KeyError`; `asyncio.timeout` raises `TimeoutError`. None matches the proposed tuple. Specify their treatment and preserve the existing bounded-read fallback.

2. **[spec] The malformed-body and status contracts contradict the SDK.** [Session.from_dict](/Users/zarz/dev/agents/flowbench--s026/.venv/lib/python3.13/site-packages/omnigent_client/_sessions.py:192) normalizes **every non-dict labels value to `{}`**. Probes with `[]`, `["x"]`, `""`, `0`, and `7` therefore returned resend `True`, without an exception to log. AC2 cannot distinguish these from missing labels through `sessions.get()`. Also, SDK status handling permits 3xx: a 302 carrying a complete session returned token count `123`. The blanket “non-2xx” guarantee is false, while 503→`None` already works. Rewrite AC2/AC3 and the corresponding [decisions](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/decisions.md:12) around observable SDK behavior; enforcing a stronger wire-level contract would require an explicit scope decision.

3. **[plan] Task 1 targets obsolete interfaces, so its tests cannot establish the contract.** [Task 1](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:16) names nonexistent `_LabelHttp`/`_FailingStatusHttp`, local response fakes already removed, and `_http.get`, which neither label read calls. Implementation instructions reference nonexistent `resp`. Use `_label_client(boom=...)` for injected failures and `_real_sdk_client` for wire-body/status cases, supplying complete session fields when testing labels. Preserve `sessions.get()` and its timeout. `_FakeSessions` returns labels directly, so it cannot prove SDK normalization.

4. **[plan] The actual task order violates the green-after-each-task requirement.** [Task 3](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:110) already enables BLE while Task 1 remains outstanding. Current lint exits **1**, reporting all four driver catches. Describe how commits are reordered or combined to keep each task green. Move the final coverage gate after Task 1; its current placement never measures that task. Also, coverage’s `source = ["src"]` excludes the changed scorer.

5. **[plan] The promised live validation has no executable task.** Spec and decisions require a post-merge todo_app run, but the plan ends at offline checks. Add the invocation, watcher/completion check, and objective success conditions. Reconcile that choice with [verification.md’s mandatory V4](/Users/zarz/dev/agents/flowbench--s026/docs/roadmap/verification.md:35) for driver/send-policy changes.

Independent traceability:

| Criterion | Task → test/check | Assessment |
|---|---|---|
| AC1 | T3 → Ruff + waiver inspection | Currently fails |
| AC2 | T1 → transport, foreign-error, malformed-body matrices; existing retry-row tests | Obsolete seams; SDK cases missing |
| AC3 | T1 → 503 token-body test | Obsolete seam |
| AC4 | T2 → transcript fallback, watcher propagation, unreadable-directory tests | Implemented |
| AC5 | T1 four logger assertions + T2 three | T2 implemented; T1 needs corrected seams |
| AC6 | T1 → existing close/pane swallow tests | Tests exist and pass |
| V1 | T3 → suite + diff-cover | Runs before final task; excludes scorer |
| Live validation | No task/test | Missing |

The seven-site scope, three reasoned waivers, BLE enforcement, and exclusion of the cap-status race are reasonable issue/code inferences.

Verification: initial UV commands exited **2** because the default cache was inaccessible. Retried with a writable cache and `--no-sync`: pytest **0** (303 passed, 1 skipped), formatting **0**, lint **1**, diff-cover **0** (100% of nine measured lines). SDK probe exited **0**.
