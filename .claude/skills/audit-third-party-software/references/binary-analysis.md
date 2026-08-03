# Binary analysis

For any compiled binary bundled with or downloaded by the software being audited. The goal is to answer: what network endpoints does it contact, what runtime does it embed, and is there anything unexpected.

## Step 1: Fingerprint

```bash
# Record a SHA-256 so future audits can detect silent swaps
shasum -a 256 <binary>

# Basic identification
file <binary>

# macOS signing + entitlements
codesign -dv <binary> 2>&1
codesign -d --entitlements - <binary> 2>&1

# Dynamic library dependencies (macOS)
otool -L <binary>

# Linux equivalents
ldd <binary>
readelf -d <binary> | head -20
```

What to note:
- **Ad-hoc signed / no team ID** on macOS = amateur or indie shop. Not necessarily bad, but combined with network behavior is context.
- **Developer ID + notarization** = vendor has at least been fingerprinted by Apple.
- **Unusual dylibs** beyond `libSystem`, `libc++`, `libicucore`, `libresolv` deserve a closer look.
- **Entitlements** like `allow-jit`, `allow-unsigned-executable-memory`, `disable-library-validation` are standard for Electron/Node runtimes. In a CLI tool they're worth noting.

## Step 2: Runtime detection

Most modern "binaries" are actually compiled JavaScript runtimes (Bun `bun build --compile`, Node SEA, pkg, nexe) or Go/Rust. Detecting the runtime tells you how much source is recoverable.

```bash
strings -a <binary> > /tmp/strings.txt

# Bun
grep -m1 "bun-v" /tmp/strings.txt

# Node SEA / pkg / nexe
grep -iE "^(NODE_SEA|nexe|pkg\/[0-9])" /tmp/strings.txt

# Go
grep -m1 "go1\." /tmp/strings.txt
# Also: runtime.g0, runtime.main — Go-specific symbols

# Rust
nm <binary> 2>/dev/null | grep -m1 _ZN4core  # mangled symbols
```

Bun and Node SEA preserve JS source in the binary — readable with `strings` even if minified with single-letter identifiers. Go and Rust give you much less back.

## Step 3: URL + domain extraction

Use the helper script:

```bash
python3 ~/.claude/skills/audit-third-party-software/scripts/extract_strings_urls.py /tmp/strings.txt
```

It pulls all `https?://...` URLs, deduplicates, extracts unique hostnames, and classifies known-benign patterns (AWS SDKs, npm registry, Google Cloud metadata servers, common feature-flag/telemetry CDNs that may be legitimately inherited from upstream deps).

Review the remaining unknown domains. Each one gets a context grep:

```bash
python3 -c "
import re
data = open('/tmp/strings.txt').read()
for m in re.finditer(r'<domain>', data):
    start = max(0, m.start() - 200)
    end = min(len(data), m.end() + 400)
    print('===')
    print(data[start:end])
"
```

The surrounding code tells you whether it's a **vendor-controlled endpoint** (hardcoded base URL used for auth/session/capabilities calls) or **benign artifact** (npm package author homepage, AWS SDK error message URL, MCP server example in help text).

## Step 4: Capability & session patterns

Especially for AI-adjacent tools, watch for these patterns in the embedded JS:

- `POST /.../session/guest` with `{client_id}` → **installation-unique tracking**
- `refresh_token` + `access_token` pair → OAuth-like session, often for SaaS-gating disguised as "local" tools
- Signed JWT with `features`, `providers`, `models`, `killswitches` claims → **remote capability control / killswitch**
- `subject: { ... }` in session responses → check what user data is echoed back; may hint at what was sent

If you see this pattern, verify there's NO env var or config flag to disable it. Grep for common opt-out names:

```bash
grep -iE "CLAUDE_[A-Z_]*_(DISABLE|OFFLINE|NO_TELEMETRY|LOCAL_ONLY)" /tmp/strings.txt
grep -iE "(DISABLE|OFFLINE|NO_TELEMETRY)_[A-Z_]+" /tmp/strings.txt
```

No opt-out = mandatory phone-home. Report as blocking.

## Step 5: Credential and filesystem access

```bash
# Dotfile reads
grep -oE "\"\\.(ssh|aws|gcp|azure|git-credentials|netrc|pgpass|docker)[^\"]*\"" /tmp/strings.txt | sort -u

# Keychain access
grep -iE "keychain|CredentialStore|DPAPI|safeStorage" /tmp/strings.txt | head -20
```

Reading `.ssh/` or `.aws/credentials` from a tool that has no legitimate reason to = finding. Keychain usage is usually *good* (means they store secrets properly).

## Step 6: Suspicious runtime behaviors

```bash
# Dynamic evaluation
grep -cE "\beval\s*\(|new Function\s*\(" /tmp/strings.txt
# Base64-decoded-then-executed payloads
grep -cE "Buffer\.from\([^)]*,\s*['\"]base64" /tmp/strings.txt
# Anti-debug / anti-VM
grep -iE "VMWare|VirtualBox|QEMU|isDebuggerPresent" /tmp/strings.txt | head
```

In a modern bundled JS app, `eval` counts in the low hundreds are often from upstream libs (React, Vue dev warnings). Above that, or in combination with base64 decode → follow the code.

## Calibration note

The first time you run this on a benign binary, it looks scary — hundreds of URLs, dozens of domains, Google Cloud and AWS metadata endpoints everywhere. That's normal for any app using cloud SDKs. The triage in `domain-triage.md` exists so you can quickly clear the noise and focus on the real signals.
