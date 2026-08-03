# Supply chain audit

What to check when a project pulls in external dependencies or runs install-time scripts.

## Manifests & lockfiles

Read in this order:

1. `package.json` — direct dependencies and lifecycle scripts
2. `pnpm-lock.yaml` / `package-lock.json` / `bun.lock` / `yarn.lock` — resolved versions, integrity hashes
3. Multiple lockfiles present = mild smell (developer churn, unclear canonical PM). Check which is committed most recently.

### Red-flag script patterns in package.json

- `"preinstall"`, `"postinstall"`, `"prepare"` running curl/wget, downloading arbitrary URLs, writing outside `node_modules/`
- `"install"` that builds native code from a git clone (could be legitimate for node-gyp packages; flag if it's running unvetted shell scripts)
- Scripts that exec files from paths controlled by env vars

### Green flags

- `"onlyBuiltDependencies": ["electron", "node-pty", "better-sqlite3", "sharp"]` (pnpm) — explicitly allow-lists which deps can run install scripts; blocks surprise postinstalls from transitive deps. Strong positive signal.
- `packageManager` field pinned to a specific version — indicates reproducibility discipline.
- `engines.node` pinned — same.

## Dependency surface scan

Grep direct deps for:
- **Typosquats**: `lodash` vs `lodash.` vs `lod4sh`; `chalk` vs `colors`; `commander` vs `command-line`. Use judgement; a single letter off from a very popular package is suspicious.
- **Recently published**: not a perfect signal (new good packages exist) but combined with low download counts and unknown maintainers it matters. Check via `npm view <pkg> time` if needed.
- **Unusual sources**: deps resolving from non-npm registries, private registries, or git URLs. Grep lockfile for `resolved:` lines that don't start with `https://registry.npmjs.org`.

## Install-time scripts outside package.json

Also read:
- `.husky/` hooks — run on git operations
- `scripts/install.sh`, `scripts/setup.sh`, `bin/*` — manually invoked
- `.github/workflows/*.yml` — run on CI but may still be triggered by the user (publish, release)
- `Dockerfile` / `docker-compose.yml` — what gets downloaded during image build
- `.pre-commit-config.yaml` — what runs on every commit

Look for:
- `curl | sh` / `wget | sh` — note the source; some are widely trusted (astral.sh, bun.sh, rustup.rs, deno.land). Unfamiliar sources are findings.
- Fetches to mirror/gist URLs rather than vendor primary
- Scripts that pipe through `eval` or `source` from downloaded content

## CI workflows

GitHub Actions are worth a skim:
- `pull_request_target` triggers + checkout of PR head = classic actor-takeover vector, but mostly a vendor-side problem, not user-install-time concern.
- Workflows that use secrets during `npm publish` — not your problem unless you're forking.
- Workflows that run `curl | bash` to set up tooling during CI — same as install-time concern.

## Python projects

Analogous checks:
- `pyproject.toml` / `setup.py` / `setup.cfg` — install hooks
- `requirements.txt` — pinned versions; unpinned `>=` is a mild smell
- `uv.lock` / `poetry.lock` — lockfile integrity
- `install_requires` with git URLs or VCS refs = same as npm git-resolved deps

## Rust / Go / compiled languages

- `Cargo.toml` `[build-dependencies]` with `build.rs` that fetches code
- `go.sum` mismatches between mod references and lock
- Vendored dependencies (binaries committed to the repo) always warrant inspection — see `binary-analysis.md`

## False alarms to clear fast

- `node-gyp`-style native builds for `sharp`, `better-sqlite3`, `node-pty`, `canvas` — legitimate native compilation, not malicious.
- `husky`'s own postinstall setting up git hooks in your local `.git/hooks/` — legitimate.
- Prisma/next/vite/webpack large install trees — large surface doesn't mean malicious; audit the shape, not the size.

## One-liner: scan for postinstalls across all package.jsons

```bash
find . -name package.json -not -path './node_modules/*' -exec grep -lE '"(pre|post)?install"' {} \;
# Then read each, checking what the script actually does
```
