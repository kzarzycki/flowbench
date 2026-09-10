REVISE

Four test-gate objections:

- [test_omnigent.py:1698](/Users/zarz/dev/agents/flowbench--s026/tests/driver/test_omnigent.py:1698): the “SDK overflow” test catches `ValueError` from `httpx.Response(json=body)` before SDK parsing. It passes after removing `OverflowError`. Supply raw JSON containing `1e400`; that corrected test fails without the catch.
- [test_watch.py:103](/Users/zarz/dev/agents/flowbench--s026/tests/test_watch.py:103): removing `HTTPException`, `ValueError`, or `AttributeError` individually leaves the full suite green. Add realistic HTTP/JSON failure cases.
- [test_scorers.py:314](/Users/zarz/dev/agents/flowbench--s026/tests/scenarios/todo_app/test_scorers.py:314): removing `ValueError` leaves the full suite green. Cover invalid UTF-8 source input.
- [omnigent.py:294](/Users/zarz/dev/agents/flowbench--s026/src/flowbench/driver/omnigent.py:294), also line 526: restoring both `or {}` expressions survives the full suite. The explicit structural prohibition needs an executable check; SDK dictionary inputs cannot distinguish this mutation behaviorally.

Baseline: **334 passed, one expected skip**. Ruff lint/format and **100% diff coverage** pass, all exit 0. Production mutations: **21 killed, five survived**.

No other scope, waiver, logging, or test-weakening objections. No CI or `.claude/` changes; protected tests remain unchanged. Worktree clean. V4/V5 remain post-merge checks.

[Detailed evidence and exit codes](/var/folders/dt/plwyfk5x12b0zz73dbjj1dvh0000gn/T/flowbench-review-5i3p4tm5/review-evidence.md).
