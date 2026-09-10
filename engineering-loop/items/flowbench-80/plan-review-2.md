REVISE

1. blocking: Fix 2 is not actually in the revised plan. `plan.md` T2 still says `build_bundle` is converted “bodies verbatim apart from `self.` → `spec.`”, which preserves the bad transcription as `spec.render_config()`. The plan does not name `test_functions_need_only_the_bundlespec_fields` or require `build_bundle()` to call module-level `render_config(spec)`. `gates.md` and the current implementation show the fix exists, but the plan still encodes the defect.
