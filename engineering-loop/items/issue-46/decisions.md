# issue-46 — self-answered questions

- **Which of the issue's three suggested fixes?** The import-system probe
  (a variant of "decide by probe returncode"). Source: the issue's first listed option,
  "decide by probe returncode", generalized from an exit status parsed out of a
  run to a direct import-system query (an inference, not a quote). Its "probe the console entry
  first" option is rejected in the spec because it would re-route every build
  that ships both styles — a behaviour change to what acceptance measures, not
  a bug fix.
- **Does the fixture need a `todo` package?** No — the whole point is a build
  with no `todo` module at all (`todoapp` + `[project.scripts] todo`), which is
  exactly the shape that scores 0.0 today. `resolve_app_dir` finds no `todo`
  and returns the workspace root, where the fixture's `pyproject.toml` lives, so
  `_console_entry()` resolves it.
- **Single-module apps (`todo.py`, no package)?** Must keep working: the probe
  treats a non-package spec (`submodule_search_locations is None`) as runnable,
  matching `python -m todo` semantics.
