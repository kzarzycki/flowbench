# S-item spec — flowbench #62: onboarding docs + omnigent-as-meta-harness decision record

## Problem

Two things a new contributor cannot learn from the code:
1. **How to get a live run working at all** — omnigent is not on PyPI in the version we
   actually drive, the server/host/tmux topology is invisible, and the
   `ANTHROPIC_API_KEY`-unset rule looks like a quirk instead of a billing invariant. Today
   this is tribal knowledge split across `$SCENARIOS/docs/knowledge/omnigent.md` and the
   ledger.
2. **Why omnigent is the meta-harness** at all. The 2026-09-03 flow decision record
   explicitly defers this ("the meta-harness … is a separate decision to be recorded in M2").

Third, smaller: CLAUDE.md's run-dir pointer and its `compare` example read as
`../flowbench-runs/` *relative to the engine checkout* — where nothing ever lands. The
default is `<launching checkout>/../flowbench-runs/` (`scenarios/coding_workflow/run.py`
`_REPO_ROOT.parent / "flowbench-runs"`, asserted by
`tests/scenarios/todo_app/test_todo_run.py`), and live runs are launched from the scenarios
checkout. The convention is right; the tracked pointer is misleading and must not carry a
per-developer path (08-20 path policy: `$VAR` tracked, real path in untracked
`CLAUDE.local.md`).

## Chosen fix

- `docs/onboarding.md`: install/topology, the readiness check, the key rule and why, the
  patch story (see below), run-dir convention, first offline + first live run, pointers.
- `docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md`: omnigent vs herdr vs
  driving each CLI directly, with the reconsider-triggers and the swap seam.
- README + CLAUDE.md link both; the run-dir pointer becomes `$RUNS`.

## Verified facts (probed, not remembered)

- The **server** is an editable install of an omnigent source checkout
  (`uv tool` receipt: `editable = <checkout>`), version 0.13.0.dev0; the `live` extra
  installs **omnigent 0.1.1 from PyPI into the venv**. That distribution is complete (it
  ships its own bridge module), but flowbench imports only its client side
  (`omnigent_client`, `omnigent.host.daemon_launch`). Runner and bridge processes are
  `~/.local/share/uv/tools/omnigent/bin/python3 -m omnigent.runner._entry` /
  `-m omnigent.claude_native_bridge`, so the **pane-scanning bridge that runs is the
  server's**, never the venv copy.
- **omnigent is public and published**: `github.com/omnigent-ai/omnigent` (HTTP 200), PyPI
  latest 0.12.0. So onboarding can give a real install command; the machine here drives an
  editable checkout of a fork, which is the development path, not the only path.
- **The `_PROMPT_SCAN_TAIL_LINES` patch is obsolete, and a *published* release carries the
  fix.** The 0.12.0 wheel (unpacked and grepped) still has the flat module
  `omnigent/claude_native_bridge.py` but already anchors on `_is_box_rule` (5 uses), with the
  5-line tail only as the no-rule fallback; the 0.13.0.dev0 checkout has the same logic at
  `omnigent/harnesses/claude_native/bridge.py`. So the bridge path is **version-specific** and
  onboarding must give both. `scripts/patch_omnigent.py` was mis-aimed either way: its glob
  targets a non-editable uv-tool `site-packages` (this machine's is editable, so no such
  tree), and its fallback imports whichever `omnigent` is importable — the venv client copy,
  whose bridge never runs. (Its "could not locate" message reproduces only where no omnigent
  is importable, e.g. a fresh worktree.) No `.flowbench-bak` exists anywhere, so no copy was
  ever patched, and todo-app-001…004 drove multi-turn injection unpatched. E02 S02.5
  pre-authorized deletion "when a release carries it" — 0.12.0 does.
- **Readiness check** = the one the driver makes: `GET /v1/hosts` → a host with
  `status: online` and `configured_harnesses["claude-native"]` truthy (probed: true here).
  There is no version/health endpoint — unknown paths return the SPA with HTTP 200, so
  `/healthz` is a false-positive probe.
- **herdr** (probed `herdr --help`, `herdr agent`, `herdr api schema`): socket API, 22
  agent kinds, `agent start … -- <agent-args>`, `agent prompt --wait --until STATUS`,
  `agent read --source visible|recent|detection`, statuses
  `idle|working|blocked|done|unknown`. No per-session skill/MCP bundle injection and no
  normalized transcript — its API carries pane text plus a reference to the harness's own
  session file (`AgentSessionInfo{source,agent,kind,value}`); and control is bound to a
  herdr-managed pane (`HERDR_ENV=1`).

## Acceptance criteria (checkable from the diff)

1. `docs/onboarding.md` exists with exactly these H2 headings, in order: "1. What you
   need" (incl. an "Installing omnigent" subsection with a runnable install command),
   "2. The topology…", "3. Is it ready?…", "4. `ANTHROPIC_API_KEY` must be UNSET",
   "5. Do I need to patch omnigent?…", "6. Where runs land", "7. Your first live run",
   "8. Where to read next".
2. `docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md` exists with
   Decision / Why / Alternatives (herdr, direct CLI) / Reconsider triggers / Consequences.
3. README and CLAUDE.md each link both new docs.
4. `rg -F -- '../flowbench-runs/coding_workflow' README.md CLAUDE.md docs/roadmap/verification.md`
   has no match, and each of those three files contains `$RUNS/`; CLAUDE.md's run-dir bullet
   states the `<launching checkout>/../flowbench-runs/<scenario>/` default. `git diff
   origin/master...HEAD -- scenarios/ src/ tests/` is empty (code defaults and the test
   asserting them untouched). The concrete path stays out of tracked files; the doc text says
   it belongs in `CLAUDE.local.md` — creating that file is not part of this item.
5. `git ls-files scripts/patch_omnigent.py` is empty; `rg -i 'omnigent patched'` has no match
   in `README.md` or `CLAUDE.md`; `rg -l patch_omnigent` matches only this allowlist:
   `docs/onboarding.md`, `docs/roadmap/ROADMAP.md`, `docs/roadmap/current-state.md`,
   `docs/roadmap/target-architecture.md`, `docs/roadmap/epics/E02-runtime-robustness.md`; and
   `rg -l patch_omnigent .github .pre-commit-config.yaml src tests pyproject.toml` has no
   match.
6. `uv run pytest -q` green; `uv run ruff check .` clean.

## Why safe

Docs + deletion of a script that provably cannot run against the installed omnigent
layout; no runtime surface → Phase 9.5 live validation is skipped by rule.
