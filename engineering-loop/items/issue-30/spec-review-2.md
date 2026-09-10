# Spec review 2 — issue #30 (re-review after REVISE)

## Verdict: APPROVE

Both blocking objections from review 1 are genuinely resolved and verified against source
and the live codex CLI; the three minors are fixed. Two nit-level residuals noted below —
neither blocks; fix in flight or during implementation.

## Objection 1 (codex boot failure) — RESOLVED, fix verified correct and complete

New spec §4 brings the flowbench `_create_metadata` change into scope, exactly option (a)
from review 1. Verified end to end:

- **Root cause still as diagnosed:** flowbench `runner/driver.py:324-349` sends the claude
  flags unconditionally (`--disallowedTools AskUserQuestion`, `--permission-mode
  acceptEdits`, `--allowedTools ...`) for every session. Re-read in source.
- **Gating seam exists:** `OmnigentDriver.harness: str = "claude-native"` at
  `driver.py:262` — `self.harness` gating is implementable and unit-testable as specified.
- **Proposed codex flags are real:** `codex --help` lists `-a, --ask-for-approval
  <APPROVAL_POLICY>` and `-s, --sandbox <SANDBOX_MODE>` with `workspace-write` a listed
  value. Empirically: `codex -a never -s workspace-write --version` → exit 0
  (codex-cli 0.142.5). The combo is valid; `never` is an accepted policy.
- **Flags actually reach codex:** omnigent's launch path
  (`runner/app.py:3761` → `build_codex_remote_args`, `codex_native_app_server.py`) passes
  `terminal_launch_args` through verbatim when `bypass_sandbox=False`; `-a`/`-s` stripping
  only happens under `bypass_sandbox=True`, and the default is `False`
  (`runner/app.py:883`). Flowbench sends only `terminal_launch_args` in metadata, so the
  passthrough is verbatim. The launch is the root `codex` command (`--remote` attach),
  which carries both flags — not `codex exec` (which lacks `-a`).
- **Claude path byte-identical:** stated explicitly in §4 ("existing flags, byte-identical
  (no behavior change for any current flow)").
- **Cross-repo merge order stated:** "flowbench PR (base `master`) merges first, then this
  repo's PR; live validation covers both together" — matches loop.md's sibling-repo rule
  (loop.md:17-21).
- **Corollary (flow A permission stance) addressed:** `--ask-for-approval never` is the
  codex zero-prompt mechanism, `--sandbox workspace-write` the guardrail — the stated
  equivalent of what the claude flags deliver. The claude-side `--disallowedTools
  AskUserQuestion` deadlock concern has no codex analogue (`-a never` means codex never
  asks), so nothing is missing from the codex arg set.

## Objection 2 (flow B model) — RESOLVED

Spec §5 flow B: `model: haiku` + `reasoning_effort: medium`, "both unchanged from the
existing superpowers flow". Verified against the current
`cases/todo_app/flows.yaml` (superpowers flow: `model: haiku`, `reasoning_effort:
medium`) — exact match with the issue's "(existing model)". D7 is rewritten: it now
derives both models from the issue text and defers the publishable-run pairing to issue
#27. No product judgment, no reliance on the timed-out AskUserQuestion. AC 4 pins
`model: haiku` accordingly.

## Minors from review 1 — all RESOLVED

- **AC header (obj. 3):** now "1–6 checkable from diff/tests alone; 7 is the loop's
  Phase 9.5 live-validation gate". Fixed.
- **D3 wording (obj. 4):** now cites a content grep and names the benign
  `server.cjs` upward reference with the try/catch/footer rationale. Fixed (one path
  slip, see nit 2).
- **D6 vs §2 (obj. 5):** D6 now says "at flow-load time (`load_flows`), before any
  session spawns" — aligned on the load-time wording. Fixed.

## New-problem sweep

No contradictions, no unverifiable criteria, no scope creep: §4 is the minimum objection 1
requires (harness gate + three-case unit tests), "Out of scope" was updated to "flowbench
changes beyond §4", and nothing else moved. Two nits:

1. **(nit) AC 5 spells the codex flags in short form** (`-a never` / `-s
   workspace-write`) while §4's normative list uses long form
   (`["--ask-for-approval", "never", "--sandbox", "workspace-write"]`). Both are valid
   codex spellings, but a literal-assertion unit test can only match one. Make AC 5 quote
   §4's exact list so the criterion is unambiguous.
2. **(nit) D3's manifest path is slightly off:** `server.cjs` reads
   `../../../package.json` and `../../../.codex-plugin/plugin.json`, not
   `.claude-plugin/plugin.json`. Conclusion (benign version-footer lookup with fallback)
   unchanged; correct the citation.

## Residual live-validation note (non-blocking)

`--sandbox workspace-write` disables network access for codex-run commands by default —
an asymmetry vs the claude flow, which has no network restriction. Irrelevant for the
planning-only deliverable (plan.md), but if the codex session tries to fetch anything at
live validation, this is the first place to look. Belongs with the existing §Risks
watch-list (turn detection, `set_reasoning_effort`), which remains correct.
