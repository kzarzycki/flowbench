# issue-30 decisions

Q&A resolved from issue + code (loop rule 3); sources cited.

**D1 — `skills:` filter value per harness.** codex-native: `skills: [using-superpowers, brainstorming, writing-plans]` — an explicit name list; `"none"` stages nothing including bundle skills (`codex_executor.py::_populate_codex_skills` returns early on `"none"`; `select_codex_skill_dirs` list case selects named skills, bundle source before `~/.codex/skills/` so bundle shadows host; codex-native shares this via `populate_codex_skills_from_bundle`, called at `runner/app.py:3635`). claude-native: `skills: none` — emits `--setting-sources ""` which suppresses host skills while bundle skills load via `--plugin-dir` (`bundle_skills.py::claude_native_skill_args`); a list is treated like `"all"` for host sources on the native CLI (no per-name allowlist flag), so `none` is the only value that gives bundle-only.

**D2 — which skills to vendor.** `using-superpowers`, `brainstorming`, `writing-plans` only. The flow is planning-only (append forbids implementation), so execution-phase skills (`subagent-driven-development`, `executing-plans`, `test-driven-development`) are never invoked. YAGNI.

**D3 — vendor verbatim, no edits.** All three skill dirs are file-complete in-dir (references/ and scripts/ ship inside each dir). A content grep found one relative path leaving the dir: brainstorming's `scripts/server.cjs` reads a version string from files three levels up (`package.json` / `.codex-plugin/plugin.json`) — benign (only affects a UI footer of the optional visual companion, which the unattended flow never starts). Cross-references to non-vendored skills (`superpowers:systematic-debugging` etc.) are soft prose names — inert when absent. `brainstorming` terminally invokes `writing-plans`, which is vendored. Verbatim copy keeps provenance auditable; upstream version 6.1.1 recorded beside the copy.

**D4 — codex model id.** `gpt-5.5` — the resolved model of a live codex-native probe session (conv_e5fda84f, 2026-07-03). `reasoning_effort` for the codex flow: omitted in flows.yaml (host codex config.toml default `model_reasoning_effort = "high"`); whether `set_reasoning_effort` applies to codex-native sessions is unverified — live validation checks the session's resolved settings.

**D5 — `_resolve_claude_host` keys on `claude-native` regardless of flow harness** (`flowbench driver.py:410`). Works on this deployment (single host, both harnesses configured). Out of scope: flowbench change, separate issue if it ever bites.

**D6 — `skill_dirs` resolution.** flows.yaml paths resolve relative to the case dir (consistent with how case files are loaded); missing dir fails fast with a clear error at flow-load time (`load_flows`), before any session spawns (acceptance criterion 2).

**D7 — flow model pairing.** The issue fixes both: flow A `gpt-5.5` (named in the issue), flow B keeps the existing flow's `haiku` + `reasoning_effort: medium` (the issue says "existing model"). A flagship pairing for publishable runs is a run-time content decision tracked by issue #27, not this issue. (A gate-1 reviewer correctly rejected an earlier `opus` choice here as product judgment the issue doesn't support.)
