# Spec review 1 — REVISE (reviewer: fresh-context Fable subagent)

Verified: codebase claims true; D1 diagnosis correct; verdict-tally
reinterpretation faithful to #3+#10; decisions D2-D7 grounded.

Objections:
1. AC4 ("all pre-existing tests pass unmodified") contradicts D1 — the
   environmental failure makes AC4 unmeetable in this worktree, or forces
   editing a test AC4 forbids. Rephrase: no new failures relative to
   baseline; D1 exempt.
2. CLI under-specified: main() prints result["meta"], but run_case_n
   (n>1) returns {"run_root","aggregate","trials"} — KeyError after a
   full live run. Return shape is mode-dependent and never stated as a
   contract; no AC exercises the --n>1 CLI path. Normalize the shape or
   specify main() per mode, and extend AC2/AC5 with an offline test.
