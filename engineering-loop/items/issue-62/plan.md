# Plan — flowbench #62 (size S, docs-only)

Worktrees: engine `../flowbench--onboarding-docs` (branch
`loop/issue-62-onboarding-docs` off `origin/master`); scenarios
`../flowbench-scenarios--onboarding-docs` (off `origin/main`) for item artifacts + ledger.

- **T1 — `docs/onboarding.md`** (AC1). Sections: what you need (Python 3.12+/uv, Node ≥22,
  tmux, a Claude subscription, an omnigent checkout); topology (venv client vs server/host
  daemon vs tmux + `claude` CLI, one paragraph + the run path); readiness check
  (`GET /v1/hosts`, the driver's own gate at `runner/driver.py:_resolve_claude_host`; no
  health endpoint); the `ANTHROPIC_API_KEY`-unset rule and why (subscription billing, the
  guard in `OmnigentDriver.start`, the quota failure signature); patch status (no patch on
  current omnigent, what the historical one was, how to check the constant/anchor if a
  2nd+-turn injection ever fails again); run dirs (`$RUNS`, never in the repo); first
  offline run; first live run (`--extra live`, `caffeinate -i`, lid open, watcher);
  where to read next (GLOSSARY, runner.md, decisions, `$SCENARIOS/docs/knowledge/omnigent.md`).
- **T2 — decision record** `docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md`
  (AC2). Decision; Why (bundle injection = the comparability mechanism, normalized
  transcript, typed session status + human-prompt signals for the watchdog, one seam for
  many harnesses, vanilla product under test on subscription billing, resumable session);
  Alternatives with the probed evidence (herdr; per-CLI drivers / `claude -p`); Costs
  accepted (private-API reach-ins, pin/version split, server+tmux ops surface);
  Reconsider triggers; Consequences (the `AgentDriver` seam is the swap point).
- **T3 — links + run-dir pointer** (AC3, AC4): README/CLAUDE.md link both new docs;
  the `compare --run-base` examples become `$RUNS/<scenario>`; CLAUDE.md's run-dir line
  states the convention (sibling of the checkout that launches the run — the scenarios
  checkout for live runs; `$RUNS` concrete only in `CLAUDE.local.md`); "needs omnigent
  patched" becomes "needs a live omnigent server (see docs/onboarding.md)". Code defaults
  and the test that asserts them are correct as they stand — do not touch them.
- **T4 — delete the dead patch script** (AC5): `git rm scripts/patch_omnigent.py`; amend
  `docs/roadmap/epics/E02-runtime-robustness.md:109-112` (patch clause done; correct only the
  wrong half — the venv copy IS what the driver imports, but its bridge never runs — and state
  that S02.5 stays open for the public-API bullets and the pin bump),
  `docs/roadmap/target-architecture.md:62` and `:134` (note the fix is in the published
  0.12.0), `docs/roadmap/current-state.md:79`, `docs/roadmap/ROADMAP.md:62`.
- **T5 — gates** (AC6): `uv run pytest -q`, `uv run ruff check .`, the two `rg` checks;
  record in `gates.md`.

Tests: docs-only, so the acceptance checks ARE the tests — AC4 is a read of the two pointer lines plus `rg` for `$RUNS`, AC5 an `rg` assertion,
AC1–AC3 file/link existence, AC6 the existing suite (proving no import referenced the
deleted script).

Global constraints (verbatim from the spec): every install/patch claim must be verified
against the local install; no concrete per-developer path in a tracked file; the driven
omnigent is a source checkout at 0.13.0.dev0 while the `live` extra pins client 0.1.1 —
do not paper over that split.


## Gate order (recorded, not hidden)

Gate 1+2 ran against the branch after T1–T4 were already written (the reviewer flagged this).
Its objections were therefore applied to the prose as well as to this spec/plan: the patch
story now names the real reason the script was mis-aimed, the bridge path is given per version,
the "client side only" wording is corrected to "flowbench imports only the client side", the
install section gains a runnable command and the real repo URL (README's placeholder link
fixed), the S02.5 correction touches only the wrong half, and the ACs are mechanical.
