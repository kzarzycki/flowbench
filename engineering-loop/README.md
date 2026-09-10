# Engineering loop

One issue at a time, through fixed gates, with no human in the loop. Runs the same
whether a human starts it for one story or a coordinator (`coordinator.md`) starts one
session per story of an epic, and the same in any coding agent — Claude Code, Codex,
or another harness. Where a step names a tool, that tool is one way to do the step;
the step is the contract. Trust files, git and the board — not your memory.

This directory is the layer: this file, `coordinator.md`, `board.sh` (board + claim),
`agent_review.py` (cross-vendor reviewer via omnigent), `LOG.md` (ledger). It lives in
flowbench and governs both repos; `flowbench-scenarios` is a passive sub-repo of the loop.

**Where state lives.** The GitHub issue and the Project board
(https://github.com/users/kzarzycki/projects/1) hold the *state of work*: Phase,
Session, questions for the owner, handoffs. The repo holds *what stays true*: spec,
ADRs (`docs/design/decisions/`) and the ledger `engineering-loop/LOG.md`. Working
artifacts of one item — spec, plan, briefs, Q&A — live in the worktree's gitignored
`.loop/` and die with it; the PR and the issue carry their summaries and the review
verdicts. The repo never holds text that can argue with the code. Nothing is written
twice.

## Repos and branches

- Engine (this repo, flowbench): BASE_BRANCH `master`. Scenarios: `$SCENARIOS`,
  BASE_BRANCH `main` (path per developer, `CLAUDE.local.md`). A fix often pairs both;
  the engine PR merges first, the live run (gate 5) validates both.
- **Always a worktree, never the shared checkout**, as a *sibling* directory
  (`../<repo>--issue-<n>`, branch `loop/issue-<n>-<slug>` from `origin/BASE_BRANCH`);
  a nested path breaks the scenarios→engine relative import. Push with `--no-verify`
  (the pre-push hook leaks GIT_DIR in worktrees, flowbench#49); CI is the gate.
- Live runs need `uv run --extra live` and `ANTHROPIC_API_KEY` unset.

## Claiming

Identity `AGENT_SESSION=<harness>:<id>` — `claude-code:<id>`, `codex:<id>`,
`omnigent:<id>`, `human:<handle>`. Export it at session start; `board.sh` derives it
only for Claude Code (`CLAUDE_CODE_SESSION_ID`), every other harness sets it.
`engineering-loop/board.sh <issue-url> <PHASE>` sets Phase and Session on the board
and, once per session, appends a `session <id> started … parent=<id>` comment.

- Claim (`board.sh … TRIAGED`) before touching a file; run `board.sh` on every phase
  change after. One session, one issue: a coordinator claims the epic, a story
  session its story, a task session its task (`gh issue create --parent <story>`).
- Never take an issue whose Session is set and Phase is not MERGED/PARKED — agent or
  human. Stale (Phase unchanged > 4 h): tell the `parent=` session; it resumes its
  child in that child's harness (`claude --resume`, `codex resume`, omnigent session
  resume) or, failing that, spawns a new one.
- Set `AGENT_PARENT_SESSION` in every session you spawn. Reviewers and in-context
  implementers have no session and do not claim; each review file starts with
  `reviewer: <harness>:<id>`.
- **Handoff** = an issue comment `handoff <session-id>: <what is in flight, worktree,
  next step>`, written before you stop or when context is about to compact. Resuming
  a claimed issue means reading its last handoff comment first. Nothing in the repo.

## Model and effort

Scale effort, not model. Judgment work runs the vendor's strongest model — Fable at
`low` beats a weaker model at any effort; codex at `low` beats a mini model (`minimal`
kills the turn silently on gpt-6-astra/sol, omnigent#6814). Mechanical work (suites,
formatting, log extraction) is sonnet or haiku. Implementers: Fable `low`, re-run at
`high` after a gate failure.

**Reviewers: strongest model, different vendor from the implementer**, never a pinned
model id. Claude implements → codex reviews (via omnigent); codex implements → Claude
reviews. Effort `high` for gates 1 and 3, `medium`/`low` for gate 2 and for
re-reviews of targeted fixes. Same-vendor review only when the other vendor is down
(server, trust gate, quota) — say so on the verdict's first line.

**Dispatching a reviewer.** Write the brief to `.loop/gate-<k>-brief.md` in the
worktree: the gate text below plus the paths of the allowed inputs; never your
reasoning (rule 1). Then get a fresh-context session of the *other* vendor to run it:
1. `uv run --extra live python engineering-loop/agent_review.py --cwd <worktree>
   --harness <codex-native|claude-native> --effort <high|medium> --title "issue-<N>
   gate-<k>" --brief-file <brief>` — works from any harness; prints the verdict.
2. If this session runs under omnigent and has the `sys_*` tools: `sys_session_create`
   on the other vendor's agent with the brief, end the turn, read the inbox (a
   `failed` child may still hold the verdict: `sys_session_get_history`).
3. Your own harness's fresh-context subagent with the same brief — same vendor as
   the implementer, so say so on the verdict's first line.
Verdict → first line `reviewer: <harness>:<id>`, then the text — posted where the
human already looks: gate 1 as an issue comment, gates 2 and 3 as a PR review (open
the PR as a draft after the plan). Nothing else is kept.

## Rules

1. **Generator never approves its own work.** Reviewers see the artifact and its
   inputs only, and must be able to fail you.
2. **Three attempts per gate.** Third rejection: label `loop:needs-human`, comment
   the reviewer's objections on the issue, Phase PARKED, next issue. Never lower a gate.
3. **Unattended.** Where a skill or your own method would ask the user: answer from
   the issue and the code and record question + answer in `.loop/decisions.md` (the
   spec reviewer audits it; a decision that outlives the item becomes an ADR); true
   product judgment → ask on the issue, `loop:needs-human`, park. "User approves"
   gates are the reviewer of that phase.
4. One issue in flight per session. Never merge red. No skipped or weakened tests, no
   force-push.
5. **Follow-ups land on the same PR, before merge** — reviewer notes, a knob to plumb,
   a doc line. A ticket is only for work the owner defers or a finding outside scope.
   A live-run defect in what just merged reopens the same issue.
6. Size (S/M/L) scales the artifacts, never skips a phase: an S spec is a few
   sentences, an S plan 1–3 tasks. Reviewers reject both padding and missing substance.

## Phases

Each phase ends with `board.sh <url> <PHASE>`. Working files (`spec.md`, `plan.md`,
`decisions.md`, briefs) go to `<worktree>/.loop/`, gitignored, never committed. The
`superpowers:*` names below are the Claude Code skills that implement a step; on a
harness without them, do the step as described.

**TRIAGE.** Spawned for one issue: that issue. Otherwise `gh issue list --state open`;
skip epics (containers), `loop:needs-human`, `duplicate`, anything claimed, anything
whose branch already merged. Label untyped issues `type:epic|story|task|bug`; a story
titled `Sxx.y …` gets `--parent <epic>`. Pick: priority labels, then stories of the
lowest in-progress epic in ROADMAP order, then blockers, then small-and-specified.
Cluster duplicates (label the rest `duplicate`, never close). Can't be specced without
inventing requirements → park it. Claim. One-paragraph pick rationale as issue comment.

**SPEC.** Worktree with a green baseline (else stop: `loop:blocked-by-main`;
`superpowers:using-git-worktrees`). Design before code: restate the problem, list the
options, pick one with reasons, write acceptance criteria that a test can check
(`superpowers:brainstorming`, under rule 3; decline its visual companion). Scope
check is binding: several independent subsystems → spec the first, comment that the
issue should split. Spec → `.loop/spec.md`.

**Gate 1 — spec review** (effort `high`). Inputs: issue, `spec.md`, `decisions.md`,
repo read access.
> Reject unless: (a) every requirement traces to the issue or a recorded decision —
> invented requirements are an automatic reject; (b) acceptance criteria are
> objectively testable; (c) `decisions.md` answers are defensible from issue + code,
> not guesses; (d) scope matches the issue. APPROVE or REVISE with numbered objections.
APPROVE → `SPEC_APPROVED`; the full spec goes on the issue as a comment (the worktree
copy is not the record).

**PLAN.** Ordered tasks with exact files and interfaces, each leaving the branch green,
every acceptance criterion mapped to a task and a test (`superpowers:writing-plans`)
→ `.loop/plan.md`.

**Gate 2 — plan review** (effort `medium`). Inputs: `spec.md`, `plan.md`, repo.
> Reject unless: (a) full criterion→task→test traceability, built by you; (b) tasks
> ordered so the branch is green after each; (c) exact paths and interfaces per task
> (context-free subagents execute this); (d) tests would catch the bug, not just the
> happy path. APPROVE or REVISE with numbered objections.
APPROVE → `PLAN_APPROVED`; open the PR as a draft with the plan in its body, so gates
2–3 land there as reviews.

**IMPLEMENT.** One fresh-context implementer per task, TDD, a review after each task
(`superpowers:subagent-driven-development`). "Escalate to the human" = park (rules
2/3). A task that proves the plan wrong → back to PLAN, not an improvised design. All
tasks + full suite green → `IMPLEMENTED`.

**Gate 3 — whole-branch adversarial review** (effort `high`, zero implementation
context; the per-task reviews do not replace it). Brief: a code-review checklist
(`superpowers:requesting-code-review`'s template where available) plus the text below.
Inputs: `spec.md`, `plan.md`, `git diff origin/BASE_BRANCH...HEAD`, repo.
> Also reject if: (a) any criterion lacks a test that fails without the change; (b) a
> test was weakened, skipped or tailored; (c) unexplained changes beyond the plan;
> (d) the diff touches CI config, agent instructions (`AGENTS.md`, `.claude/`,
> `.codex/`) or `engineering-loop/` outside `LOG.md`; (e) docs do not state current
> truth once, in the doc that owns
> it — no strikethroughs, "done (date)", restated facts or narration of how the text
> came to be. APPROVE or REVISE with file:line objections.
Fixes via fresh fix subagents, re-review. APPROVE → `BRANCH_APPROVED`.

**Gate 4 — mechanical.** Suite, lint, build; rebase on `origin/BASE_BRANCH` (code
changed in conflict resolution → re-run gate 3); suite again → `GATES_GREEN`.

**SHIP.** Mark the draft PR ready (`Closes #<N>`, spec and plan summaries in the
body), never merge locally (`superpowers:finishing-a-development-branch` with that
answer pre-made). Standing merge authorization for loop PRs (owner, 2026-07-03) — `gh pr merge
--squash` once CI is green; red CI is a failed gate (fix, rule 2 cap, else park with
the PR open). Merged → `MERGED`, PR link on the issue. The ledger entry ships in this
PR (the scenarios PR when the change is engine-side).

**LIVE (gate 5)** — after a merge touching the runner, a flow, a case or scenario
orchestration; docs-only skips it. From `$SCENARIOS`: `caffeinate -i uv run --extra
live python -m scenarios.swe_planning.run --run-id <id> --n 2`, watched by
`python -m scenarios.swe_planning.watch <run_id> --pid <pid>`. Clean = no permission
prompts, no failed sessions, no artifact_missing, `run.json` lands. Anomaly → issue
labeled `loop:regression` with the watcher output; it outranks everything at the next
triage. Never revert blind — quota and host flaps are environmental.

Then: spawned → stop. Otherwise back to TRIAGE.

## Ledger — `engineering-loop/LOG.md`

Append-only, compressed: **one entry per merged item**, ≤ 8 lines — issue, PRs, what
changed and why in one sentence, live-run id and verdict, and only the lessons that
are new (a root cause, a probe result, a rule that should change). No phase
journaling, no gate play-by-play — the PR reviews and the board already have those.
Read it first when resuming work in either repo. Never rewrite history. Never edit
this file — amendments go through the owner.
