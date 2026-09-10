Whole-branch adversarial review (gate 3). You are the approver; the generator
cannot approve its own work. Verdict: the literal token APPROVE or REVISE on its
own line, then numbered objections marked blocking / non-blocking.

Branch: `loop/issue-s022-driver-split` in /Users/zarz/dev/agents/flowbench--s022,
based on `origin/master` 1324132. Read the diff yourself:
`git -C /Users/zarz/dev/agents/flowbench--s022 diff origin/master...HEAD`
(and `--stat`, and `git log origin/master..HEAD`).

Contract it must satisfy:
- Spec (approved):  /Users/zarz/dev/xebia/flowbench-scenarios--s022/.claude/engineering-loop/items/flowbench-80/spec.md
- Decisions:        .../items/flowbench-80/decisions.md
- Plan (approved):  .../items/flowbench-80/plan.md
- Gate record:      .../items/flowbench-80/gates.md
- Epic:             /Users/zarz/dev/agents/flowbench--s022/docs/roadmap/epics/E02-runtime-robustness.md § S02.2

The story's contract is **behavior-preserving relocation**. Attack that claim:

1. **Is anything semantically different from `origin/master`?** Compare
   `git show origin/master:src/flowbench/runner/driver.py` against
   `src/flowbench/driver/{base,bundle,omnigent}.py` and
   `git show origin/master:src/flowbench/runner/loop.py` against
   `src/flowbench/loop.py`, function by function. Report ANY changed
   expression, dropped comment that carried a reason, altered default,
   reordered call, or changed exception surface. A useful technique: transcribe
   a moved function back into the old file's shape and diff it.
2. **The `self.` -> `spec.` conversion in `driver/bundle.py`.** One instance was
   already caught (`spec.render_config()`). Check every remaining attribute
   access in the three functions against the old methods.
3. **The compat shims.** Would any real caller break? Enumerate what the engine,
   its tests, and the sibling repo
   (/Users/zarz/dev/xebia/flowbench-scenarios--s022) import from the old paths
   and check each. Is `tests/test_compat_reexports.py` actually able to fail?
4. **The new tests.** `tests/driver/test_bundle.py` goldens,
   `test_functions_need_only_the_bundlespec_fields`, and the `start()` tests in
   `tests/driver/test_omnigent.py`. Are any of them tautological, or asserting
   the fake rather than the code? Do the `start()` fakes misrepresent what
   omnigent actually does (check the installed `omnigent_client` if useful)?
5. **Scope.** Anything here that belongs to S02.3/S02.4/S02.5/S02.6, or any
   policy change smuggled in. Also: is the epic amendment in
   `docs/roadmap/epics/E02-runtime-robustness.md` (the "~350 lines" line)
   honest and correctly reasoned, or is it rationalizing a shortfall?
6. **Docs.** Do `docs/design/runner.md`, `docs/roadmap/current-state.md`,
   `docs/roadmap/target-architecture.md`, `CLAUDE.md` and the omnigent decision
   record now describe the code that exists? Any stale path left anywhere in
   the repo?
7. Anything else that should block a merge.

Under 500 words.
