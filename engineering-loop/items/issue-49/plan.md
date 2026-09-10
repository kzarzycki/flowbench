# issue-49 — plan

Constraint (verbatim from spec): scrub every `GIT_*` variable from the
environment handed to the subprocess in `run()`.

## T1 — failing test (red)
`tests/runner/test_driver_config.py`: add
`test_git_init_repo_ignores_inherited_git_env(tmp_path, monkeypatch)`.
Build an outer repo in `tmp_path/outer` (git init + identity + one commit),
`monkeypatch.setenv("GIT_DIR", str(outer/".git"))`,
`monkeypatch.setenv("GIT_WORK_TREE", str(outer))`,
`monkeypatch.setenv("GIT_INDEX_FILE", str(outer/".git"/"index"))`, then
snapshot `(outer/".git"/"index").read_bytes()`, then
`git_init_repo(tmp_path/"nested")`. Assert nested `.git` exists, nested
`rev-parse HEAD` succeeds, the outer repo's commit count is still 1, the outer
index bytes are unchanged, and `git -C outer status --porcelain` exits 0 with
empty stdout (all assertion commands run with a GIT_*-free env).
Covers AC2/AC3, and discriminates AC1 (a two-name scrub fails it). Verify it fails before T2.

## T2 — fix (green)
`src/flowbench/runner/driver.py` `git_init_repo.run()`: pass
`env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")}`
with a one-line comment naming the hook case. Covers AC1.
(`os` is already imported at module scope.)

## T3 — gates
`uv run pytest -q` (no new failures; 189 passed / 1 skipped today), `uv run ruff check .`,
`uv run ruff format --check .`. Covers AC4.
