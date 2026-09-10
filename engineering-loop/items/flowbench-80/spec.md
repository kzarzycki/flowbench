# flowbench #80 — E02 S02.2: driver split

Epic: `docs/roadmap/epics/E02-runtime-robustness.md` § S02.2.
Target layout: `docs/roadmap/target-architecture.md` § Module map.

## Problem

`src/flowbench/runner/driver.py` is 617 lines carrying four concerns:

| lines | concern |
| --- | --- |
| 43–61 | `AgentDriver` ABC |
| 66–92, 94–97, 192–210, 212–232, 234–268 | agent-config render + tar bundle + session metadata |
| 606–617 | `_to_jsonable` — event → plain dict (transcript-shaped) |
| 99–120, 123–604 (rest) | `git_init_repo` + the omnigent session lifecycle |

`runner/loop.py` sits under `runner/` although the target position is
`flowbench/loop.py`. Line 64 is a dead section marker (`# --- transcript
helpers ---`) left behind when S01.1 moved those helpers to `transcript.py`.

## Scope

Behavior-preserving relocation only. No policy change, no signature change to
anything a caller passes, no change to bytes written to disk.

### Moves

1. `src/flowbench/driver/` package:
   - `base.py` — `AgentDriver` ABC, verbatim.
   - `bundle.py` — `AGENT_CONFIG`, `_indent`, and three pure functions of a
     `BundleSpec` protocol: `render_config(spec)`, `build_bundle(spec)`,
     `session_metadata(spec)`.
   - `omnigent.py` — `OmnigentDriver` (lifecycle, send/settle, capture, URLs)
     and `git_init_repo`.
   - `__init__.py` — re-exports `AgentDriver`, `OmnigentDriver`,
     `git_init_repo`, `render_config`, `build_bundle`, `session_metadata`,
     `TurnResult`, `TurnStatus`.
2. `_to_jsonable` → `flowbench.transcript.to_jsonable` (public; it is the last
   transcript-shaped thing in the driver). Dead marker at line 64 deleted.
3. `src/flowbench/runner/loop.py` → `src/flowbench/loop.py`.
4. Compat shims, one release each: `flowbench/runner/driver.py` and
   `flowbench/runner/loop.py` become re-export modules with a
   `# compat re-export (one release, E02 S02.2)` docstring.

### Test moves

`tests/runner/test_driver_bundle.py` → `tests/driver/test_bundle.py`;
`tests/runner/test_driver_config.py` → `tests/driver/test_config.py`;
`tests/runner/test_driver.py` → `tests/driver/test_omnigent.py`;
`tests/runner/test_loop.py` → `tests/test_loop.py`. Bodies change only where
they name a moved module (imports, `monkeypatch.setattr` targets).

## Acceptance criteria

- **AC1** `src/flowbench/driver/{__init__,base,bundle,omnigent}.py` and
  `src/flowbench/loop.py` exist. Both shims (`runner/driver.py`,
  `runner/loop.py`) are import-only: an `ast.parse` of each file yields
  top-level nodes drawn solely from `{Expr(Constant str)}`, `ImportFrom`,
  `Import`, and one `Assign` to `__all__` — no `def`, no `class`, no other
  statement (so a shim cannot smuggle in a side effect). Asserted by
  `tests/test_compat_reexports.py::test_shims_are_import_only`.
- **AC2** `render_config`, `build_bundle`, `session_metadata` are module-level
  functions in `driver/bundle.py`, each taking one positional parameter named
  `spec` (checked with `inspect.signature`), and `grep -n 'self\.' src/flowbench/driver/bundle.py`
  is empty. They read *only* `BundleSpec` fields, proved dynamically:
  `tests/driver/test_bundle.py::test_functions_need_only_the_bundlespec_fields`
  calls all three with a `SimpleNamespace` carrying exactly the protocol's
  fields and nothing else — any extra attribute read raises `AttributeError`.
  `OmnigentDriver` keeps `render_config()`/`_build_bundle()`/`_create_metadata()`
  as one-line delegates (tests and `docs/design/runner.md` name them).
- **AC3** `flowbench.transcript.to_jsonable` exists and is the only definition;
  `grep -rn '_to_jsonable' src/ tests/` → empty.
- **AC4** Compat holds for **every** symbol imported from the old paths today,
  by identity (`is`), plus module import itself:

  | old path | symbols |
  | --- | --- |
  | `flowbench.runner.driver` | `AgentDriver`, `OmnigentDriver`, `TurnResult`, `TurnStatus`, `git_init_repo`, `_PAGE` |
  | `flowbench.runner.loop` | `run_agent_session`, `render_tail`, `prime_prompt`, `relay_prompt`, `_is_done` |

  `import flowbench.runner.driver as m` and `import flowbench.runner.loop as m`
  both succeed and expose those names. `_PAGE` (`tests/runner/test_driver.py:528`)
  and `_is_done` (`tests/runner/test_loop.py:6`) are private but imported today,
  so they ride the shim for the same one release. Covered by
  `tests/test_compat_reexports.py`.
- **AC4b** The shims do **not** carry module internals: patching
  `flowbench.runner.driver.asyncio` / `flowbench.runner.loop.asyncio` is
  intentionally unsupported (decisions #11). Every test patch target names the
  canonical module: `grep -rn 'flowbench\.runner\.\(driver\|loop\)\.' tests/`
  → empty.
- **AC5** No engine source outside the two shims imports `flowbench.runner.driver`
  or `flowbench.runner.loop`:
  `grep -rn 'flowbench\.runner\.\(driver\|loop\)' src/ scenarios/` matches only
  the shims themselves and `src/flowbench/types.py`'s docstring.
- **AC6** `src/flowbench/driver/omnigent.py` line count is recorded in
  `gates.md` and in `docs/roadmap/current-state.md`. The epic's "~350" is not
  reachable behavior-preservingly (decisions #3); the epic's Verify line is
  amended to the achieved number with the reason.
- **AC7** Byte-identical bundle *contents*. Before implementing, `gates.md`
  records, from the unmodified tree, for one fixed driver + one fixed skill dir
  + one fixed MCP file: (a) the exact `render_config()` string (three variants:
  `skills="none"` with a two-paragraph `agent_prompt`, `skills="all"` with no
  prompt, `skills=["a","b"]`); (b) every tar member as
  `(name, kind, sha256(content))` — content hashes, not just `getnames()`, so a
  changed `config.yaml`/`SKILL.md`/MCP payload fails even when the paths match;
  (c) `_create_metadata()` for `claude-native`, `codex-native` and an unknown
  harness, with and without `session_title`/`project`.
  `tests/driver/test_bundle.py` gains golden assertions on all three, so the
  branch reproduces them exactly. Gzip *stream* bytes are deliberately not
  pinned — `tarfile` writes an mtime, so they are not reproducible; the member
  set plus per-file content hashes is the invariant that matters.
  (The pre-existing tests assert substrings only — gate 1 objection 4; content
  hashes are gate 1 r2 objection 1.)
- **AC8** V1 green: baseline count (`origin/master` 1324132: 220 passed,
  1 skipped) plus the new tests, no test deleted or weakened.
- **AC9** V2 green, run against *this branch's* engine:
  `cd $SCENARIOS-worktree && uv run --with-editable /Users/zarz/dev/agents/flowbench--s022 pytest -q`,
  with `python -c "import flowbench; print(flowbench.__file__)"` recorded under
  the same `--with-editable` and asserted to resolve inside the engine worktree.
- **AC10** `docs/design/runner.md`, `docs/roadmap/current-state.md`,
  `docs/roadmap/target-architecture.md` and `CLAUDE.md` name the new paths; the
  CLAUDE.md pre-read rule covers `src/flowbench/driver/`.
- **AC11** `ruff check` + `ruff format --check` clean; V8 diff-cover 100% in CI.
- **AC12** V4 (live `swe_planning` run) green — `verification.md:43-44` makes it
  mandatory for any change to `driver.py`/`loop.py`, and this story moves both
  files (decisions #10). Success criteria are V4's own: the watcher exits on
  `run.json`, no failed sessions, `winner` parsed, and each flow dir holds
  `plan.md` + `transcript.md` + `session.json`. Run-dir under
  `/Users/zarz/dev/xebia/flowbench-runs/`, `ANTHROPIC_API_KEY` unset,
  wrapped in `caffeinate -i`. Recorded in `gates.md` with the run id.

## Out of scope

- Any change to send/settle/retry policy or the wait budget — that is S02.3.
- Splitting the polling machinery (`_wait_idle`/`_snapshot`/`_children`/
  `_read_retry`/`_list_items`) out of `OmnigentDriver`: the epic assigns
  send/settle to `OmnigentDriver`, and S02.3 rewrites exactly this code.
- `artifact_name` leaving the driver (S02.4), private-API migration (S02.5),
  error taxonomy (S02.6).
- Deleting the compat shims — one release, like S02.1's.
