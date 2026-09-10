Plan re-review, attempt 2 — verify the fixes to your three attempt-1 objections.
Verdict: the literal token APPROVE or REVISE on its own line, then numbered
objections. Do not re-review what you accepted.

Your attempt-1 verdict:
  /Users/zarz/dev/xebia/flowbench-scenarios--s022/.claude/engineering-loop/items/flowbench-80/plan-review-1.md

Revised plan: .../items/flowbench-80/plan.md
Goldens:      .../items/flowbench-80/gates.md § T0 (recaptured)

Fixes:
1. (blocking) T0 now captures `session_metadata` for `claude-native`,
   `codex-native` AND an unknown harness, each with and without
   `session_title`/`project` — six variants. gates.md § T0 was regenerated from
   a detached worktree of origin/master.
2. (blocking) T2 now requires `test_functions_need_only_the_bundlespec_fields`
   and states that `build_bundle` must call the module-level `render_config(spec)`.
   Note: the defect you predicted was real — the implementation had transcribed
   `spec.render_config()`; it is fixed and that test fails on it.
3. (non-blocking) The plan's "Scenarios PR" section now names both downstream
   sites explicitly and says why a green engine suite hides them.

Is the plan now sound? Under 250 words.
