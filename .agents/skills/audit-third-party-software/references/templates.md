# Report & issue templates

## AUDIT_FINDINGS.md

Write this to the audit directory root after finishing. Lets the user come back to the audit later without re-running it.

```markdown
# Static audit — <project name>

**Date:** YYYY-MM-DD
**Auditor:** local review, no execution
**Verdict:** SAFE | CAUTION | UNSAFE

## Artifacts examined

| Artifact | SHA-256 |
|---|---|
| `<path or name>` | `<hash>` |

(Omit this table if no binaries.)

## Critical findings

### 1. <Short name>

<Evidence with file:line. Two-to-four sentences on what it does and why it matters.>

### 2. <Short name>

…

## Notable but non-blocking

- **<name>** — evidence + impact.
- **<name>** — evidence + impact.

## What the software does (code-grounded)

<One paragraph describing actual runtime behavior. Call out any contradiction with README claims.>

## What cannot be determined without running the binary

<Only include if static analysis left gaps — e.g. payload of a call you could see in code but couldn't examine in traffic.>

## Recommendation

<Specific. If UNSAFE: don't install, why. If CAUTION: conditions under which to reconsider, or local mitigations that would allow safe use. If SAFE: install command + any minor tweaks.>
```

## GitHub issue (vendor notification)

Use when findings warrant reporting to the upstream. Tone: factual, specific, non-accusatory. Avoid AI-slop signals (generic preamble, triple markdown nesting, lists of asks when one ask would do).

### Title
Specific and claim-grounded. Bad: "Security concerns about this project". Good: "README says 'runs entirely locally' — the runtime calls `api.voicetext.site` on every launch".

### Body structure

```markdown
<one-line Claude disclosure if static analysis was AI-assisted>

I ran static analysis on <artifact> before installing (<hash or version>).

<Concrete finding with endpoints / file:line / quoted strings>

<Quote of the contradicting claim from README or marketing>

That's not accurate — <why, in one sentence>.

## What I'd like to ask

- **<top ask>.** <One sentence on why it matters.>
- **<secondary ask>.**
- **<tertiary ask>.**

<Closing line offering to be wrong if there's documentation you missed.>
```

### Claude disclosure line

If the audit used Claude-assisted analysis, be upfront. One line is enough:

```
_Static analysis was done automatically with Claude Code before installing — I've reviewed and endorsed the findings below. Happy to share the full audit output on request._
```

### Common tone failures to avoid

- "In good faith" / "Opening this in the spirit of" — slop preamble. Cut.
- Lists of asks where each ask repeats the same point in different words.
- Closing with an environment/metadata section ("Environment: macOS, darwin-arm64, Node 20.x"). Not an audit report.
- Triple-nesting (## section → ### subsection → #### sub-sub) when two levels would do.
- Hedging ("It seems like perhaps…"). Say what you found.

### Length

For a vendor issue, aim for 200-300 words. The findings themselves, one clear ask list, close. If you're at 500+ words, you're restating.

## Local patch / mitigation ticket

When the user wants to use the software anyway with hardening applied, document the patch for future reference so they can rebase on updates.

```markdown
# Local hardening — <project>

**Branch:** `local/harden`
**Base commit:** <sha>
**Date:** YYYY-MM-DD

## Changes

- <file path> — <one-line description>

## Why

<Short explanation of the threat being mitigated, citing the original audit.>

## Verification

<Exact commands that confirm the mitigation works, e.g. curl with different Origin headers.>

## Rebase procedure

```bash
cd <path>
git checkout main && git pull
git checkout local/harden && git rebase main
```
```

## Key writing principles across all templates

1. Verdict first, evidence second. A reader skimming for 30 seconds should get the conclusion.
2. Every finding has a file:line or SHA. No floating claims.
3. "What it actually does" is a neutral description — not marketing, not accusation.
4. Match the user's stated threshold. If they said "no warnings", don't engineer a soft "yes".
5. Offer a concrete next step. Findings without a recommendation are abandoned work.
