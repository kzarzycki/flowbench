# Domain triage

When you extract hostnames from a binary or grep URLs from source, you'll see dozens of domains. Most are benign artifacts from upstream dependencies, help text, or standard cloud SDKs. Triaging them fast lets you focus on the actual signals.

## Clear benign patterns

These show up in almost every Node/Bun/Electron binary. Don't flag them unless there's *active* code calling them at runtime (not just a string reference).

### Upstream dependency artifacts
- `plus-innovations.com` — `systeminformation` npm package author homepage
- `feross.org` — several Feross utility packages (buffer, safe-buffer, etc.) author
- `react-native.canny.io` — AWS SDK error message URL for RN streaming polyfill
- `sharp.pixelplumbing.com` — `sharp` image package
- `ui.shadcn.com`, `react.dev`, `tailwindcss.com` — framework docs referenced in comments
- `registry.npmjs.org`, `npmjs.org` — package registry (always present)

### Cloud SDK endpoints (benign unless actually used)
- `cognito-identity.amazonaws.com`, `sts.amazonaws.com`, `bedrock-*.amazonaws.com` — AWS SDK
- `iamcredentials.googleapis.com`, `oauth2.googleapis.com`, `cloudresourcemanager.googleapis.com` — Google Cloud auth/project SDK
- `login.microsoftonline.com`, `aka.ms/azsdk/*` — Azure identity
- `169.254.169.254`, `metadata.google.internal` — cloud instance metadata (SDKs probe these)

### Language runtimes
- `bun.com`, `bun.sh`, `bun.report`, `debug.bun.sh` — Bun runtime's own telemetry/docs (shows up in every Bun-compiled binary)
- `nodejs.org` — Node SEA metadata

### Example/help-text domains
- `example.com`, `another.com`, `evil.com`, `hooks.example.com` — JSON Schema / test fixtures from libraries
- `a.co/*` — Amazon short-link, usually a comment reference
- `app.corridor.dev` — appears in `claude mcp add` help text as an example MCP server

### Feature flags inherited from upstream
- `cdn.growthbook.io` with SDK keys like `sdk-yZQvlplybuXjYh6L` — Claude Code's upstream feature-flag client. Not a custom vendor telemetry channel.

### AI platform endpoints that belong there
- `api.anthropic.com`, `claude.ai`, `claude.com`, `code.claude.com`, `cloudcode-pa.googleapis.com` — legitimate Anthropic/Claude Code
- `api.openai.com`, `auth.openai.com`, `chatgpt.com/backend-api/codex/responses` — OpenAI/Codex
- `generativelanguage.googleapis.com`, `aiplatform.googleapis.com` — Google Gemini
- `mcp.sentry.dev`, other `mcp-*.*.dev` — MCP servers users can add (not auto-connected)

## Red flags to investigate

### Vendor-operated endpoints disguised
- A hardcoded base URL stored in a variable (`const API = "https://xyz.foo"`) that doesn't match the project name or any listed dependency. Example from a prior audit: `__Y = "https://api.voicetext.site"` inside an agent_teams-related code path. The disguise is the point.
- Domains with generic/unrelated names (`voicetext.site`, `datasync.io`, `cloudhelper.app`) referenced as the base URL for the tool's own backend.

### Session/auth endpoints
- `/session/guest`, `/session/refresh`, `/capabilities`, `/auth/register`, `/license/activate` paths hit on startup, especially when combined with `client_id`, `installation_id`, or persistent UUID generation.

### Killswitch / capability JWTs
- Server-returned signed JWTs decoded client-side with claims like `features`, `providers`, `killswitches`, `enabled_models`. Means the vendor controls behavior remotely.

### Unusual protocols
- `ws://` / `wss://` connections to non-obvious hosts — persistent telemetry channels.
- `file://` references into user home dirs.

### Typosquatted or lookalike domains
- `anthropic-api.com` (not Anthropic), `claudecode.com` (not real Claude Code domain), `npmregistry.org` (not real npm), etc.

## Triage workflow

1. **Extract**: run `scripts/extract_strings_urls.py` against `strings` output to get unique hostnames.
2. **Classify**: mark each as `benign` (matches patterns above), `unknown` (needs investigation), or `suspicious` (matches red flags).
3. **Context grep unknowns**: for each unknown domain, grep ±200 chars around each occurrence. Is it a variable assignment, a string literal in an error message, a doc comment, an actual `fetch(...)` call, part of a JSON Schema example?
4. **Report only after classification**. Don't list 100 AWS SDK subdomains as "findings" — that's noise.

## Calibration

If the full extracted domain list has ~100-150 entries for a 270MB Bun binary, that's normal. The task is filtering down to the 1-5 that matter.
