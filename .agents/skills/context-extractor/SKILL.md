---
name: context-extractor
description: Analyze a project and extract conventions, patterns, and context into a CLAUDE.md file. Works for any project type — code repos, presentation collections, research corpora, documentation projects. Trigger on "extract conventions", "analyze project patterns", "generate CLAUDE.md", "what are the conventions", or /conventions.
---

# Context Extractor

Analyze the current project and draft a CLAUDE.md capturing its conventions, patterns, and context. Works for ANY project type, not just code.

## Workflow

### Step 1: Detect Project Type

Scan the project root to determine what kind of project this is:

| Signals | Project Type |
|---------|-------------|
| package.json, Cargo.toml, pyproject.toml, go.mod, pubspec.yaml | Code repository |
| .github/workflows/, Jenkinsfile, .gitlab-ci.yml | CI/CD pipeline |
| *.pptx, *.key, slides/ | Presentation collection |
| *.md collection, docs/, wiki/ | Documentation project |
| data/, notebooks/, *.ipynb | Data/research project |
| Mixed or unclear | General project |

A project may be multiple types. Identify the primary and secondary types.

### Step 2: Scan for Conventions

Based on detected type(s), scan using the appropriate checklist:

**For all project types:**
- File/directory organization and naming patterns
- Existing README.md, CONTRIBUTING.md, CLAUDE.md content
- Git commit message style (last 20 commits)
- Any .editorconfig, .prettierrc, or formatting configs

**For code repositories (add to above):**
- Build system and commands (from package.json scripts, Makefile, etc.)
- Language conventions: naming style, import patterns, error handling (sample 5-10 source files)
- Test framework, test file naming, test patterns
- CI/CD quality gates
- Linting/formatting configuration
- Non-obvious: .env.example, docker-compose, special scripts, gotchas

**For presentation projects:**
- Slide structure patterns (title slides, section dividers, etc.)
- Branding: colors, fonts, logos used
- Template files
- Naming conventions for slide decks

**For documentation projects:**
- Document structure (headings, sections)
- Citation/reference style
- Metadata/frontmatter patterns
- File naming conventions

**For data/research projects:**
- Notebook structure patterns
- Data pipeline conventions
- Naming for datasets, experiments
- Environment setup

### Step 3: Draft CLAUDE.md

Use the template at [references/templates/claude-md-template.md](references/templates/claude-md-template.md) as a starting point. Fill in discovered conventions.

**Rules:**
- Keep it concise — only include what Claude can't infer from reading the code/files
- Use imperative style ("Run X before committing", not "The team prefers to run X")
- Focus on non-obvious things that would cause mistakes
- Include build/test/run commands prominently

### Step 4: Present to User

- If CLAUDE.md already exists: present proposed additions as a diff. NEVER remove existing user content.
- If no CLAUDE.md exists: present the full draft.
- **NEVER apply without explicit user approval.**

### Update Mode

When called on a project that already has a good CLAUDE.md:
1. Run the analysis
2. Compare findings against existing CLAUDE.md
3. Propose ADDITIONS only (new conventions not yet documented)
4. Present as individual proposals the user can accept/reject
