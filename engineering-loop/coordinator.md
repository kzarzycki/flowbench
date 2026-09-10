# Epic coordinator

One session per epic, in any harness, started by the owner: `Read
engineering-loop/coordinator.md and run it for <epic-url>`. It claims the epic, spawns
one loop session (`README.md`) per story — each in whichever harness the owner names,
default the coordinator's own — and never writes code, specs or plans itself.
`README.md` explains claiming and where state lives; Herdr spawns and watches the
workers (`herdr agent start --kind <claude|codex|…>`; the `orchestrating-agents`
skill's `herdr_watch.sh` tells a settled pane from a busy one). Only what is specific
to this project is here.

- **Claim the epic** (`board.sh <epic-url> SPEC`). Stories run in the order the epic
  spec (`$FLOWBENCH/docs/roadmap/epics/E*`) lists them; a story that names a
  dependency waits for its MERGED. Skip anything claimed (agent or human) or
  `loop:needs-human`.
- **Spawn** up to 3 story sessions per vendor at once (sessions of one vendor share
  one subscription and hit the usage limit in the same minute; six Claude sessions
  drained a window in ~4 h). Prompt: `Work <issue-url> per
  $FLOWBENCH/engineering-loop/README.md; worktree ../<repo>--issue-<n>; stop after
  your handoff.` with `AGENT_SESSION` and `AGENT_PARENT_SESSION` exported. Tell the worker it may ask only at
  a fork that changes what gets built or before something hard to undo; you'll read
  its question in the pane. Watch with the skill's `herdr_watch.sh`.
- **Done is the board**, not the pane: Phase MERGED. Anything else after the session
  settles → resume it, do not respawn while its claim stands. BLOCKED → answer only
  from the epic spec, ROADMAP or code (worker records it in `decisions.md`); otherwise
  leave it, note it in your handoff. Two stories reaching GATES_GREEN together: nudge
  the second to wait for the first's merge.
- **Handoff** as a comment on the epic (`handoff <session-id>: …`) after every fleet
  change; the owner reads the board and that comment, nothing else.
- **Close:** all stories MERGED → epic MERGED plus one ledger entry with the epic's
  lessons. A story parked on the owner → epic PARKED with a comment saying what
  needs them.
