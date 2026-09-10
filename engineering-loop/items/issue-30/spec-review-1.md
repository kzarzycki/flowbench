# Spec review 1 — issue #30 (codex-native flow with bundled superpowers skills)

## Verdict: REVISE

Two objections block approval: (1) the codex-native flow dies at terminal launch because
flowbench's driver unconditionally sends claude-only CLI flags that omnigent passes through
to the codex binary — verified, codex aborts with exit 2 — and the spec declares the only
fix ("flowbench changes") out of scope while AC 6 requires the flow to complete a live run;
(2) flow B's `model: opus` contradicts the issue's explicit "(existing model)" and rests on
an unanswered user question (D7). Everything else checks out.

## What was verified (all claims read in source)

**D1 skills-filter semantics — TRUE, all four legs:**
- codex `"none"` stages nothing including bundle skills:
  `omnigent/inner/codex_executor.py` — `select_codex_skill_dirs` returns `{}` on `"none"`
  (L446-447); `_populate_codex_skills` returns before even creating `skills/` (L506-507).
- codex list stages named skills, bundle shadowing host: `codex_skill_sources` (L398-421)
  orders `<bundle>/skills` before `~/.codex/skills`; list case selects names present in
  sources (L468-469). Shared with codex-native via `populate_codex_skills_from_bundle`,
  called at `runner/app.py:3635` — exact line, verified.
- claude-native `"none"` emits `--setting-sources ""` (host suppressed) while bundle skills
  ride `--plugin-dir`: `omnigent/inner/bundle_skills.py::claude_native_skill_args` L107-113.
- claude-native list does NOT suppress host — only `"none"` emits `--setting-sources`;
  docstring L85-89 states list is treated like `"all"` for host sources. So `skills: none`
  for flow B and a name list for flow A is the correct pairing.

**flowbench seams — TRUE:** `Flow.skill_dirs` (`runner/flow.py:30`),
`OmnigentDriver.skill_dirs` (`runner/driver.py:264`), `_build_bundle` copytrees each entry
into `<bundle>/skills/<name>/` (driver.py:311-312). `render_config` emits
`skills: [a, b, c]` for lists (L292-296). `_resolve_claude_host` keys on `claude-native`
regardless of flow harness (driver.py:410-412) — D5 accurate, reasonable to defer.

**Path resolution — TRUE:** `cases/todo_app/flows.yaml` + `../../skills/<name>` →
`scenarios/swe_planning/skills/<name>`. Vendor location and relative entries line up.

**D3 self-containment — conclusion holds, verification claim overstated:** all
`references/` and `scripts/` live in-dir for the three skills. Content grep (which a
"file listing" would not catch) found one upward reference:
`brainstorming/scripts/server.cjs:209` reads `../../../package.json` /
`.codex-plugin/plugin.json` — but it is a version-display lookup inside try/catch with a
fallback, benign when vendored. `writing-plans` cross-references to
`superpowers:subagent-driven-development` / `executing-plans` are prose in the generated
plan template, inert in a planning-only flow. `using-superpowers` references are in-dir.

**Repo state — matches spec's deltas:** `helpers.py::load_flows` is a bare yaml load
(L28-29, no skill_dirs today); `run.py::make_flow_driver_omni` (L291-304) passes no
skill_dirs; judge/simulator are claude-native `skills: none` (run.py L307-347), untouched
by the spec. Existing tests that pin flow names (`tests/test_swe_planning_flows.py`)
target `feature_flag_service` only, and `tests/test_swe_planning_run.py` uses inline flow
fixtures — renaming todo_app flows to `codex`/`claude` breaks nothing. `scenario.CASES`
not listing `todo_app` is a pre-existing quirk, out of scope.

**Scope vs issue:** all five issue ACs are represented (vendored skills + provenance,
skill_dirs schema/threading + tests, flows.yaml matchup, offline suite, live validation).
Spec's extra "lacks SKILL.md → error" check is a small, justified extension (bundle
staging requires SKILL.md). No scope loss. `gpt-5.5` matches the issue's probe note.

## Objections

1. **(blocking) Codex-native terminal launch aborts on flowbench's hardcoded claude
   launch args — spec is silent and rules out the only fix.**
   `OmnigentDriver._create_metadata` (flowbench `runner/driver.py:329-344`) sends
   `terminal_launch_args: ["--disallowedTools", "AskUserQuestion", "--permission-mode",
   "acceptEdits", "--allowedTools", ...]` for EVERY session, harness-independent.
   Omnigent's codex-native launch passes these straight to the codex binary:
   `runner/app.py:3761` (`codex_args=tuple(launch_config.terminal_launch_args or ())`) →
   `codex_native_app_server.py:1822-1824` (passthrough; only `-a`/`-s` variants are
   stripped). Verified empirically: `codex --disallowedTools AskUserQuestion --version`
   → `error: unexpected argument '--disallowedTools' found`, exit 2. Flow A therefore
   cannot boot, making AC 6 unattainable while the spec says "Out of scope: flowbench
   changes." The spec must either (a) bring a harness-aware `_create_metadata` (or
   equivalent) flowbench change into scope, or (b) cite verified evidence the codex path
   drops these args (it does not, per the lines above). Corollary: flow A's
   permission stance is also unspecified — the claude flags are exactly what delivers
   "zero permission prompts" for flow B; the codex equivalent (approval mode / bypass /
   policy hook) needs a stated mechanism, since AC 6 requires zero prompts on both flows.

2. **(blocking) Flow B `model: opus` contradicts the issue.** The issue fixes flow B as
   "`harness: claude-native` (existing model)" — the existing model is `haiku`. D7
   changes it to `opus` on the strength of an AskUserQuestion the user never answered
   (60s timeout) plus the flows.yaml comment "opus for real runs". That is a product
   judgment the issue as filed does not support (review rule d). Either revert flow B to
   the existing model or obtain an actual user answer and record it; a one-line change
   either way, but the spec cannot pin `opus` (spec §4 and AC 4) on a timeout.

3. **(minor) AC header is self-contradictory.** "Acceptance criteria (each checkable from
   diff/tests alone)" — AC 6 is a live run checked from run artifacts, not diff/tests.
   Mirror the issue's framing: split AC 6 out as the live-validation gate (loop Phase
   9.5) rather than claiming diff/tests-only checkability for it.

4. **(minor) D3's verification method is overstated.** "verified by file listing" cannot
   establish content self-containment; a content grep finds the `server.cjs`
   `../../..` manifest lookup (benign, see above). Reword D3 to cite the content check
   and note the benign upward reference, so the next reader doesn't re-litigate it.

5. **(nit) Failure-point wording drift.** Spec §2 says the missing-dir `ValueError` fires
   in `load_flows` "at load time, before any session spawns"; D6 says "at driver
   construction". Align on load time (the spec's version — it is the better behavior).

## Notes (non-blocking)

- The risk section correctly flags codex-native turn-detection and
  `set_reasoning_effort` applicability (D4) as live-validation checks; after objection 1
  is resolved, those remain the right residual risks.
- Flow rename `superpowers`/`plain` → `codex`/`claude` is internally consistent (judge
  A/B is order-based; run.json uses names dynamically; no test or case doc couples to the
  old todo_app names).
