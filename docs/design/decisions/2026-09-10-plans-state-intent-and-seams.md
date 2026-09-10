# Decision: plans state intent and seams

**Date:** 2026-09-10. **Status:** accepted. Applies to every implementation plan written for the
engineering loop's gate-2 review.

## Decision

1. **A plan names the behaviour that must hold**, per task, in prose an implementer can check
   against a suite.
2. **It names the test cases to add and the seam each one drives** — which function, class or
   file the test reaches through — so the review can argue about coverage and about seams.
3. **It states the signatures that are themselves the decision** (a public function's parameters,
   a class's attribute names, an error's exact text, a file layout). Those are the interface, so
   they belong in the plan verbatim.
4. **It does not embed test bodies or fixture wiring.** No `def test_...` blocks, no fake-object
   plumbing, no assertion text. Choosing the arrangement is the implementer's job with the code in
   front of them; gate 3 reviews the result against a suite that runs.

## Why

Test bodies on paper cannot be reviewed for the only thing that matters about them — whether they
pass. This story's first plan ran to **3170 lines, 2302 of them inside code fences**, and every
objection across three plan reviews questioned whether a fixture written on paper would work: an
argument that is not settleable on paper, and that a running suite settles at gate 3 in seconds.

The cost is not only the wasted review. A plan whose fences are stale on contact teaches the
implementer to skim it, and the behavioural intent — the part only the plan can carry — gets
skimmed with it.

## What stays locked

- Gate 2 still reviews the plan, and a task with no stated behaviour or no named tests is
  incomplete.
- Signatures, error texts and layouts stay verbatim in the plan: they are decisions, not
  arrangement.
- Test-first still holds at implementation time (write the test, watch it fail, then implement).
