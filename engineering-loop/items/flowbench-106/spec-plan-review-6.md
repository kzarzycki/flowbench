REVISE

The spec reflects the SDK migration; Task 1 at the supplied path still describes raw HTTP reads. Only Task 2 is committed (`88fedd4`); Tasks 1 and 3 remain outstanding.

1. **[spec] `OverflowError` is reachable and its omission regresses fallbacks.** [Decisions line 42](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/decisions.md:42) claims otherwise. The installed SDK preserves dictionary label values and converts numeric Session fields with `int()`. Real-SDK probes with JSON `1e400` produced `OverflowError` for `created_at`, `context_window`, and the token-label conversion. Current catches return `False`/`None`; the proposed tuple would propagate. Include `OverflowError`, correct the reasoning, and add regression cases for SDK-field and label-value conversion.

2. **[spec] The non-string-message contract exceeds what the proposed membership check guarantees.** [Spec line 48](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/spec.md:48) says non-string messages raise `TypeError` today and will return `False`. Lists and dictionaries do neither: real-SDK probes with `["not delivered"]` and `{"not delivered": true}` returned resend `True`. Resolve whether the contract covers all non-strings or specifically null/non-iterable values. For the stated all-non-string contract, require a string check, test both containers, and record the additional behavior change.

3. **[plan] Task 1 targets obsolete interfaces and contradicts revised AC2/AC3.** [Task 1](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:16) still names `_LabelHttp`, `_FailingStatusHttp`, removed response fakes, `_http.get`, and nonexistent `resp`; its tuple omits SDK errors and the timeout. Rewrite around `_client.sessions.get()` under the existing timeout, `_label_read_errors()`, `_label_client(boom=...)`, and `_real_sdk_client`. Supply complete Session bodies for label tests. Update both existing `RuntimeError("transport gone")` fixtures to transport exceptions. Also make `_FakeSessions`’ default labels `{}`: it currently returns `None`, which becomes incompatible when removing `or {}`. SDK-normalized non-dict labels must expect `True`, without a driver exception log.

4. **[plan] Task order still cannot remain green with Task 1 last.** [Task 3](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:110) enables BLE before the outstanding driver fixes. The explicit audit exits **1** on four driver catches. State the actual execution order and combine BLE enablement with the final driver task, or otherwise resolve that dependency. Run the final coverage gate after all implementation changes.

5. **[plan] Coverage expansion has no implementation task.** The spec requires `scenarios` coverage, but [Task 3](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/plan.md:110) never changes `[tool.coverage.run].source`. Current diff-cover reports 100% over nine lines in transcript/watch and entirely excludes the changed scorer. Assign the configuration change and verify the scorer appears in the final report.

6. **[plan] Required live validation remains unplanned.** [Spec line 90](/Users/zarz/dev/xebia/flowbench-scenarios--s026/.claude/engineering-loop/items/flowbench-106/spec.md:90) and decisions refer to Task 4, but the plan ends at Task 3. Add executable V4/V5 instructions: checkout/run directory, commands, watcher and process completion checks, and objective artifact/result assertions. Until then, “clean live runs as defined there” has no definition.

Independent traceability:

| Criterion | Task → test/check | Assessment |
|---|---|---|
| AC1 | T3 → Ruff and reasoned-waiver audit | Blocked by task order |
| AC2 | T1 → injected-error matrix, real-SDK body matrix, retry rows, foreign-error propagation | Obsolete seams; revised cases missing |
| AC3 | T1 → real-SDK 503 containing token label | Plan uses obsolete HTTP double |
| AC4 | T2 → transcript exceptions, watcher fallback/propagation, unreadable directory | Implemented; tests pass |
| AC5 | T1 → four driver logger checks; T2 → three other logger checks | T2 complete; label-test seams need correction |
| AC6 | T1 → existing close/pane swallow tests | Existing tests pass |
| V1 | T3 → suite and diff-cover | Wrong placement; scorer excluded |
| V4/V5 | Referenced T4 → live completion/artifact checks | Task absent |

Round-5 closure: **#1 closed for its named exception omissions; #2 closed in spec/decisions only; #3 open; #4 partially closed by removing premature BLE enablement from the branch, but sequencing/coverage remain open; #5 open.** The seven-site scope, reasoned waivers, and exclusion of the cap-status race remain reasonable.

Verification using `uv run --no-sync` with a writable cache: SDK probe **0**; pytest **0** (303 passed, 1 skipped); lint **0**; formatting **0**; explicit BLE audit **1**; diff-cover **0**, with the exclusion described above.
