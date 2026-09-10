# Plan review 1 — issue #30 (codex-native flow with bundled superpowers skills)

**VERDICT: APPROVE**

Reviewed the approved spec against the plan and both repos (scenarios worktree +
`/Users/zarz/dev/flowbench`). All four rejection gates hold. Every path, symbol,
and line number the plan cites was verified real and exact. No blocking objections.

---

## (a) Traceability — criterion → task → test

Built independently from the spec. All six diff-checkable criteria have a task **and** a test.

| Spec criterion | Task | Test(s) | Verified |
|---|---|---|---|
| 1. Vendored skills present + VERSION.md pins 6.1.1 | Task 2 | `test_vendored_superpowers_skills_present` (SKILL.md ×3 + `"6.1.1" in VERSION.md`) | Source dir `~/.claude/plugins/cache/.../superpowers/6.1.1/skills/{using-superpowers,brainstorming,writing-plans}/SKILL.md` all present (cp -R target valid) |
| 2. `load_flows` resolves relative→absolute; ValueError names path on missing dir | Task 3 | `test_load_flows_resolves_skill_dirs` (== `[skill.resolve()]`, absolute), `test_load_flows_missing_skill_dir_raises` (`pytest.raises(ValueError, match="nope")`), `..._without_skill_dirs_unchanged` | `helpers.py:28-29` is exactly `load_flows`; `Path`/`yaml` imported (lines 7,9) |
| 3. `make_flow_driver_omni` threads `skill_dirs`→`OmnigentDriver.skill_dirs` | Task 4 §3 | `test_make_flow_driver_threads_skill_dirs`, `..._defaults_no_skill_dirs` | `run.py:291-304` exact; `OmnigentDriver.skill_dirs` field exists (driver.py:264), `model` (238), `harness` (262) |
| 4. todo_app flows.yaml A/B shape, equal skill_dirs, no `skills: all`, identical prompts | Task 4 §4 | `test_todo_app_flows_are_codex_vs_claude_same_skills` (pins names/harness/model, `reasoning_effort`, exact skills list, `skills: none`, `!= "all"`, skill_dirs equality + len 3, prepend/append equality) | todo_app case dir + flows.yaml exist; rewrite is a valid create-target |
| 5. flowbench `_create_metadata` harness-gated; claude byte-identical, codex long-form, other `[]`; one test per case | Task 1 | `..._codex_native_gets_codex_flags` (exact list ==), `..._unknown_harness_gets_no_flags` (== []), `..._claude_native_flags_unchanged` + 2 pre-existing default-harness tests | `driver.py:324-349` is exactly `_create_metadata`; `ALLOWED_TOOLS` defined at line 32 |
| 6. Offline suites green both repos | Task 5 | `uv run pytest -q` ×2 (verification task, no test needed) | — |
| 7. Live gate | (none — Phase 9.5) | — | Correctly deferred |

No criterion is missing a task or a test.

## (b) Ordering / cross-repo seam — PASS

- **flowbench Task 1** is fully self-contained (failing test → impl → suite → commit); flowbench green after it. Pre-existing metadata tests construct the default `claude-native` harness, so they stay green.
- **scenarios Tasks 2→3→4** each leave the offline suite green: Task 2 only adds vendored files + a presence test; Task 3 changes `load_flows` behind an `if "skill_dirs" in flow` guard (flows without the key unchanged); Task 4 threads one kwarg + rewrites todo_app flows.yaml.
- **No cross-repo test dependency.** `OmnigentDriver.skill_dirs` is a **pre-existing** flowbench field (driver.py:264), not added by Task 1 — so scenarios Task 4 does not need Task 1 to land. Conversely, Task 4's `test_make_flow_driver_threads_skill_dirs` constructs a `codex-native` driver but only reads `.skill_dirs/.harness/.model`; it never calls `_create_metadata`, so it does not exercise the flowbench change. Each repo's offline suite is green independently. The stated flowbench-first merge order is correct for the live gate but not required for offline greenness.
- Renaming todo_app flows superpowers/plain → codex/claude breaks nothing offline: no existing test reads todo_app flows content (`test_flows_shape` reads the untouched feature_flag_service case; `test_parse_args` checks only the default-case string). Import ordering is sound — Task 2 adds `from pathlib import Path` to `test_swe_planning_flows.py`, which Task 4's appended test then reuses.

## (c) Exact paths / interfaces — PASS (all verified)

- `driver.py:324-349` → `_create_metadata` def at 324, body through 349. Exact.
- `OmnigentDriver.harness` default `"claude-native"` at line 262. Exact.
- `ALLOWED_TOOLS` at driver.py:32, already consumed by the current `_create_metadata`. In scope for the rewrite.
- `helpers.py:28-29` → `load_flows`; `Path`/`yaml` already imported.
- `run.py:291-304` → `make_flow_driver_omni(flow: dict, flow_dir: Path)` — signature matches the plan's test calls.
- `OmnigentDriver` fields `harness`/`model`/`skill_dirs` all present (262/238/264); `_build_bundle` copies `skill_dirs` into `<bundle>/skills/<name>/` (driver.py:311-312), matching the spec's threading claim.
- `test_swe_planning_helpers.py` currently imports neither `pytest` nor `load_flows`; the plan explicitly adds both. Correct.
- `test_swe_planning_run.py` already imports `make_flow_driver_omni`, `pytest`, `Path`.
- `test_driver_config.py` imports `OmnigentDriver`; new tests use only the `harness` kwarg. Valid.

## (d) Test strength — PASS

- Codex flags test pins the **exact** list `["--ask-for-approval","never","--sandbox","workspace-write"]`; unknown-harness pins `== []`.
- todo_app flows test would fail if prompts diverge (prepend/append equality) or skills lists drift (exact list + `!= "all"` loop + skill_dirs equality/len).
- Missing-skill-dir test pins the raised `ValueError` and that the message names the path (`match="nope"`).
- `load_flows` resolution test asserts equality to an absolute `resolve()`d path.

Code blocks compile conceptually: `make_flow_driver_omni(flow, flow_dir)`, `OmnigentDriver(...skill_dirs=...)`, and field reads all reference real symbols.

---

## Advisory notes (non-blocking — no action required)

1. No offline test asserts flow A **omits** `reasoning_effort` (spec §5) nor that the claude-native branch reproduces the full `ALLOWED_TOOLS` tail byte-for-byte (criterion 5 wording). Both are acceptable: criterion 4/5's required assertions are present, and the impl reuses `",".join(ALLOWED_TOOLS)` verbatim, so the tail cannot regress from this change.
2. The `load_flows` implementation collapses "dir missing" and "dir lacks SKILL.md" into a single `SKILL.md.is_file()` check, so a genuinely missing directory yields a message worded "no SKILL.md at …". Behavior matches the spec (ValueError naming the path); only the wording is slightly imprecise. The spec's required test (missing dir) passes.
3. Environment: the scenarios editable dep is `../../flowbench` resolved from the pyproject location. The plan runs the suite in the worktree and cites a known baseline (100 passed, 1 skipped), so resolution is assumed already validated by the loop; not a plan defect.
