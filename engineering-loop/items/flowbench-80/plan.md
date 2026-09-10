# Plan — flowbench #80 (E02 S02.2 driver split)

Engine worktree `/Users/zarz/dev/agents/flowbench--s022`, branch
`loop/issue-s022-driver-split`, based on `origin/master` 1324132.
Baseline V1: 220 passed, 1 skipped.

Every task ends green on `uv run pytest -q`; a task that cannot stay green
alone is merged into its predecessor. All source moves use `git mv` where the
whole file moves, so the rename is visible in the diff.

## T0 — capture the goldens from `origin/master` (before any edit)

Run against a pristine `git worktree` of `origin/master` (or `git stash`-clean
HEAD, since T0 precedes every edit) a one-off script that builds one
`OmnigentDriver` with a fixed `run_dir`, one skill dir and one MCP file, and
prints (a) `render_config()` for three skills/prompt variants, (b) every tar member as `(name, kind, sha256(content))`, sorted, (c) `session_metadata()` for `harness=
"claude-native"`, `"codex-native"` and an unknown harness, **each** with and
without `session_title`/`project` (six variants — gate 2 objection 1: bare
`codex-native`/unknown were missing, so label/title leakage in those branches
would not have been caught). Paste the output verbatim into `gates.md` and into
the golden assertions T2 adds to `tests/driver/test_bundle.py`. **AC7.**

## T1 — `transcript.to_jsonable` + delete the dead marker

- Move `_to_jsonable` (`runner/driver.py:606-617`) verbatim into
  `src/flowbench/transcript.py` as `to_jsonable`, keeping the local
  `import dataclasses`.
- `runner/driver.py`: import it from `flowbench.transcript`, call site at
  `:362` becomes `to_jsonable(ev)`. Delete the dead marker at `:64`
  (`# --- transcript helpers ...`).
- Test: add `tests/test_transcript.py::test_to_jsonable_*` if the existing file
  has no coverage of it; otherwise the driver tests that assert `_captured`
  contents already cover it — check `grep -rn "to_jsonable\|__type__" tests/`
  first and only add what is missing (V8 needs the moved lines covered).
- Gate: `uv run pytest -q` → 220 passed (+ any new).
  **AC3** (`grep -rn '_to_jsonable' src/ tests/` empty).

## T2 — `src/flowbench/driver/` package

Order matters: create the package, then make `runner/driver.py` a shim, so the
suite never sees a half-moved module.

1. `git mv src/flowbench/runner/driver.py src/flowbench/driver/omnigent.py`
   (creating the dir), then carve out of it:
   - `driver/base.py` — module docstring + `AgentDriver` (`:43-61`) verbatim,
     imports `TurnResult` from `flowbench.types`.
   - `driver/bundle.py` — the AGENT_CONFIG comment block + template
     (`:66-92`), `_indent` (`:94-97`), and, converted from methods to
     module-level functions of a single `spec` argument, `render_config`
     (`:192-210`), `build_bundle` (from `_build_bundle`, `:212-232`) and
     `session_metadata` (from `_create_metadata`, `:234-268`). Bodies verbatim
     apart from `self.` → `spec.` — **with one exception that is not a
     mechanical rewrite**: `_build_bundle`'s `self.render_config()` becomes the
     module-level `render_config(spec)`, NOT `spec.render_config()`. A spec is
     not required to have that method, and the transcription slip survives every
     driver-backed test because `OmnigentDriver` does (gate 2, objection 2).
     Add:

     ```python
     class BundleSpec(Protocol):
         """The `Flow`-like fields the three functions read. `OmnigentDriver`
         satisfies it structurally; `runner.flow.Flow` will once S03.1 widens it."""
         run_dir: Path
         harness: str
         agent_name: str
         agent_description: str
         agent_prompt: str | None
         skills: str | list[str]
         skill_dirs: list[Path]
         mcp_files: list[Path]
         session_title: str | None
         project: str | None
     ```
   - `driver/omnigent.py` keeps `_PROMPT_KEYS`, `_PAGE`, `git_init_repo`,
     `OmnigentDriver`. Its three extracted methods become one-line delegates:
     `def render_config(self) -> str: return bundle.render_config(self)`,
     `def _build_bundle(self) -> bytes: return bundle.build_bundle(self)`,
     `def _create_metadata(self) -> dict[str, Any]: return bundle.session_metadata(self)`.
     Trim the module docstring's "everything omnigent-specific lives here" to
     match the new boundary; keep the three hard-won-settings bullets.
   - `driver/__init__.py` — docstring + re-exports of `AgentDriver`,
     `OmnigentDriver`, `git_init_repo`, `render_config`, `build_bundle`,
     `session_metadata`, `TurnResult`, `TurnStatus`, with `__all__`.
2. `src/flowbench/runner/driver.py` recreated as the compat shim:
   docstring `"""Compat re-export (one release, E02 S02.2) — canonical home is
   flowbench.driver."""` plus `from flowbench.driver import (...)  # noqa: F401`
   covering the AC4 symbol list — `AgentDriver`, `OmnigentDriver`, `TurnResult`,
   `TurnStatus`, `git_init_repo` — and `from flowbench.driver.omnigent import
   _PAGE  # noqa: F401`. The shim carries an `__all__` and nothing else; it does
   **not** re-export `asyncio` or any other module internal (decisions #11).
3. Update in-repo importers: `src/flowbench/run.py:17`,
   `src/flowbench/testing.py:8`, `src/flowbench/model.py:16`,
   `src/flowbench/runner/loop.py:12`,
   `scenarios/coding_workflow/cases/todo_app/scoring.py:13`.
4. Tests: `git mv tests/runner/test_driver_bundle.py tests/driver/test_bundle.py`,
   `test_driver_config.py` → `tests/driver/test_config.py`,
   `test_driver.py` → `tests/driver/test_omnigent.py` (+ `tests/driver/__init__.py`
   only if `tests/runner/` has one). Edit **only** imports and the
   `monkeypatch.setattr` string targets:
   `flowbench.runner.driver.asyncio.{sleep,create_subprocess_exec,wait_for}` →
   `flowbench.driver.omnigent.asyncio.…` (every site enumerated in gates.md),
   and `from flowbench.runner.driver import _PAGE` → `flowbench.driver.omnigent`.
   Then `grep -rn 'monkeypatch.setattr("flowbench\.runner' tests/` must be empty
   (**AC4b**) — a missed target would silently stop patching the code under test.

   Add to `tests/driver/test_bundle.py`:
   - the T0 golden assertions — the config string (3 variants), the tar members
     as `(name, kind, sha256)`, `session_metadata` (6 variants) (**AC7**);
   - `test_functions_need_only_the_bundlespec_fields` (**AC2**): call all three
     with a `SimpleNamespace` carrying exactly the protocol's fields and nothing
     else. This is the only check that catches the `spec.render_config()` trap
     above — it raises `AttributeError` on any read outside `BundleSpec`.
   Leave `tests/test_model.py:7` and `tests/test_types.py:39,57` pointing at the
   old paths — they are the compat coverage.
- Gate: `uv run pytest -q` green, same count. **AC1, AC2, AC5, AC7**.

## T3 — `flowbench/loop.py`

- `git mv src/flowbench/runner/loop.py src/flowbench/loop.py`; its import
  becomes `from flowbench.driver import AgentDriver`.
- `src/flowbench/runner/loop.py` recreated as the shim
  (`from flowbench.loop import run_agent_session, ...  # noqa: F401`),
  re-exporting every name the file defines: `render_tail`, `prime_prompt`,
  `relay_prompt`, `run_agent_session`, and `_is_done` (private, but imported by
  `tests/runner/test_loop.py:6` today — AC4).
- `src/flowbench/run.py:24` → `from flowbench.loop import run_agent_session`.
- `git mv tests/runner/test_loop.py tests/test_loop.py`; its
  `monkeypatch.setattr("flowbench.runner.loop.asyncio.sleep", …)` (`:236`) →
  `flowbench.loop.asyncio.sleep`.
- Gate: `uv run pytest -q` green. **AC1, AC5**.

## T4 — compat tests

New `tests/test_compat_reexports.py`:
- `test_runner_driver_reexports_are_the_same_objects` — for each of
  `AgentDriver, OmnigentDriver, TurnResult, TurnStatus, git_init_repo`,
  `getattr(flowbench.runner.driver, n) is getattr(flowbench.driver, n)`.
- `test_runner_loop_reexports_are_the_same_objects` — same for
  `run_agent_session, render_tail, prime_prompt, relay_prompt, _is_done`
  against `flowbench.loop`.
- `test_downstream_import_forms_still_work` — the two literal import
  statements `scripts/codex_review.py:23` and `tests/test_codex_review.py:7`
  use in the scenarios repo.
- `test_shims_are_import_only` — `ast.parse` each shim; every top-level node is
  a docstring `Expr`, an `Import`/`ImportFrom`, or the `__all__` `Assign`
  (**AC1**).
- Negative control: assert `flowbench.driver.omnigent` does **not** define
  `render_config`/`build_bundle`/`session_metadata` at module level (a
  copy-paste-instead-of-move implementation fails this test), and that
  `flowbench.runner.driver` has no `asyncio` attribute (**AC4b**, decisions #11).
- **AC1, AC4, AC4b**.

## T5 — docs + line count

- `docs/design/runner.md`: `## driver.py` → `## flowbench/driver/ — the ONE
  package that knows omnigent exists`, with the three-module table; `:21`
  `OmnigentDriver._build_bundle` → `flowbench.driver.bundle.build_bundle`;
  mention `flowbench/loop.py`'s new home.
- `docs/roadmap/current-state.md`: replace the `runner/driver.py | 575` row
  with rows for `driver/omnigent.py`, `driver/bundle.py`, `driver/base.py`,
  `loop.py`, and the two shims, each with its measured `wc -l`.
- `docs/roadmap/target-architecture.md`: module map — `__init__.py` becomes
  "public surface (re-exports)" and a `base.py # AgentDriver ABC` line is added
  (decisions #1); `bundle.py` comment gains "+ session metadata".
- `docs/roadmap/epics/E02-runtime-robustness.md` S02.2 Verify: replace
  "`driver/omnigent.py` under ~350 lines" with the measured number and one
  sentence naming #68/#76 and S02.3 (decisions #3). Do **not** edit any other
  story.
- `CLAUDE.md`: Layout section — `src/flowbench/driver/` (three modules),
  `src/flowbench/loop.py`, `runner/` reduced to `flow.py`/`judge.py` + the two
  shims; the pre-read rule becomes "Touching `src/flowbench/driver/` or
  `src/flowbench/loop.py`? Read `docs/design/runner.md` first."
- **AC6, AC10**.

## T6 — gates

Record every command + output in `gates.md`:
V1 (AC8), V3 `pre-commit run --all-files` / `ruff check` + `ruff format --check`
(AC11), V2 under `--with-editable` with the `flowbench.__file__` assertion
(AC9), the AC1/AC3/AC5 greps, `wc -l src/flowbench/driver/*.py src/flowbench/loop.py`
(AC6), V8 locally
(`uv run pytest -q --cov=src/flowbench --cov-report=xml && uv run diff-cover
coverage.xml --compare-branch origin/master --fail-under=90`), and the AC4b
patch-target grep.

## T7 — V4 live validation (AC12)

**Before the merge**, not after — rule 5 ("never merge with a red gate") applies
to V4 too. The run must exercise *this branch's* engine, so it uses the same
`--with-editable` form AC9 uses for V2:

```bash
cd /Users/zarz/dev/xebia/flowbench-scenarios--s022
unset ANTHROPIC_API_KEY
caffeinate -i nohup uv run --extra live \
  --with-editable /Users/zarz/dev/agents/flowbench--s022 \
  python -m scenarios.swe_planning.run --run-id s022-<ts> \
  --runs-root /Users/zarz/dev/xebia/flowbench-runs/swe_planning &
uv run python -m scenarios.swe_planning.watch s022-<ts> --pid $!
```

Self-verifying like AC9: record `python -c "import flowbench;
print(flowbench.__file__)"` under the identical `uv run --extra live
--with-editable …` invocation and require a path inside the engine worktree —
`uv run` re-syncs and would otherwise validate the git-pinned engine, not the
branch (the S02.1 lesson in `LOG.md`).

Launched with `nohup … &`, not as a harness background task (the ledger's
todo-app-006 note: the memory reaper killed one mid-run). Record run id,
exit statuses, `winner`, and the per-flow file list in `gates.md`. A red V4
blocks the merge like any other gate.

## AC traceability

| AC | Task | Check |
| --- | --- | --- |
| AC1 | T2, T3 | grep for defs in the shims |
| AC2 | T2 | `bundle.py` functions module-level, `self.`→`spec.` |
| AC3 | T1 | `grep -rn '_to_jsonable'` empty |
| AC4 | T4 | `tests/test_compat_reexports.py` |
| AC5 | T2, T3 | `grep -rn 'flowbench\.runner\.(driver|loop)' src/ scenarios/` |
| AC6 | T5, T6 | `wc -l`, epic + current-state edits |
| AC7 | T0, T2 | goldens captured from master, asserted on the branch |
| AC8 | T6 | V1 |
| AC9 | T6 | V2 `--with-editable` + `flowbench.__file__` |
| AC10 | T5 | doc diffs |
| AC4b | T2, T6 | patch-target grep, `no asyncio` assertion |
| AC11 | T6 | ruff, diff-cover |
| AC12 | T7 | V4 live swe_planning run |

## Scenarios PR (separate worktree, after the engine PR merges)

`scripts/codex_review.py:23` and `tests/test_codex_review.py:7` →
`from flowbench.driver import OmnigentDriver` / `TurnResult`; engine pin bumped
to the merge SHA (`uv lock`); ledger entry; this item dir.

These two are the only downstream sites, and they are the reason the shim
exists: engine V2 stays green through it, so nothing forces them to move.
Gate 2 (objection 3) is right that a green suite hides them — they are
therefore listed explicitly here and in the ledger entry, and the shim's
one-release clock starts at this merge.
