APPROVE

# Gate 3 — branch review, loop/issue-49-git-env (53bcd9e, 1 commit, `git diff origin/master...HEAD`)

Reviewed by git commands only; the worktree `/Users/zarz/dev/agents/flowbench--bugs` is
checked out on a different branch (`loop/issue-46-invoker-probe`), so all file content came
from `git show loop/issue-49-git-env:<path>`. Verification ran in throwaway `git archive`
copies under the scratchpad; nothing in the worktree was edited.

## Evidence

- **AC1** — `src/flowbench/runner/driver.py:132` builds
  `env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}` and passes it at
  `driver.py:134`. Whole-prefix scrub, as the spec requires. `os` already imported at module
  scope; no new import.
- **AC3 / would-fail** — branch test run against master's `driver.py` (branch tree, driver
  swapped from `origin/master`): FAILS with
  `CalledProcessError … ['git','-C',…/nested,'commit',…] returned non-zero exit status 1`.
- **AC2 discrimination** — verified empirically, not just by reasoning: with the driver patched
  to a two-name scrub (`k not in ("GIT_DIR","GIT_WORK_TREE")`) the test still FAILS, at
  `git -C outer status --porcelain` → exit 128. So the delivered test does discriminate the
  prefix scrub from the narrow one, which was AC2's stated purpose.
- **AC4** — pristine branch copy: `189 passed, 1 skipped` (master baseline `188 passed,
  1 skipped`; exactly the one new test, nothing else moved). `ruff check .` → All checks
  passed. `ruff format --check .` → 54 files already formatted.
- **(b)** Diff is purely additive: no test deleted, weakened, skipped, or xfailed; no assertion
  relaxed; the new test asserts on observable outer-repo state, not on the implementation's
  internals (it never inspects the `env` dict).
- **(c)** `git diff --stat`: `src/flowbench/runner/driver.py` (+5/-1) and
  `tests/runner/test_driver_config.py` (+65). Exactly T1+T2 of the plan, nothing else.
- **(d)** No CI config, no gate definitions, nothing under `.claude/`, no `.github/`,
  no `pyproject.toml`/`mise.toml` touched.
- **(e) root, not leaf** — `git` is shelled out from exactly one place in the repo:
  `driver.py:134`. `grep` over `src/`, `scenarios/`, `scripts/` finds no other `git`
  subprocess (`scenarios/.../acceptance.py:104,125` run *python* in the workspace;
  `src/flowbench/run.py` only threads the `git_init` flag). `scripts/` holds
  `check-symlinks.sh` and `patch_omnigent.py`, neither invokes git. No second site with the
  same bug.
- **(f) correctness traps**
  - Scrubbing all `GIT_*` at runtime: `git_init_repo` does local `init`/`config`/`add`/`commit`
    only, never contacts a remote, and sets its own `user.email`/`user.name` per-repo, so
    dropping `GIT_ASKPASS`/`GIT_SSH*`/`GIT_AUTHOR_*`/`GIT_COMMITTER_*` cannot break it.
    `PATH`/`HOME` and everything non-`GIT_` are preserved (the dict is a filtered copy of
    `os.environ`, not a replacement).
  - Test soundness: every assertion subprocess runs with `_no_git_env()`, so the monkeypatched
    `GIT_DIR` cannot redirect the checks themselves — and the same helper makes the *setup* of
    the outer repo hermetic when the suite is itself run from the pre-push hook (the very
    context that produced the bug). Ordering is sound: outer repo built and committed BEFORE
    the `monkeypatch.setenv` calls, act, then reads. `outer` and `nested` are siblings under
    `tmp_path`, no nesting artefact.

## Non-blocking notes (do not need a revision)

1. `tests/runner/test_driver_config.py:63-67` — AC2 literally asks for two further assertions
   the test omits: the outer index byte-identical before/after, and `status --porcelain`
   stdout empty (the call uses `check=True` + `capture_output=True` but never asserts on
   stdout). I checked these are omissions of form, not of power: the `status` exit code
   already catches the `GIT_INDEX_FILE` leak (proven above), and I could not construct a scrub
   variant that dirties outer's worktree while leaving `status` at exit 0. I also confirmed the
   index-bytes assertion is *not* flaky when placed before the `status` call (added it to a
   scratch copy against the branch driver: passes) — note the ordering matters, since `status`
   can itself refresh and rewrite the index, so a snapshot compared after it would be unsound.
   Two lines if the loop wants literal AC2 coverage.
2. Out of scope, pre-existing: the scrub does not isolate the *global* git config, so a
   developer with e.g. `commit.gpgsign=true` or a `core.hooksPath` would still have it apply to
   the run-dir commit (visible in the captured stderr of the test run: a global pre-commit hook
   fires). Unchanged from master; not this issue's bug.
