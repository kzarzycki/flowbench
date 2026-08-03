# CLAUDE.md Template

Use this as a starting point. Remove sections that don't apply. Keep it short.

```markdown
## Project Overview

<!-- 1-2 sentences: what this project is and its primary purpose -->

## Commands

<!-- Build, test, lint, run commands. Most important section for code projects. -->

## Conventions

<!-- Non-obvious rules that would cause mistakes if not followed -->
<!-- Examples: naming patterns, file organization, commit style -->

## Architecture

<!-- Only if the structure isn't self-explanatory -->
<!-- Key directories and what they contain -->

## Gotchas

<!-- Things that are surprising or easy to get wrong -->
<!-- Known issues, workarounds, things that look wrong but are intentional -->
```

## Guidelines for filling this template

- **Commands section is mandatory** for code projects — Claude needs to know how to build/test/run
- **Conventions section**: only include what differs from language/framework defaults
- **Architecture section**: skip if the project is small or the structure is standard
- **Gotchas section**: the highest-value section — this is where you prevent repeated mistakes
- Total target: 20-60 lines for most projects, up to 100 for complex ones
- If a rule can be inferred by reading the codebase, don't include it
