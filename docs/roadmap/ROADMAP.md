# Roadmap — milestones, epics, stories

The destination is `vision.md` (pillars); this file is the ordered plan. Three phases:

- **Foundation (M0–M3)** — one execution model, robust runtime, case format, CLI.
  Everything later stands on this; do not reorder past it.
- **Capabilities (M4–M7)** — flow portability, reproducibility, sandboxing, auditing.
  These make third-party and proprietary flows (OpenSpec, ACE, ADF chains) benchmarkable
  and the results defensible.
- **Scale (M8–M9)** — statistics and reporting over many trials, flows, and versions.

Sequencing rules:

- One story = one engineering-loop iteration (branch → spec → tests → PR → merge →
  live validation where the runtime is touched → journal). Target diff ≤ ~300 lines.
- Verification: stories cite the shared procedures in `verification.md` (V1 offline
  suite, V2 downstream suite, V4/V5 live runs, V6–V8 sweeps/gates) plus story-specific
  assertions.
- Epics E00–E04 have full specs in `epics/`; later epics get their spec promoted from
  this file (plus `proposals/` and `research/`) before execution starts.
- A milestone closes with a green live validation run and a ledger entry.
- Flow-requirements research (ACE, ADF chain, OpenSpec) lives in
  `research/flow-requirements.md` and feeds M4/M6 specs.

---

## Phase: Foundation

### M0 — Guardrails (`epics/E00-guardrails.md`)

Make the repo safe for autonomous weak-model development first.

- S00.1 Vocabulary/docstring sweep (`arm`, "An flow", `OMNIGENT_PROBE_MODEL`).
- S00.2 CI hardening: coverage + `diff-cover` gate, suite runtime budget.
- S00.3 Regression tests for every live-incident comment in `driver.py`/`loop.py`.
- S00.4 Docs wiring: CLAUDE.md pointers, refresh `docs/design/runner.md`.

### M1 — One execution model (`epics/E01-one-execution-model.md`)

Executes the recorded 2026-07-02 decision: `run_case`, everything omnigent, Inspect and
`claude -p` removed.

- S01.1 Lift the generic runtime out of swe_planning into the engine
  (`run.py`, `SessionModel`, `judge.py`, `transcript.py`, `flowspec.py`, `testing.py`).
- S01.2 Paired scenarios PR: swe_planning consumes the engine, deletes local copies.
- S01.3 Port todo_app to `run_case` (case files + scenario-local scorers).
- S01.4 Remove Inspect + `subscription_model.py`; wheel ships `flowbench` only;
  extra `spike` → `live`.
- S01.5 Milestone live validation: todo_app + swe_planning runs, parity notes.

### M2 — Runtime robustness (`epics/E02-runtime-robustness.md`)

- S02.1 `types.py`: `TurnStatus` enum, typed `TurnResult`, simulator Protocol.
- S02.2 Driver split: `driver/bundle.py`, transcript out; driver = lifecycle only.
- S02.3 One retry policy at the driver (absorb the issue-#39 fresh-text rule);
  documented policy table; single wall-clock budget per send (nested-timeout bug).
- S02.3b Loop hygiene: keep harness nudges out of the simulator's relayed context;
  per-turn child-busy state (both audit-confirmed bugs).
- S02.4 Artifact probe out of the driver (kill `artifact_name="__none__"`).
- S02.5 Omnigent public-API migration + upstream the tmux-scan patch; delete
  `scripts/patch_omnigent.py` when released.
- S02.6 Error taxonomy: narrow the broad `except Exception` sites.

### M3 — Case format v1 and a real CLI (`epics/E03-case-format-and-cli.md`)

- S03.1 Flow schema v1 (union of dataclass + downstream yaml shape; validating loader).
- S03.2 Case format v1 (documented loader; scenario-authoring guide moves engine-side).
- S03.3 `flowbench run` / `flowbench watch`; per-scenario `__main__`s deleted.
- S03.4 `run.json`/`scorecard.json` schema v1 (`schema_version`, reader rules).
- S03.5 Generic compare (metric discovery replaces the hardcoded todo_app table).

---

## Phase: Capabilities

### M4 — Flow portability & the flow catalog (`epics/E04-flow-portability.md`)

Goal: a flow is a versioned, resolvable artifact — not "whatever the host has installed".
Proof: the same comparison (plain vs superpowers vs openspec) runs identically on a
second machine; the ADF chain runs under the engine's chain orchestrator. Requirements
source: `research/flow-requirements.md`.

- S04.1 Flow sources + resolver (git/path/plugin ref → pinned sha in the manifest).
- S04.2 Bundle v2: carry `.claude/agents` and hooks, not just skills + MCPs (the ADF
  repos ship all three; investigate omnigent bundle support first).
- S04.3 Workspace provisioning: declared python deps + required binaries (gitleaks
  et al.), executed before the session, recorded in the manifest.
- S04.4 Flow catalog: named definitions in `flows/`; cases reference + overlay.
- S04.5 OpenSpec flow as the portability proof (three-way vs plain and superpowers).
- S04.6 Chain orchestrator: staged sessions, scripted handoff, per-stage scoring,
  SKIPPED semantics (mechanism in engine; the ADF chain definition stays private).
- S04.7 ACE flow via its remote MCP servers (design/planning surface only; env-injected
  API key; declared non-hermeticity caveats rendered in reports). Its server-side code
  engine is out of scope without a new decision record.
- S04.8 Cross-harness comparability rules + a codex-native smoke through `run_case`.

### M5 — Reproducibility (E05, spec to write)

Goal: `flowbench rerun <run-id>` reconstructs a run from its manifest; anything
unpinnable is reported, not hidden.

- S05.1 Run manifest v1 in `run.json`: engine git SHA, omnigent + harness CLI versions,
  flow source pins (from S04.1) + bundle content hash, case content hash, seed hashes,
  isolation level (from M6), reasoning efforts.
- S05.2 Resolved-model capture: record the session's actual model ID next to the alias
  ("opus" → the dated model id), per role (flow/sim/judge). Subscription aliases drift;
  the manifest says what actually ran.
- S05.3 Bundle archival: store each session's exact `agent.tar.gz` in the run dir,
  content-addressed; capture already keeps `session_id`/`conversation_url`.
- S05.4 `flowbench rerun <run-id>`: rebuild flows from pins + archived bundles, re-run,
  emit a pin-drift report (what differs from the original manifest).
- S05.5 Case/seed freezing as an engine convention: content-hash verification command
  (the migration scenario's frozen seeds become the reference implementation).

### M6 — Sandboxing & isolation (E06, spec to write; starts with an investigation story)

Goal: declared isolation levels; a comparison states the level all its flows ran at.
Today everything is L0 (host env, `bypassPermissions`, `sandbox: none`).

- S06.1 Investigation (output = decision record in `docs/design/`): omnigent `os_env` /
  sandbox capabilities, Claude Code sandboxing options, what L1/L2 can be built from
  them; gaps → upstream wishlist.
- S06.2 L1 *confined*: scrubbed environment (env allowlist, no host secrets), host
  `~/.claude` never visible (today that's per-flow `skills: none`; make it a run-level
  guarantee), file access scoped to the workspace; a guard test proves a canary host
  secret is unreachable.
- S06.3 Isolation level in the flow/case schema, the run manifest, and reports;
  invariant: one comparison = one level.
- S06.4 L2 *containerized* (upstream-dependent): pinned container image in the manifest;
  network default-off with a case-declared allowlist (migration cases need their
  DB endpoints); egress log per run.
- S06.5 Simulator/judge confinement: they never needed shell/file tools — restrict them
  first (prompt-only mitigation today; bundle-level tool restriction when omnigent
  supports it).

### M7 — Auditing (E07, spec to write)

Goal: every scorecard traces to an untampered, queryable record of what the agent did.

- S07.1 Action log: normalize captured session items into `actions.jsonl` per session
  (commands run, files written, subagents spawned, skills invoked, network fetches) —
  the existing `skills_invoked` scraper generalized into `flowbench/audit.py`.
- S07.2 Cost ledger: per-role tokens (flow/sim/judge), turns, wall-clock in `run.json`
  (flow stats exist; sim/judge are blind spots today).
- S07.3 Integrity: sha256 of transcripts, artifacts, and `session.json` recorded in
  `run.json` at capture time.
- S07.4 Claims-vs-evidence scoring input: scorers receive (claims extracted from
  narration, action log, artifacts) so "said vs did" is a reusable metric — generalizing
  the migration harness's claim verification and the todo judge's narration-distrust
  instruction.
- S07.5 `flowbench audit <run-id>`: render the action log + cost ledger + integrity
  check as a report.

---

## Phase: Scale

### M8 — Statistics (`proposals/P01-statistics-and-scale.md`)

Failure-isolated parallel trials; spread (not just means); position-bias reporting; cost
columns; `flowbench history` regression tracking across flow versions. Framework
reconsider-trigger checkpoint lives here.

### M9 — Reporting & DX (`proposals/P02-reporting-dx.md`)

Per-run/aggregate report v2 with session links; HTML export; scenario-author quickstart,
template case, fixture-capture helper; optional Inspect log exporter (only when pulled).

---

## Explicit non-goals

- No web dashboard, database, or run-registry service — plain files until a
  reconsider-trigger fires.
- No prompt-level flow steering — locked decision; a flow that cannot run un-steered is
  declared with a comparability caveat, not accommodated with harness hacks.
- No harness zoo: `claude-native` + `codex-native` until a real comparison demands more.
