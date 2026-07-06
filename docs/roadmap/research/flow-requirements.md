# Flow requirements research

What the target flows actually need from the engine, from reading each flow's source
(2026-07-06). This feeds the E04 (flow portability) and E06 (sandboxing) specs. Engine
docs keep this requirement-level; proprietary flow *definitions* live in the private
scenarios repo.

## ADF chain (X-Lens → X-Port) — migration flows

Two Claude Code skills repos (`adf-xlens-skills`, `adf-xport-skills`, both `dev` branch,
**no git tags** — pin by commit SHA). Each is skills + a deterministic Python library;
LLM turns are the reasoning steps between deterministic prepare/finalize phases.

Shape: X-Lens (`/xlens-all <repo> <run_dir>`) analyzes a legacy warehouse repo into a
judgement-free fact catalog (`catalog_*.jsonl`), then judgment layers (severity findings,
lineage graph, wave plan, planner xlsx). X-Port stages those catalogs into a slot layout
(`data_objects/`, `data_lineage/`, `codebase/`, …, plus `migration_context.json`) and
runs design → cross-check → coverage → mapping → refactor stages, each a
`prepare → LLM turn → finalize` cycle writing `<skill>/<step>_findings.json`, ending in
rewritten target-dialect code.

Requirements this imposes on the engine:

1. **Bundles must carry more than skills + MCPs.** Both repos ship `.claude/skills/`,
   `.claude/agents/` (stored subagents the orchestrator skills spawn), and `.claude/hooks/`
   (a PostToolUse SQL-validation hook that makes the agent self-heal invalid writes).
   Today's bundle builder copies skills and MCP yamls only — agents and hooks are
   invisible to a flow definition. (E04)
2. **Workspace provisioning.** The chain needs its Python libs installed (`x_lens`,
   `xport` — console scripts on PATH) and external binaries (`gitleaks` ≥ 8.24.3 is a
   hard STOP for the secrets skill). A flow definition needs a declared-prerequisites /
   setup step that runs before the session starts, recorded in the manifest. (E04, E05)
3. **Human gates become simulator knowledge.** X-Port's orchestrator pauses at six
   mandatory sign-off gates (inventory, structure, orphans, coverage, mapping, rewrites)
   and X-Lens asks for the migration target — via `AskUserQuestion`, which flowbench
   disables, so the questions arrive as plain text to the simulator. The case's
   `knowledge.md` must carry the gate-answer policy (target platform, output flavor,
   approve/inspect rules), and turn/deadline budgets must fit a run with many gates. (M4
   scenario work, not engine code)
4. **Stage boundaries and handoff.** X-Lens → X-Port handoff is explicitly the
   consumer's job (stage/symlink catalogs into the slot layout). A chained flow needs:
   ordered stages, a handoff step between them (scripted or agent-performed — decide in
   the E04 spec), and per-stage scoring checkpoints. Natural checkpoints with objective
   contracts: X-Lens's `catalog_*.jsonl` + per-skill `*_coverage.json` ledgers
   (invariant: scope == processed + skipped + failed), X-Port's per-stage
   `*_findings.json`, and the final rewritten code (row-level golden diff downstream).
   (E04)
5. **Reproducibility hooks.** The deterministic core (sqlglot/regex extraction,
   prepare/finalize) is re-runnable; nondeterminism is confined to the LLM turns and
   optional user-gated rescue/resolve agents — a benchmark run should decline those (or
   pre-supply overrides) and record that choice. `model: "no-llm"` in any findings file
   means a fallback skeleton fired — score it as a stage failure, never as output. (E05,
   scenario scorers)
6. **Sandboxing compatibility: good.** Neither repo needs network at runtime (both
   generate text; X-Port never connects to Databricks/Teradata). L1/L2 isolation is
   viable for the whole chain; only the *scoring* side (golden diff vs the real source
   system) needs credentials, and that runs in the harness, not the agent session. (E06)

## ACE — remote-service flow

ACE is a hosted multi-tenant SaaS (SPA + FastAPI + Celery workers + three separate AI
runtimes), not an installable bundle. It walks a project through SDLC phases
(requirements → architecture → UX → development → IaC → DevOps → AiOps) with HITL
approval gates, artifacts stored server-side. Two integration shapes, only one of which
fits the engine's model:

- **Path A — ACE-as-MCP (fits).** ACE exposes three remote MCP servers (requirements,
  architecture, UX; HTTP JSON-RPC with an ACE-issued API key). A flow = vanilla Claude
  Code + a bundle of those three MCP configs (+ ACE's recommended context-setting
  prompt as the per-case overlay). This benchmarks ACE's *design/planning* generation —
  scored as documents, a natural companion to the planning scenario — not its code
  production. Generation tools are async server-side tasks; the agent polls via the MCP's
  own status tools, so the session loop is unaffected.
- **Path B — ACE's code engine (does not fit).** Scaffolding/code runs inside ACE's own
  server-side Claude Code wrapper behind REST+WS (submit job, poll session, approve,
  download zip). Driving it means being an HTTP client of a remote service — no omnigent
  session, no workspace, a different driver class entirely. Not scheduled; if ever
  wanted, it needs its own decision record (it breaks the bundle model and hermeticity).

Requirements this imposes on the engine:

1. **Credentialed MCP configs.** The bundle must carry an MCP config whose API key is
   injected at run time from the environment, never committed; the manifest records
   *which* credential was used, not its value. (E04, E06)
2. **Comparability caveats as first-class flow metadata.** An ACE run is non-hermetic:
   server-side prompts/models are invisible, unpinnable, and continuously deployed. The
   flow definition must declare this and reports must render it (a comparison of
   superpowers vs ACE states that the ACE side is a black box that may have changed
   since the last run). Reproducibility levers are weak: record run dates, tenant
   config snapshot where readable, request-pinned model params where the API accepts
   them — or negotiate a pinned deployment. (E04 caveats, E05 manifest)
3. **Network allowlist entry.** L1/L2 isolation must permit exactly the ACE MCP
   endpoints for this flow — the first real consumer of the per-case egress allowlist.
   (E06)
4. **HITL gates.** Design-path MCP generation is gate-light; if a scenario ever touches
   gated ACE surfaces, gate answers become simulator knowledge, as with the ADF chain.

## OpenSpec — spec-driven flow

Fission-AI/OpenSpec (MIT, npm `@fission-ai/openspec`, Node ≥ 20.19, semver releases with
matching git tags — cleanly pinnable). Change-proposal-centric workflow: explore →
propose (`openspec/changes/<name>/{proposal.md, specs/, design.md, tasks.md}`) → apply
(implements tasks, flipping checkboxes) → sync (deltas merged into `openspec/specs/`) →
archive (change folder moved to `changes/archive/`).

Requirements this imposes on the engine:

1. **CLI runtime dependency, not a pure skills bundle.** `openspec init --tools claude
   --profile core` writes `.claude/skills/openspec-*/SKILL.md` (or legacy
   `.claude/commands/opsx/*`) into the repo — but those files *shell out to the
   `openspec` binary* at runtime (`status --json`, `instructions --json`, `validate`,
   `archive`). Vendoring the skill files isn't enough; the flow needs the npm package
   installed and on PATH — the same provisioning requirement class as ADF's Python libs
   and gitleas binary. (E04 provisioning)
2. **Headless-safe.** The propose→apply human review gate is a documentation convention,
   not a technical block; `init` and `archive` prompts are avoidable with flags
   (`--tools/--profile`, `--yes`). No blockers to a simulator-mediated run.
3. **Clean objective scoring surface.** Did-the-workflow-fire checks mirror the
   superpowers `skills_invoked` pattern but on disk: `openspec/changes/<name>/` artifact
   presence, `tasks.md` checkbox state vs source diffs, archive layout, and
   `openspec validate --all --json` for structured spec-completeness — an objective
   scorer that needs no judge. (S04.5 scorers)
4. **Setup-time network only.** The npm install (and possibly `init`) needs registry
   access once, at provisioning; the session itself runs offline — compatible with
   default-off network at L2 if provisioning happens before lockdown. (E06)
