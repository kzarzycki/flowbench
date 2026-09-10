# issue-49 — self-answered questions

- **Scrub only GIT_DIR/GIT_WORK_TREE, or every GIT_\*?** Every `GIT_`-prefixed
  var. Source: git's own hook contract — a hook environment also carries
  `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_PREFIX`, `GIT_CONFIG_*`, each of
  which redirects a nested git the same way. Fixing only the two named in the
  issue leaves the same bug reachable from a different hook. The issue's own
  suggested fix is the prefix filter.
- **Any other git call site to fix?** No.
  `grep -rn "\"git\"" src scenarios --include='*.py'` → `driver.py:131` only.
- **Does dropping `GIT_AUTHOR_*`/`GIT_COMMITTER_*` break the commit?**
  No: `git_init_repo` sets `user.email`/`user.name` in the fresh repo's own
  config before committing (driver.py:135-137).
