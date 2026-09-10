REVISE

Independent criterion → task → test mapping:

| Criterion | Task | Verification | Finding |
|---|---|---|---|
| AC1 | T3 | Ruff with BLE; waiver inspection | Covered |
| AC2: transport/status/JSON failures; RuntimeError propagation | T1 | Existing transport/status tests; new JSON/reraise tests | Covered |
| AC2: malformed labels | T1 | Resend matrix; context-token matrix | Context tests omit `[]`, `""`, `0`, `7` |
| AC2: null error message; invalid/overflow tokens | T1 | New malformed-body tests | Return values covered; prescribed exception handling is not |
| AC2: legitimate retries | T1 | Existing empty-map/undelivered tests; new missing/null tests | Covered |
| AC3 | T1 | 503 response carrying token label | Covered |
| AC4 | T2 | Existing ValueError/OSError tests; new RuntimeError and unreadable-directory tests | Covered |
| AC5 | T1 + T2 | Seven caplog tests | Assertions insufficiently specified |
| AC6 | T1 | Existing close/pane swallow tests unchanged | Covered |
| V1 | T3 | Full pytest suite; diff-cover threshold | Gate specified |

1. **AC2 lacks required tests—automatic reject.** T1’s `_context_tokens` matrix omits four explicitly required malformed-label values. Add `[]`, `""`, `0`, `7` in `tests/driver/test_omnigent.py`. Require DEBUG logging for malformed inputs too: return-value assertions alone cannot distinguish swallowed shape errors from incorrectly treating malformed labels as absent.

2. **T1 contradicts the specified catch boundary.** In `src/flowbench/driver/omnigent.py`, apply None-only label normalization to **both** methods. The plan currently leaves `_context_tokens`’s `or {}` intact. For `_resend_allowed`, remove `msg … or ""` and keep message membership evaluation inside `try`: null must enter the logged fallback; a truthy numeric message currently would raise `TypeError` outside the proposed catch. Add that regression case.

3. **T1 cannot finish green as written.** The local `_FakeResp` in [test_capture_session_includes_context_tokens](/Users/zarz/dev/agents/flowbench--s026/tests/driver/test_omnigent.py:850) lacks `raise_for_status()`. The planned addition therefore produces a caught `AttributeError`, returning `None` instead of `42072`. Update both local context-token response doubles in T1, preserving the successful-token assertion.

4. **T2 is not executable precisely as specified.** Declare full implementation paths: `src/flowbench/transcript.py`, `src/flowbench/watch.py`, and `scenarios/coding_workflow/cases/todo_app/scorers.py`. Explicitly initialize `log = logging.getLogger(__name__)` in each; watch and scorers currently have no `log`, so their prescribed snippets fail Ruff with undefined names. Replace the nonexistent `test_run_watch_run_sessions_*` reference with the actual test name.

5. **AC5 tests could accept incorrect logging.** Setting caplog’s threshold to DEBUG also captures INFO/WARNING. Specify assertions on `record.levelno == logging.DEBUG`, exact module logger name, and exception details for every site—including `scenarios.coding_workflow.cases.todo_app.scorers`.

Three tasks suit size S; enabling BLE last is sound. These corrections fit within the existing tasks.
