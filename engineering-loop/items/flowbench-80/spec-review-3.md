APPROVE

1. No remaining defect in the two targeted fixes. AC7 now catches the prior blocker for `render_config`, `build_bundle`, and `session_metadata` content behavior.

2. Broken implementations that could still slip past: tar header/order metadata changes, gzip stream byte changes, and bundle behavior outside the single fixed skill/MCP fixture shape. Those are outside the now-stated invariant.

3. Line citation is fixed: the spec now consistently says line 64.
