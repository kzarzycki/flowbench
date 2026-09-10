REVISE

Three test gaps violate the required mutation protection. Each mutation survived the full suite: **326 passed, 1 skipped, exit 0**.

- [test_omnigent.py:1565](/Users/zarz/dev/agents/flowbench--s026/tests/driver/test_omnigent.py:1565): AC2’s missing `labels` key is never tested—the fake always supplies it. Changing `_resend_allowed` to `resp.json()["labels"]` survives, despite raising `KeyError` on `{}`. Add that response case.
- [test_scorers.py:311](/Users/zarz/dev/agents/flowbench--s026/tests/scenarios/todo_app/test_scorers.py:311): widening `collect_code` to `except Exception` survives pytest. Add a test requiring an unexpected `RuntimeError` to propagate.
- [test_scorers.py:329](/Users/zarz/dev/agents/flowbench--s026/tests/scenarios/todo_app/test_scorers.py:329): removing the exception from the DEBUG log survives. `"broken.py"` comes from the separate path argument. Assert exception-specific text.

Other checks passed: allowed driver regions, unchanged swallow tests, truthful waivers, exception-bearing DEBUG logs, and no CI/gate/`.claude/` or documentation changes.

Baseline pytest, Ruff lint/format, and diff-cover all exited **0**; diff coverage **100%**. Initial uv attempts exited **2**; reruns used `/tmp` cache. Of **17 mutations**, **14 triggered test failures (exit 1)**; three survived. All mutations restored; worktree clean.
