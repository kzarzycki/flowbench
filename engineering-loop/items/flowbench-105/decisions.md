# Decisions — flowbench #105 part 1

- Docs-only engine PR: the brief forbids engine code changes (S02.3 owns the driver). Migration
  verdicts are recorded for part 2, not applied.
- Public-equivalent check is done against two truths: the pinned `omnigent-client==0.2.0`
  (what the driver imports) and the server checkout at `~/dev/ext/omnigent/omnigent`
  (`0.13.0.dev0`, fork of omnigent-ai/omnigent; what actually serves requests). A migration is
  "now" only if the pinned client already has the call.
- Upstream target: `omnigent-ai/omnigent` (parent of the fork; the fork has issues disabled —
  precedent `items/upstream/omnigent-effort-validation.md`). Drafts are written to
  `items/upstream/`, filing waits for the owner.
- Raw REST calls through flowbench's own `httpx` client (`/v1/hosts`, `/v1/sessions/{id}`,
  `/child_sessions`, `/resources`) are public HTTP, not private Python API; listed in an appendix
  so part 2 can decide, not counted as reach-ins.
