# Vision — what flowbench is being built toward

The long-term goal: **a benchmark that can take any engineering flow — vanilla Claude
Code, superpowers, OpenSpec, Xebia's ACE, a proprietary migration chain like ADF's
X-Lens → X-Port — point it at a realistic engineering case, and produce a comparison you
can trust.** "Trust" decomposes into the pillars below; each pillar is a milestone track
in `ROADMAP.md`.

## The bet

Agent-workflow vendors (and internal teams) make claims: "spec-driven beats vibe-coding",
"our skills chain migrates warehouses", "this workflow asks before it assumes". Nobody can
check these claims without driving *real interactive agent sessions* through *whole
workflows* on *cases with hidden requirements and objective oracles* — which is exactly
the runtime flowbench already has and eval frameworks don't. Everything in this roadmap
grows that core; nothing replaces it.

## Pillars

### 1. Runtime (exists; hardening in M0–M2)

Drive a real coding agent through a multi-turn task via omnigent: session lifecycle,
simulator-mediated conversation, DONE detection, artifact capture. One module knows
omnigent exists; everything else is data in, files out.

### 2. Scenario & case format (M3)

A case is a folder of plain files (task, simulator persona, hidden knowledge, judge
rubric, flow list). A scenario adds scoring code over captured sessions and workspaces.
Scenario families the format must carry:

- **Greenfield coding** (todo_app): vague prompt, hidden shape, black-box acceptance.
- **Planning** (swe_planning): compare plans, comparative judge.
- **Migration** (dwh_migration, private): fixture legacy codebase in, ported codebase
  out, scored against a golden oracle computed on the *real source system* — plus
  infra lifecycle (spin up/tear down the source DB) around the run.

### 3. Flow portability & the flow catalog (M4)

Today a flow is a bundle assembled from whatever is on the host (superpowers resolved
from the local plugin cache). Target: a **flow definition is a versioned, resolvable,
self-contained artifact** — "superpowers@4.2.1", "openspec@0.9", "ace@<ref>",
"adf-chain@<ref>" — that any flowbench install can fetch, pin, and run identically.
Requirements the known flows impose:

- **Bundle flows** (superpowers): skills/commands/config copied into the bundle;
  resolution from a git ref or plugin release, not a host path.
- **CLI-backed flows** (OpenSpec, the ADF repos): the workflow's skills shell out to a
  real binary/library, so a flow also declares provisioning — packages installed and
  binaries asserted in the workspace before the session starts, recorded in the
  manifest.
- **Chained flows** (ADF X-Lens → X-Port): multiple stages, each potentially its own
  session, with artifact handoff between stages and per-stage scoring checkpoints (score
  the analysis manifest before the port consumes it).
- **Remote-service flows** (ACE): the tool under test is a hosted service reached
  through MCP servers in the bundle. Runs are non-hermetic — server-side prompts and
  models are invisible and unpinnable — so the flow definition carries declared
  comparability caveats that reports must render. Only the MCP-reachable surface is
  benchmarkable within the bundle model (`research/flow-requirements.md`).
- **Cross-harness flows**: the driver already knows `codex-native`; the comparability
  rules for cross-harness comparisons must be written down (same case, same simulator,
  same judge — different harness is itself the variable).

### 4. Reproducibility (M5)

A run must be re-runnable and a result attributable. Every run records a **manifest**:
engine git SHA, omnigent + harness CLI versions, resolved model IDs (not aliases),
reasoning effort, flow version + bundle content hash (store the exact bundle tar in the
run dir), case content hash, frozen seed hashes. `flowbench rerun <run-id>` reconstructs
a run from its manifest and reports what could not be pinned (the model behind a
subscription alias drifts; say so instead of pretending).

### 5. Sandboxing & isolation (M6)

Benchmarked agents currently run with `permission_mode: bypassPermissions`,
`sandbox: none`, in the caller's process environment. Fine for trusted first-party flows;
not fine for third-party flows, and a reproducibility hole (host state leaks into runs).
Target: **declared isolation levels per run** —

- L0 *trusted* (today): host env, guarded only by allowed-tools flags.
- L1 *confined*: workspace-scoped file access, no host `~/.claude`, scrubbed env
  (no host secrets), still native processes.
- L2 *containerized*: the agent session runs in a container image pinned in the
  manifest; host is untouchable; network default-off with an explicit allowlist (the
  migration scenario needs Databricks/Teradata endpoints — allowlisted, logged).

What's reachable per level depends on omnigent's `os_env`/sandbox support — the epic
starts with an investigation story, and gaps go to the omnigent upstream wishlist.

### 6. Auditing (M7)

The captured session already holds every tool call; auditing makes it a first-class,
queryable record. Per run: an **action log** (`actions.jsonl`: commands executed, files
written, subagents spawned, network touched — normalized from session items), a **cost
ledger** (tokens and wall-clock per role: flow, simulator, judge), and **integrity
hashes** of transcripts and artifacts in `run.json`, so a scorecard can be traced to
untampered evidence. Auditing also covers the *claims vs evidence* discipline that
already exists in pockets (the judge is told to distrust narration; the migration
harness verifies claims against the real source system) — generalized as a scoring
input: what the agent *said* it did vs what the action log shows.

### 7. Statistics (M8) and Reporting (M9)

N-trial runs with failure isolation and parallelism; winner counts with spread; judge
position-bias checks; cost columns; regression tracking across flow versions. Reports
stay pure readers over run dirs. Full proposals: `proposals/P01-statistics-and-scale.md`,
`proposals/P02-reporting-dx.md`.

## What stays true at every step

The locked decisions in `README.md`: bundle-only flow variation, one execution model,
DIY over frameworks until a written trigger fires, plain-file seams, subscription-only
billing, outputs outside the repo. A pillar that seems to require breaking one of these
gets a decision record first, not a quiet exception.
