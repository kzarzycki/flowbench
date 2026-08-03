---
name: setup-engineering-workflow-for-apm
description: Configure repository-owned APM instruction sources for the engineering workflow, then compile and audit them with agent-sync. Run before first use of the other engineering skills.
disable-model-invocation: true
---

# Setup Engineering Workflow for APM

Configure the repository-owned source files consumed by APM. This skill writes
only below `.apm/instructions/` and `docs/agents/`, then delegates all compiled
agent-file changes to `mise run agent-sync`.

Never write `AGENTS.md`, `CLAUDE.md`, or another compiled target directly.

## Process

### 1. Inspect the repository

Read enough of the repository to understand its existing conventions:

- Top-level directories and build/task configuration.
- Git remotes and issue-tracker references.
- Existing files below `.apm/instructions/` and `docs/agents/`.
- Root `AGENTS.md` and `CLAUDE.md`, when present, as compiled-output context
  only.
- Domain documentation such as `CONTEXT.md`, `CONTEXT-MAP.md`, and
  `docs/adr/`.

Identify prior output from this skill by the markers:

```markdown
<!-- engineering-workflow:start -->
<!-- engineering-workflow:end -->
```

If a file contains only one marker or contains either marker more than once,
report the malformed file and stop before writing.

### 2. Prepare the two source files

Prepare these exact source paths:

- `.apm/instructions/engineering-workflow.md`, starting from
  [templates/project-guidance.md](./templates/project-guidance.md).
- `docs/agents/issue-tracker.md`, starting from
  [templates/issue-tracker-github.md](./templates/issue-tracker-github.md).

Default the issue tracker to GitHub Issues. When repository evidence or the user
selects another tracker, adapt the marked section in
`docs/agents/issue-tracker.md` to the repository's actual commands and
conventions.

Wrap skill-owned content in the start and end markers. On a later run, replace
only the content between those markers. Preserve every byte outside the marked
section. If the markers are absent, append one marked section without trimming
or reformatting the existing content; if the file is absent, create it with one
marked section.

### 3. Show the proposal

Before writing, show:

1. Every proposed source path.
2. A unified diff for each path, including new files.
3. A note that approval will write the displayed source changes and then run
   `mise run agent-sync`.

Ask the user to approve or edit the proposal. A rejection or requested edit
causes no writes and no sync command.

### 4. Write and compile

After approval, write exactly the displayed marked-section changes. Do not
change any other path.

Then invoke exactly:

```sh
mise run agent-sync
```

Do not substitute an underlying APM command or add another compile command.

If compilation or its audit fails, report the command output and leave the
repository-owned source files for the user to inspect. Do not repair, replace,
or delete compiled targets directly. If it succeeds, report the two source
paths and the compiler result.

A second run with the same choices must propose no source diff. When there is
no source diff, stop and ask for a fresh explicit confirmation before scheduling
`mise run agent-sync` to recheck compiled output. Approval from a prior run or
from the source-change proposal does not carry into this no-diff flow. Do not
rewrite the source files.

<!-- setup-fixture-protocol
version: 1
fixture: tests/fixtures/setup-project
markers:
  start: "<!-- engineering-workflow:start -->"
  end: "<!-- engineering-workflow:end -->"
confirmations:
  source_changes: required
  no_diff_recheck: fresh
source_files:
  - template: templates/project-guidance.md
    destination: .apm/instructions/engineering-workflow.md
  - template: templates/issue-tracker-github.md
    destination: docs/agents/issue-tracker.md
sync_command:
  - mise
  - run
  - agent-sync
-->
