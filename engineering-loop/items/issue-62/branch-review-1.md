# Gate 3 — whole-branch review, attempt 1 (opus, fresh context)

Verified all nine gate-1+2 objections as satisfied and independently re-checked the 0.12.0
wheel, the repo URL, the install subcommands and the scope. One new objection, fixed in the
follow-up commit: §2 named a version-specific bridge process (`-m omnigent.claude_native_bridge`)
as a general fact — the module moved on 0.13.0.dev0+, and the `ps` output that agreed with it
was pre-move leftovers. §2 is now version-neutral and the §5 table carries the process name
per version.

**VERDICT: REVISE** — one objection. All nine prior objections are satisfied; the fixes introduced one new false statement. Nothing was left unverified.

**Objection**

1. **`docs/onboarding.md:70-72` states a version-specific process name as a general fact, and contradicts the doc's own §5 table.** The text: "every runner and bridge process is `~/.local/share/uv/tools/omnigent/bin/python3 -m omnigent.runner._entry` / `-m omnigent.claude_native_bridge` (see for yourself: `ps ax | grep omnigent`)". On the install this repo drives (editable 0.13.0.dev0, `omnigent --version` → `0.13.0.dev0 (8627eb9f, built 2026-09-09T05:04:28Z)`), `omnigent.claude_native_bridge` no longer exists: `.../uv/tools/omnigent/bin/python3 -c "importlib.util.find_spec('omnigent.claude_native_bridge')"` → `None`; only a stale `omnigent/__pycache__/claude_native_bridge.cpython-313.pyc` remains in the checkout, and current code spawns `python -Im omnigent.harnesses.claude_native.bridge serve-mcp` (`omnigent/inner/_acp_omnigent_mcp.py:6`). The `-m omnigent.claude_native_bridge serve-mcp` processes visible in `ps` today (e.g. PID 10791) are leftovers from a pre-move build, so "see for yourself" disagrees with the doc on any freshly started session. `-m omnigent.runner._entry` is current and correct; the live harness process is `-m omnigent.runtime.harnesses._runner --harness claude-native --module omnigent.inner.claude_native_harness`. Fix: give the bridge module per version, or point at `docs/onboarding.md:141-144`, which already does — the same requirement objection 2 imposed on §5. §2's load-bearing point (the server's install, not the venv, drives the CLI) is true and unaffected.

**Objections 1-9 — satisfied**

1. `spec.md:49-53` replaces the false "cannot even find the file" with the real reason (non-editable glob; import fallback resolves the venv client copy); the prose says the same at `docs/onboarding.md:133-136`, and the "could not locate" caveat is scoped to a checkout with no importable omnigent (`spec.md:52-53`).
2. Bridge path now per version: `docs/onboarding.md:141-144` table (≤0.12.0 flat / 0.13.0.dev0+ `omnigent/harnesses/claude_native/bridge.py`), with the trigger credited to a published release at `docs/roadmap/target-architecture.md:135-138`, `docs/roadmap/epics/E02-runtime-robustness.md:109-111`, `spec.md:44-48`. Verified independently: PyPI latest is **0.12.0**; the 0.12.0 wheel ships flat `omnigent/claude_native_bridge.py` (no `omnigent/harnesses/`), `_is_box_rule` on 5 lines — `:3501` and `:4011` anchor prompt-ready and the permission-mode read on it, `_PROMPT_SCAN_TAIL_LINES = 5` (`:163`) used exactly once in logic, as the no-rule fallback at `:3502`. Source 0.13.0.dev0 has the same logic at `omnigent/harnesses/claude_native/bridge.py` (6 uses) and no flat module.
3. `docs/onboarding.md:65-69` now says the distribution is complete and "flowbench only ever imports the client side of it"; `spec.md:34-37` matches. Pins at `pyproject.toml:21-22`.
4. `docs/onboarding.md:27-38` names `github.com/omnigent-ai/omnigent` (HTTP 200, no redirect) and gives `uv tool install 'omnigent==0.12.0'` plus the editable path; `:43-46`/`:49` use `omnigent setup`, `start`, `--version`, `diagnose`, `stop` — all present in `omnigent --help`. README's placeholder link fixed (`README.md:9`, `:31`).
5. AC5 is mechanical with an enumerated allowlist (`spec.md:84-89`) and passes: `git ls-files scripts/patch_omnigent.py` empty, no `omnigent patched` in README/CLAUDE.md, `patch_omnigent` hits exactly the five allowlisted docs.
6. AC1 names the exact H2 headings (`spec.md:70-74`); `docs/onboarding.md`'s `## ` lines match one-for-one, in order.
7. The `CLAUDE.local.md` clause is dropped from the AC (`spec.md:83`), consistent with the worktree, where the file does not exist.
8. `plan.md:31-35` carries all five file:line anchors; `docs/roadmap/epics/E02-runtime-robustness.md:112-115` corrects only the import half, and `:113-114` states S02.5 stays open for the public-API bullets and the pin bump.
9. `plan.md:49-55` records that gates 1+2 ran after T1-T4 and that the objections were applied to the prose; commit `c8acb36` bears that out.

**Scope — clean.** `git diff --name-status origin/master...HEAD` touches 9 docs plus `D scripts/patch_omnigent.py`; `git diff origin/master...HEAD -- scenarios/ src/ tests/` is empty; no `patch_omnigent` reference in `.github/`, `.pre-commit-config.yaml`, `pyproject.toml`, `src/`, `tests/`.

**Other new claims — all true.** `RuntimeError` text matches `src/flowbench/runner/driver.py:286-287` verbatim; the readiness check matches `_resolve_claude_host` at `driver.py:335-345` and probes `[('online', True)]`; `OMNIGENT_SERVER` default at `driver.py:156`; both log paths exist; `launchctl list | grep omni` → `dev.zarz.omnigent`. Gates 4a-4c recorded green in `gates.md`.
