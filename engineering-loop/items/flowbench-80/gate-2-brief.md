Plan review (gate 2). Verdict: the literal token APPROVE or REVISE on its own
line, then numbered objections marked blocking / non-blocking.

Inputs (absolute paths; read them yourself):
- Plan:      /Users/zarz/dev/xebia/flowbench-scenarios--s022/.claude/engineering-loop/items/flowbench-80/plan.md
- Spec:      .../items/flowbench-80/spec.md   (APPROVED)
- Decisions: .../items/flowbench-80/decisions.md
- Goldens:   .../items/flowbench-80/gates.md  (§ T0, already captured)
- Code:      /Users/zarz/dev/agents/flowbench--s022/src/flowbench/ and tests/
  (note: T1 is already committed — `to_jsonable` now lives in
  `src/flowbench/transcript.py`; `runner/driver.py` is 605 lines)

Check:
1. **Traceability both ways.** Every AC in spec.md reaches at least one task
   that would actually fail if the AC were violated; every task step traces to
   an AC. Name any AC with no real check and any step that is scope the spec
   does not authorize.
2. **Ordering and green-at-every-step.** T1..T7 as written — does the suite
   stay green after each task? Flag any step that leaves the tree importable
   but the suite red, or that must be merged with its neighbour.
3. **Completeness of the mechanical edits.** Derive the list yourself:
   every file in both repos that imports from `flowbench.runner.driver` or
   `flowbench.runner.loop`, and every string monkeypatch target naming those
   modules. Compare against T2 step 3, T2 step 4 and T3. Report anything the
   plan will miss — especially a site whose omission leaves the suite GREEN
   but the code untested or unpatched.
4. **The shim design.** `runner/driver.py` re-exports `_PAGE` from
   `flowbench.driver.omnigent` while `runner/loop.py` re-exports `_is_done`.
   Does the plan's shim survive `ruff` (F401) and the AC1 ast check
   simultaneously? Is there an import cycle in
   `driver/__init__.py` -> `omnigent.py` -> `base.py` / `bundle.py`?
5. **T0's goldens.** Are the captured values in gates.md § T0 sufficient for
   the golden assertions T2 must add, or is a variant missing that the moved
   code could break?
6. **T7 / V4.** Is the command form correct for this repo (check
   `scenarios/swe_planning/run.py` and `watch.py` for the real flags), and is
   running it pre-merge from a scenarios worktree with `--with-editable`
   actually going to exercise the engine branch?

Under 500 words.
