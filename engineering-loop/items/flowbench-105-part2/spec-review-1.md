1. [src/flowbench/driver/omnigent.py:260](/Users/zarz/dev/agents/flowbench--s025p2/src/flowbench/driver/omnigent.py:260): **Criterion (b) fails.** SDK 0.2.0’s `_sessions.py:696` delegates to `_errors.py:66`, which accepts statuses below 400. Reproduced with the installed SDK: HTTP 301/302/307 carrying valid Session JSON with empty labels makes `_resend_allowed()` return **True**; the previous raw implementation returns **False**. Preserve strict non-2xx rejection and add regression coverage before migrating this read.

Other checks pass: scope/A1–A3, unchanged pre-existing assertions, SDK label mapping, and concurrent-region boundaries. Reverting the import makes the start test fail as required (exit 1).

Verification: driver tests **73 passed**, full suite **298 passed, 1 skipped**, Ruff and contract probe exit **0**. Live A4 excluded.

REVISE
