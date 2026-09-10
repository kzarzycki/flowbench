Spec re-review, attempt 2. You reviewed this spec once and returned REVISE with
six objections. Verify the fixes; do not re-litigate what you already approved,
but do report any NEW defect the fixes introduced. Verdict must be the literal
token APPROVE or REVISE on its own line, then numbered objections.

Your attempt-1 verdict:
  /Users/zarz/dev/xebia/flowbench-scenarios--s022/.claude/engineering-loop/items/flowbench-80/spec-review-1.md

Revised artifacts:
  .../items/flowbench-80/spec.md      (AC1, AC2, AC4, AC4b, AC7, AC12 rewritten)
  .../items/flowbench-80/decisions.md (new #10, #11, #12; old #10 replaced)
  .../items/flowbench-80/plan.md      (new T0 golden capture, T7 V4 run before merge)

Code, for checking claims:
  /Users/zarz/dev/agents/flowbench--s022/src/flowbench/ and tests/
  /Users/zarz/dev/agents/flowbench--s022/docs/roadmap/verification.md
  /Users/zarz/dev/xebia/flowbench-scenarios--s022/scripts/codex_review.py, tests/test_codex_review.py

Check, one per prior objection:
1. V4 — is AC12 + decisions #10 an adequate resolution, and is the T7 command
   form actually able to exercise the branch's engine rather than the git pin?
2. AC4 — is the compat symbol table now complete? Re-derive it yourself from a
   grep of both repos and say what is still missing, if anything.
3. AC4b + decisions #11 — does the grep actually catch a missed monkeypatch
   target? Consider what happens if a target is left pointing at the shim.
4. AC1/AC2/AC7 — are these now machine-checkable and fail-on-broken? In
   particular: does the AC2 SimpleNamespace test really fail if a bundle
   function reads an attribute outside BundleSpec, and do the AC7 goldens
   actually pin the bytes?
5. The line-64 citation.
6. Anything the revision broke, and any remaining gap between the spec and the
   epic's S02.2.

Keep the reply under 500 words.
