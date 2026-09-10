APPROVE

No remaining objections.

- Both Task 4 fixes verified: argv root resolves the real `run.json`; named runner wait preserves exit **7** despite watcher exit **0**.
- Checkout, merge-SHA pin checks, CLI flags, watcher interfaces, exit-status and artifact assertions match the code.
- Criterion→task→test traceability holds. T2→T1→T3 keeps BLE activation last.
- Planned tests catch real bugs: shell probes reproduced container-message retries and swallowed foreign `RuntimeError`s.

Verification: **303 passed, 1 skipped**. Suite, lint, formatting, CLI help, corrected-signature and behavior probes exited **0**. Mutable-default control exited **1/B006**, expected.

No files changed or live runs launched; live validation remains after merge.
