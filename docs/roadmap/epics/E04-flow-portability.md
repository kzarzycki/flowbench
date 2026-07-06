# E04 — Flow portability and the flow catalog

Milestone M4. Depends on E01 (run_case in engine) and E03 (flow/case schema v1).
Requirements source: `../research/flow-requirements.md`.

## Goal

A flow is a versioned, resolvable, self-contained definition — "superpowers@4.2.1",
"openspec@<ver>", "adf-chain@<sha>" — that any flowbench install runs identically. The
proof for single-session flows is a three-way plain vs superpowers vs openspec comparison
reproduced on a second machine; the proof for chains is the ADF X-Lens → X-Port chain
running under the engine's chain orchestrator (its definition living in the private repo).

## Design

### Flow definition v2

`flows.yaml` entries (and catalog files under `flows/`) grow:

```yaml
name: openspec
source:                      # NEW — where the bundle content comes from
  git: https://github.com/...      # or `path:` (local), or `plugin:` (release)
  ref: v0.9.0                      # tag/branch/sha; resolver records the exact sha
bundle:
  skills: [...]              # today: skill_dirs
  agents: [...]              # NEW — .claude/agents/ dirs (stored subagents)
  hooks: [...]               # NEW — hook configs + scripts
  mcp: [...]
provision:                   # NEW — workspace setup before the session starts
  python: ["x_lens @ git+...@<sha>"]   # installed into the run workspace env
  binaries: [{name: gitleaks, min_version: 8.24.3}]  # asserted present, else the
                                                     # run fails BEFORE spawning
prompts: {prepend: ..., append: ...}   # per-case overlay, as today
```

Comparability rule unchanged: bundle content and provisioning vary per flow; launch
flags and harness steering never do. Provisioning runs *before* the session and is
recorded in the manifest — it is workspace state, not steering.

### Chained flows

A flow may be a `chain:` of stages. Each stage: its own bundle/provision (usually
shared), a kickoff overlay, a done condition (done token via simulator, or expected
artifacts present), and declared output artifacts. Between stages an optional
**handoff** step runs — a scripted transformation of stage N outputs into stage N+1
inputs (the ADF catalog→slot staging). Handoff is deterministic harness code, not agent
work, so a chain comparison doesn't also measure "can the agent do file plumbing"
(unless a scenario wants exactly that, in which case it omits the handoff and the case
prompt covers it — both are legitimate, but they are different benchmarks).

Each stage is a scoring checkpoint: scorers can attach per stage (score the analysis
catalog before the port consumes it), and a failed stage fails forward honestly (later
stages are SKIPPED in the scorecard, not silently run on garbage).

## Stories

- S04.1 **Flow sources + resolver.** `source:` field; resolver fetches git/path/plugin,
  pins the sha into the run manifest, builds bundle inputs from the checkout. Replaces
  todo_app's newest-version-in-host-plugin-cache lookup. Verify: same flow file on a
  clean checkout produces an identical bundle hash.
- S04.2 **Bundle v2: agents + hooks.** Bundle builder carries `.claude/agents` and hook
  configs; verify with a fixture flow whose hook fires in a live session. (Blocked on
  checking what omnigent's bundle format supports for agents/hooks — if unsupported,
  this becomes an upstream story first.)
- S04.3 **Provisioning.** `provision:` executes in the run workspace (python deps into a
  per-run venv, binary presence asserted); failures abort before any session spawns;
  everything lands in the manifest. Verify: a flow requiring a missing binary fails with
  a named error and no session is created.
- S04.4 **Flow catalog.** `flows/` registry (open flows in-engine; private repos add
  their own); case `flows.yaml` references catalog entries + per-case overlays. Verify:
  swe_planning's two flows read from the catalog with unchanged behavior.
- S04.5 **OpenSpec flow** (portability proof): pin `@fission-ai/openspec@<ver>` via
  `provision:` (npm), scaffold with `openspec init --tools claude --profile core` as a
  provisioning step, bundle nothing (init writes the skills into the workspace). Score
  objectively on `openspec/changes/<name>/` artifacts, `tasks.md` checkbox state, and
  `openspec validate --all --json`. Run the three-way comparison on todo_app and
  swe_planning. Verify: V4 and V5 with the third flow — its scorecard column renders;
  a second machine reproduces the bundle/provision hashes.
- S04.6 **Chain orchestrator.** `chain:` support in flowspec + run.py: stages as
  sequential sessions over a workspace lineage, scripted handoff hook, per-stage
  scorecard sections, SKIPPED semantics. Verify: a two-stage fixture chain (fake
  drivers) end-to-end offline (V1); the ADF chain definition then lives downstream and
  its first live chain run is that repo's validation.
- S04.7 **ACE flow (MCP path).** Bundle = ACE's three remote MCP configs with the API
  key injected from env at run time (never stored); per-case overlay carries ACE's
  context-setting prompt. The flow definition declares its comparability caveats
  (non-hermetic remote service, unpinnable server-side prompts/models) and reports
  render them; the manifest records run date + whatever tenant/model params are
  readable. Scored as documents (planning-scenario style). ACE's server-side code
  engine (REST/WS job API) is explicitly out of scope — different driver class, needs
  its own decision record if ever wanted. Verify: a live ACE-flow run in the planning
  scenario produces a scorecard column with the caveat rendered.
- S04.8 **Cross-harness comparability rules** + one codex-native smoke through
  `run_case`.

## Non-goals

- A remote flow registry/marketplace — `flows/` dirs in git are the registry.
- Running proprietary flows in this repo's CI — the engine ships the mechanism and a
  fixture chain; real chains are validated downstream.

## Risks

- omnigent bundle format may not carry agents/hooks (S04.2 investigation-first).
- Provisioning is a sandboxing surface (arbitrary install steps); E06's isolation levels
  apply to provision steps too — record and confine them like agent actions.
