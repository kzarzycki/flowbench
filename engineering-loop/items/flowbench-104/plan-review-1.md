reviewer: claude-code subagent gate2-review-104 (Fable, fresh context)

REVISE
1. Ordering: suite red after Task 1/2 (factories, scoring.py, testing.py still pass artifact_name / 3-arg TurnResult). → reordered: Task A additive (loop probe, find_artifact, run_case wiring, fakes, factories) then Task B strip.
2. `test_run_case_artifact_none_omits_artifact_keys` goes red with `n_run_factories` writing plan.md. → test builds local fakes without `run_dir`.
3. `test_run_case_artifact_none_forwards_zero_grace` asserts the reversed behaviour. → replaced by `test_run_case_builds_probe_from_flow_dir`; traceability row added.
4. Unnamed red tests (`test_capture_session_returns_the_run_fields`, `test_omni_factories_artifact_name_and_git_init`, `test_make_simulator_omni_...`, `test_make_flow_driver_omni_maps_flow_config`, `test_types.py:35`). → each listed with its edit under Task A/B.
