# Vendored superpowers skills

Verbatim copies from the `superpowers` Claude plugin, marketplace
`claude-plugins-official`, version **6.3.0**
(`~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/`),
copied 2026-09-08 for issue #2 (S01.3).

Never hand-edit these copies — re-vendor from a newer upstream version instead
(pre-commit whitespace normalization on copy is expected and fine). They exist
so the superpowers flow loads an identical skill set from the flow bundle
(`flows.yaml` `skill_dirs`) with no host-skill dependence. All 14 dirs are
vendored (not just the 3 swe_planning needs) because the build workflow spans
brainstorm → plan → implement → review.
