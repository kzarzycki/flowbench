# Spec: codex-native flow with bundled (vendored) superpowers skills

Issue: #30. Size M. Decision 2a pre-made with the user (see issue body).

## Problem

The benchmark cannot compare the superpowers planning workflow on Codex vs Claude Code:
codex-native sessions get no superpowers (superpowers 6.1.1 dropped `hooks-codex.json`;
omnigent's codex skill staging never scans the plugin cache — verified live and in
omnigent source, evidence in issue #30). Both existing flows also depend on host machine
config (`skills: all`), against the project direction of explicitly-configured runs.

## Change

Both todo_app flows load the same vendored superpowers skills from the flow bundle;
neither depends on host skills. Flow A runs codex-native, flow B claude-native.

### 1. Vendored skills — `scenarios/swe_planning/skills/`

Verbatim copies of `using-superpowers/`, `brainstorming/`, `writing-plans/` from
superpowers 6.1.1 (`~/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/`),
each dir complete (SKILL.md + references/ + scripts/ as shipped). Beside them a
`VERSION.md` recording upstream plugin, version, copy date, and the rule that the copy
is never hand-edited (re-vendor to change). Planning-only scope: execution-phase skills
(subagent-driven-development, executing-plans, TDD) are NOT vendored — the flow's append
forbids implementation, so they are unreachable (decisions.md D2/D3).

### 2. `helpers.py::load_flows` — skill_dirs resolution

`load_flows(path)` additionally resolves an optional per-flow `skill_dirs: [<relpath>, ...]`:
each entry resolves relative to the flows.yaml parent directory to an absolute `Path`;
an entry whose dir does not exist (or lacks `SKILL.md`) raises `ValueError` naming the
offending path — failing at load time, before any session spawns. Flows without
`skill_dirs` are unchanged.

### 3. `run.py::make_flow_driver_omni` — threading

Pass `skill_dirs=flow.get("skill_dirs", [])` into `OmnigentDriver` (field exists;
flowbench `_build_bundle` copies each into `<bundle>/skills/<name>/`; omnigent stages
them per harness: `--plugin-dir` on claude-native, `$CODEX_HOME/skills/` symlinks on
codex-native via `populate_codex_skills_from_bundle`, `runner/app.py:3635`).

### 4. flowbench: harness-aware terminal launch args (paired change, sibling repo)

`OmnigentDriver._create_metadata` (flowbench `driver.py:324`) unconditionally sends
claude-only CLI flags (`--disallowedTools`, `--permission-mode`, `--allowedTools`) as
`terminal_launch_args`; omnigent's codex-native launch passes them verbatim to the
`codex` binary, which rejects them (exit 2, verified) — a codex-native flow cannot
boot without this change. Fix: gate the args on `self.harness`:

- `claude-native` → existing flags, byte-identical (no behavior change for any
  current flow).
- `codex-native` → `["--ask-for-approval", "never", "--sandbox", "workspace-write"]`
  (codex's unattended zero-prompt stance with sandbox guardrails — the codex
  equivalent of what the claude flags exist for).
- any other harness → `[]` (no foreign flags; safe default).

Unit tests in flowbench cover all three cases. Merge order per loop.md sibling-repo
rule: flowbench PR (base `master`) merges first, then this repo's PR; live
validation covers both together.

### 5. `cases/todo_app/flows.yaml` — the matchup

- Flow A `codex`: `harness: codex-native`, `model: gpt-5.5`, no `reasoning_effort`
  (host codex default `high`; see decisions.md D4),
  `skills: [using-superpowers, brainstorming, writing-plans]` (list required: `"none"`
  stages nothing on codex, bundle included — decisions.md D1).
- Flow B `claude`: `harness: claude-native`, `model: haiku` and
  `reasoning_effort: medium` — both unchanged from the existing superpowers flow, per
  the issue ("existing model"; D7). Model pairing for publishable runs is a run-time
  content decision (issue #27 territory), not this issue. `skills: none` (host
  suppressed via `--setting-sources ""`; bundle skills still load — D1).
- Both: identical `skill_dirs: [../../skills/using-superpowers, ../../skills/brainstorming,
  ../../skills/writing-plans]`, identical prepend (`Use /brainstorming …`) and append.
- Flow names are the harness (`codex`, `claude`) since skills are now identical.
  The old `superpowers`/`plain` pair is replaced by this matchup in todo_app;
  `feature_flag_service/flows.yaml` is untouched.

Judge/simulator sessions stay claude-native `skills: none` — untouched.

## Out of scope

- flowbench changes beyond §4. Known wart recorded: `_resolve_claude_host` keys on
  `claude-native` regardless of flow harness (works here, single host has both
  harnesses — D5).
- Sandboxing (`os_env: caller_process`, `sandbox: none`) — separate axis, unchanged.
- feature_flag_service case, judge/simulator config, report/aggregation machinery.

## Acceptance criteria (1–6 checkable from diff/tests alone; 7 is the loop's
Phase 9.5 live-validation gate)

1. `scenarios/swe_planning/skills/{using-superpowers,brainstorming,writing-plans}/SKILL.md`
   all exist; `scenarios/swe_planning/skills/VERSION.md` pins upstream version 6.1.1.
2. `load_flows` resolves relative `skill_dirs` to absolute paths against the flows.yaml
   dir — unit test asserts absolute paths; unit test asserts `ValueError` (message names
   the path) for a missing dir.
3. `make_flow_driver_omni` passes `skill_dirs` through to `OmnigentDriver.skill_dirs` —
   unit test on the constructed driver.
4. `cases/todo_app/flows.yaml`: flow A `harness: codex-native` + `model: gpt-5.5` +
   `skills` as a 3-name list; flow B `harness: claude-native` + `model: haiku` +
   `skills: none`; both flows' `skill_dirs` lists equal; neither flow has `skills: all`;
   prepend/append identical across flows.
5. flowbench (sibling repo): `_create_metadata` launch args gated on harness —
   claude-native byte-identical to today's flags, codex-native =
   `["--ask-for-approval", "never", "--sandbox", "workspace-write"]` (long form, matching
   §4), any other harness = `[]`; one unit test per case.
6. Offline suites green in both repos (`uv run pytest -q`).
7. Live validation (loop Phase 9.5): a real run where each flow's transcript/session
   shows the superpowers skills visible or invoked, zero permission prompts, per-flow
   `plan.md` and run-level `run.json` land.

## Risks (watched at live validation, not blocking merge)

- Driver turn-detection against codex-native sessions is unproven (status/settle
  semantics differ from claude-native; codex-native has been observed flipping to
  `failed` after emitting a final message in other contexts).
- Whether `set_reasoning_effort` applies to codex-native — D4; checked live.
