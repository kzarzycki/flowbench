# issue-49 — git_init_repo must not inherit GIT_* from a hook-invoked parent

**Size:** S (one function, one test file).

## Problem
`git_init_repo()` (`src/flowbench/runner/driver.py:123`) shells out to git inside a
fresh run-dir. Its `run()` helper passes no `env`, so the subprocess inherits the
caller's environment. When the caller is itself a git hook (this repo's
`pytest (pre-push)`), git has exported `GIT_DIR`/`GIT_WORK_TREE` pointing at the
OUTER repo; the nested `git -C <tmp> commit` is redirected onto that repo and
fails. Real impact beyond tests: a live run launched from any git-hook or
git-alias context would seed the run-dir repo into the wrong repository.

## Fix
Scrub every `GIT_*` variable from the environment handed to the subprocess in
`run()` — the single call site for git in the codebase
(`grep -rn "\"git\"" src scenarios --include='*.py'` → driver.py:131 only).
Scrubbing the whole `GIT_` prefix, not just the two named vars, is the root-cause
fix: `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_CONFIG_*` and friends are all
exported by hooks and all redirect a nested git.

`GIT_ASKPASS`/`GIT_SSH*` are also dropped; `git_init_repo` never touches a remote,
so nothing needs them.

## Why safe
Local-only init/config/add/commit. Identity is already set per-repo by the
function itself, so dropping `GIT_AUTHOR_*`/`GIT_COMMITTER_*` cannot break the
commit. No other caller of git exists.

## Acceptance criteria (machine-checkable)
1. `run()` passes an explicit `env` that contains no key starting with `GIT_`.
2. A test sets `GIT_DIR`, `GIT_WORK_TREE` **and `GIT_INDEX_FILE`** (via
   monkeypatch) to a *different* real repo, calls `git_init_repo(tmp_path)`, and
   asserts: it does not raise, `tmp_path/.git` exists, `git -C tmp_path rev-parse
   HEAD` resolves, and the outer repo pointed at by GIT_DIR gained no commit.
   Plus: the outer repo's index file is byte-identical before and after, and
   `git -C outer status --porcelain` (run with a GIT_*-free env) exits 0 with
   empty output. The index assertion is what discriminates AC1's prefix scrub
   from a scrub of just the two vars the issue names: under a two-name scrub the
   nested `git add` writes through the inherited `GIT_INDEX_FILE`, corrupting the
   outer index while leaving its commit count untouched — so commit count alone
   cannot see it.
3. That test fails on master (`CalledProcessError`).
4. Offline suite green with no new failures; ruff check and ruff format clean.
