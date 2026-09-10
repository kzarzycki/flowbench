Adversarial spec review. You are the approver; the generator cannot approve its
own work. Verdict must be the literal token APPROVE or REVISE on its own line,
followed by numbered objections (blocking vs non-blocking).

Story under review: flowbench E02 S02.2 "Driver split" — a behavior-preserving
relocation of `src/flowbench/runner/driver.py` into a `src/flowbench/driver/`
package, plus moving `runner/loop.py` to `flowbench/loop.py`, with compat
re-exports at the old paths.

Inputs (read them yourself; absolute paths):
- Spec:      /Users/zarz/dev/xebia/flowbench-scenarios--s022/.claude/engineering-loop/items/flowbench-80/spec.md
- Decisions: /Users/zarz/dev/xebia/flowbench-scenarios--s022/.claude/engineering-loop/items/flowbench-80/decisions.md
- Epic:      /Users/zarz/dev/agents/flowbench--s022/docs/roadmap/epics/E02-runtime-robustness.md  (section S02.2)
- Target arch: /Users/zarz/dev/agents/flowbench--s022/docs/roadmap/target-architecture.md
- Verification procedures: /Users/zarz/dev/agents/flowbench--s022/docs/roadmap/verification.md
- Code under change: /Users/zarz/dev/agents/flowbench--s022/src/flowbench/runner/driver.py,
  src/flowbench/runner/loop.py, src/flowbench/transcript.py, src/flowbench/testing.py,
  src/flowbench/run.py, src/flowbench/model.py, tests/runner/
- Design doc: /Users/zarz/dev/agents/flowbench--s022/docs/design/runner.md

Check specifically:
1. Does the spec cover everything the epic's S02.2 asks for, and nothing the
   epic assigns to another story? Cite the epic line for any gap.
2. Is every acceptance criterion machine-checkable and does it actually fail if
   the change is wrong? Name any AC that would pass on a broken implementation.
3. Every line/symbol citation in spec.md and decisions.md: verify it against the
   real file. Report any wrong line number, wrong count, or claim about the code
   that is false.
4. Decision #3 claims the epic's "~350 lines" target is unreachable
   behavior-preservingly and amends the epic instead. Is the arithmetic right,
   and is amending the roadmap the correct call rather than widening the split?
   Say so plainly if you disagree.
5. Is the compat surface complete? Enumerate every symbol any caller (this repo,
   its tests, and the sibling scenarios repo) imports from
   `flowbench.runner.driver` / `flowbench.runner.loop` today, and confirm the
   spec's AC4 covers them.
6. Any behavior change hiding inside a "pure move" — import-time side effects,
   `monkeypatch.setattr` targets that would silently stop patching the code
   under test, module-level state, or a name that changes identity.

Keep the reply under 500 words.
