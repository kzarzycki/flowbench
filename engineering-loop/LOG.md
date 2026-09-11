# Engineering-loop ledger

Cross-session memory for both repos — flowbench (engine) and flowbench-scenarios — kept once, here in `flowbench/engineering-loop/LOG.md`. One entry per merged item (plus run outcomes and post-mortems), oldest first, append-only; read it first when resuming work in either repo. Format: `engineering-loop/README.md` → "Ledger". Live-run details live in the run dir; gate verdicts on the PR and the issue.

## 2026-07-02 — scenarios#7 swe_planning rework v2 (`7a62c83`; flowbench#6 `93f8adc`)
- `scenarios/swe_planning/` rebuilt as a free-text scenario driven by omnigent agents (fork taxonomy, pydantic manifest, dimension-vector scorer, `claude -p` judge deleted); flowbench gained reasoning-effort, a send() settle loop and `exit_status` in session.json.
- live-001 found three bugs: the flow driver defaulted `turn_timeout_s` to 240 s so plan.md landed after capture (now per flow, default 1800); `_wait_idle` accepted idle before any assistant message (judge.md empty; fix: settle until a NEW assistant message appears); loop exit status was invisible.
- live-002 plain flow implemented the app (flows.yaml now forbids implementation). live-003 the SIMULATOR green-lit implementation ("Go ahead") → simulator.md: never green-light, offers-to-implement ⇒ PLAN_COMPLETE. live-004 clean as intended.
- Judge sees only final plans, so a wrong-guess-then-corrected path is invisible → transcripts to judge (#9). Winner flipped between runs → N>1 (#10/#3).

## 2026-07-02 — flowbench#2 todo_app → run_case port, parked (branch `feat/todo-app-run-case`, 3 commits, never PR'd)
- Port reviewed and approved (removes inspect-ai) but live verify aborted: owner direction — planning is the benchmark, the todo_app planning case is THE focus, feature_flag_service parked. Superseded by the S01.3 re-port (2026-09-08); branch kept as reference.

## 2026-07-03 — scenarios#15 todo_app planning case + flowbench#8 relay protocol (`d2719cd`)
- Case: task.md = "I want a todo app"; knowledge.md MUST/SHOULD/COULD; simulator = realistic technical product owner who speaks needs not values and names the need never the fix; judge grades design soundness + fulfillment of what the user SAID, reading both transcripts (closes scenarios #9). Flows on haiku/medium while tuning.
- Relay protocol: `prime_prompt` once + `relay_prompt` delta only (was quadratic re-send of system+tail every simulator turn). Verified in todo-002: prime 2962 chars once, deltas ~800.
- Reasoning-effort is a string passed through; Claude levels are low/medium/high/xhigh ("med" is not one).

## 2026-07-03 — flowbench#9 #10 #11 #12 driver settle/retry stack (`3112034` … `5e8d005`; scenarios#16)
- todo-003: bridge reported idle while the agent was still writing → 60 s settle cap → stale idle → duplicate relay → injection hit a busy terminal → `runner_error`, run dead. #9: settle to the full turn budget; idle without a new reply on expiry ⇒ `timeout`, never stale idle.
- todo-004: one `httpx.ReadError` in a poll killed the run → #10 `_read_retry` on read-only polls (4 attempts, backoff); sends are never retried blindly (double-delivery risk).
- flowbench #7: projects = `omni_project` label (probed via create → `GET /v1/sessions/projects`). #11 driver `session_title` + `project`; scenarios #16 project `swe_planning/<run_id>`, titles `flow:`/`sim:`/`judge:`.
- todo-005: second lying-idle variant (idle between an interim message and pending tool work) → #12: send() retries injections the server reports "not delivered" (never reached the agent; 3×30 s) and the DONE-token loop grace-polls the artifact ≤60 s.
- Ops: never `git add -A` in the scenarios repo (sweeps `.claude/`); check the current branch before committing after any failed command chain.

## 2026-07-03 — flowbench#14 #15 permission prompts were the "artifact lands late" cause (`dced263`, `3cb338e`; runs todo-006/007/008)
- todo-006 died of subscription QUOTA, not code: flows share the operator's Claude subscription. Check quota before long runs.
- todo-007: plan.md landed exactly when the user manually approved a Write prompt; the bridge routes permission prompts to the omnigent UI with a 24 h timeout, so an unapproved tool call burns the turn budget. #14 seeds workspace `.claude/settings.json` with `acceptEdits`.
- todo-008: superpowers stalled its whole budget on a Read prompt (skills read outside the workspace cwd) → #15 also allows Read/Glob/Grep + file-work bash.
- `uv run` re-synced the env and dropped `omnigent` → launch live runs with the extra (`--extra spike`, today `--extra live`).

## 2026-07-03 — flowbench#17 permission asymmetry root cause (`dc3e7f2`; flowbench#16 `943eeb9`; scenarios#22 `3277fb2`, #23 `d3c12cd`, #24 `1d77d5e`; runs todo-009..011)
- todo-009: first fully clean unattended run; first merit verdict (superpowers).
- ROOT CAUSE (todo-010): omnigent `bundle_skills.py` maps skills "none" to `--setting-sources ""`, so Claude Code loads NO settings files, including the seeded workspace one → plain prompted while superpowers auto-accepted: a permission asymmetry riding the skills channel. #17: permissions ride `terminal_launch_args` (`--permission-mode`, `--allowedTools`), identical per flow; settings seeding removed.
- #16 `context_tokens` captured from the `omnigent.last_context_tokens` label. #22 per-run report.html, judge `SCORES` lines, A/B swap on even trials with canonical aggregation. #23 `_project()` skips `trial-XX`. #24 `watch.py`: permission prompts, server ERROR lines, TRIAL DONE / RUN COMPLETE; trial-qualified titles.
- todo-011 (n=2): zero prompts (watcher-verified), superpowers 2–0 including the B position; context ~46k vs ~32–37k tokens.

## 2026-07-03 — scenarios#25 #29 loop.md amendments, journals unified (`fa0c5cb`; flowbench#18 `bba4b0e`, #20)
- S/M/L sizing scales spec/plan LENGTH, never skips phases; Phase 9.5 live-validation gate (run + watch.py); ONE ledger = this file, both CLAUDE.md files point here.

## 2026-07-03 — scenarios#3 N>1 runs (PR #19); scenarios#18 offline-suite hang + CI (PRs #20, #21)
- #3: `--n` runs + majority-vote aggregation. #18: flowbench's 60 s artifact grace-poll stalled the offline fakes → `artifact_grace_s` threaded through `run_case`; #21 ci.yml clones the flowbench sibling and fixes `test_default_runs_root_is_sibling_of_repo` (string check tripped on the runner's `work/<repo>/<repo>` nesting) → scenarios CI green for the first time.
- Owner granted standing merge authorization (loop.md Phase 9). The auto-mode permission classifier blocks agent-authored `gh` writes regardless; explicit Bash allow rules in `.claude/settings.local.json` bypass it and must be written by the user.
- An implementer cwd-slipped and committed to the main checkout: briefs require `git rev-parse --abbrev-ref HEAD` before commit; `git reset --keep` restores main. Background reviewer task IDs do not survive a session resume — re-dispatch.

## 2026-07-03 — scenarios#26 aggregate report for n>1 (PR #31 `0a32c6e`); scenarios#14 contradicting requirements (PR #32 `0fa4084`)
- #14: a contradiction pair in todo_app knowledge.md; simulator volunteers both halves and withholds the resolution until confronted; judge emits `conflict=` scores. Watch item: an agent that asks near-zero questions can collide "volunteer early" with the PLAN_COMPLETE-only reply rule.
- Backlog closed with evidence comments: #17 (unattended permissions), #12 (report renderer), #8 (judge scores).

## 2026-07-03 — scenarios#30 codex flow via vendored skills (PR #33 `f1ebb65`; flowbench PR #21 `4e84a74`)
- codex-native ran (gpt-5.5) but had NO superpowers: superpowers 6.1.1 dropped `hooks-codex.json`, and omnigent's codex skill staging scans only `<bundle>/skills/` + `~/.codex/skills/`, never `plugins/cache/`. Decision 2a: vendor the superpowers skills into the repo; BOTH flows load via bundle `skill_dirs` with `skills: none`.
- flowbench CI green for the first time: `uv sync` never installed extras (pytest absent on the runner) → `--extra dev --extra spike`; the demo eval.py resolves superpowers from the host plugin cache at import → skipif when absent.

## 2026-07-04 — scenarios#34 N-way judging (PR #38 `46404f8`)
- Labels per trial, name-keyed aggregation, rotation `(k-1)%N`; todo_app runs 3 flows (claude/codex superpowers, plain; codex `reasoning_effort: low`).
- Live 001/002 crashed on omnigent "terminal did not become ready within 30.0s" during a simulator turn — `OmnigentModel.generate` had no retry (flow sessions recover through omnigent's own retries). → #39.

## 2026-07-05 — scenarios#36 codex review gates (PR #37 `eadf667`); scenarios#39 generate retry (PR #40)
- Gates 1–3 dispatch cross-vendor codex-native reviewers via `scripts/codex_review.py` (thin `OmnigentDriver` wrapper); a Claude subagent is the explicit fallback. `verdict_from()` trusts emitted text even when codex-native flips to `failed` right after its final message.
- #39: `OmnigentModel.generate` trusts only fresh text (staleness sentinel), retries failed+empty/stale turns (3 sends, 30 s apart); timeout still raises immediately.

## 2026-07-06 — flowbench#22 alpha roadmap (`0d740d0`)
- `docs/roadmap/`: vision, current-state audit, target architecture, M0–M9, epics E00–E04, proposals P01/P02, verification procedures V1–V8. Key non-finding: the driver's `sessions._http` reach-in is FORCED — the public client `create()` cannot pass `terminal_launch_args`.

## 2026-07-07 — flowbench#23 P03 evaluation-quality proposal (`80df4ef`)
- A colleague's 5-dimension × 15-sub-metric planning-grading framework adapted as a cross-cutting thread: grading = a skill the judge READS as rubric (runs no code) + numeric scorers harness-side, so the judge stays tool-less; per-case `grading.yaml`; comparative near-term, absolute per-flow scorecards in Phase 2.

## 2026-08-20 — flowbench#37 #38 repo hygiene after the checkout move (scenarios#46)
- Both checkouts moved (engine → `dev/agents/flowbench`), silently breaking every relative doc pointer, the flowbench `.venv` shebangs (pre-push pytest hook dead), and CI `push.branches: [main]` (flowbench's default is `master`; no post-merge run had ever fired).
- Policy: no per-developer checkout path in any tracked file — docs say `$SCENARIOS`/`$FLOWBENCH`/`$RUNS`, the concrete path lives in untracked `CLAUDE.local.md`. Read #38 (not #37) for the convention.
- Parked branches: flowbench `docs/tau2-inspirations` (`fcb7d40`, τ²-bench research: pass^k, simulator-error rate, termination taxonomy) and `feat/todo-app-run-case`.

## 2026-09-07 — flowbench#41 E01 S01.1 generic runtime into the engine (PR #43 `517fd5c`, also closes #3)
- `flowbench.run` (`run_case`/`run_case_n`, `omni_factories`), `flowbench.model` (`SessionModel`), `flowspec`, `transcript`, `runner.judge`, `report.run_report`, `watch` (`RunWatch`), `testing`; `runs_root` and `scenario` are REQUIRED kwargs; run.json gains `"scenario"`; pyyaml is a core dep. Engine suite 87 → 160.
- `last_json_object` rewritten "while moving" scanned backwards and could not resolve escapes (fuzz regression vs the raw counter) → forward candidate-start scan, 100k fuzz clean. A fix-while-moving is where a move stops being behaviour-preserving; give it its own fuzz.
- Also merged: flowbench #40 (flow-is-the-full-configuration decision record). Sonnet implementer, opus/Fable reviewers: keep that split.

## 2026-09-08 — scenarios#57 E01 S01.2 scenarios consume the engine (PR #58 `fc221f8`; #60 `52184c1`; #62 `eb38ff7`; flowbench#45 `6e70650`)
- swe_planning `run.py`/`watch.py` are thin CLIs over `flowbench.run`/`flowbench.watch` (−2014/+69); flowbench #45 drops the driver's alias re-exports.
- Live todo-012: the feature_flag_service superpowers flow said `skills: superpowers` (host plugin, disabled on this machine) → "Unknown skill". A flow naming a host plugin is hidden configuration; vendored `skill_dirs` or nothing (#60).
- Live todo-013 `--n 2`: superpowers on opus/xhigh was cut mid-writing-plans at 2253 s. The cut is the per-turn `turn_timeout_s` (checked in the driver), not `deadline_s` (checked only between turns). #62: both flows `turn_timeout_s: 3000`, `--deadline-s` (default 3600) on `swe_planning.run`. `scores: {}` is by design here (this judge.md has no SCORES contract).
- Ops: a Python background watcher was OOM-killed → shell Monitor loops; zsh `for path in …` clobbers `$PATH`; `gh issue create --label` with a missing label fails silently; `git fetch && ff` before every live run; `.claude/worktrees/<x>` breaks the relative engine dep → worktrees go to a sibling dir.

## 2026-09-08 — flowbench#2 E01 S01.3 + S01.4: todo_app on run_case, Inspect gone (PRs #48 `f054976`, #50 `b663b3a`; scenarios#64 `a2a720f`)
- `run_case(done_token=, score_flow=)` writes `<flow>/scorecard.json` (a raising scorer becomes `{"error"}` and a `compare` FAILED column); judge + report.html only when the case has `judge.md`. todo_app is a plain-file case with superpowers 6.3.0 vendored (all 14) and `scoring.py`. `inspect-ai`/`subscription_model.py` deleted; extra `spike` → `live`; httpx a base dep; wheel ships `src/flowbench` only.
- Engine tests must not import a scenario (decision 14). Found: `resolve_invoker` console-script bug → #46; the pre-push hook's `GIT_DIR` leaks into `git_init_repo` inside a worktree → #49.
- Live `coding_workflow/todo-app-001`: both flows waited out the 1800 s cap on an invisible Bash permission prompt (`rm -f … && python3`, outside the allowlist) → #52. `superpowers_used` keyed on the `superpowers:` namespace but vendored skills are `claude_code:<name>` → #53 name-match.
- Live todo-014 `--n 2` (validates #62): superpowers 2–0, the reverse of todo-013 under the 1800 s cap, but exiting `running` at ~3300 s — on opus/xhigh the plan-writing turn is effectively unbounded. The cap is a first-order benchmark variable and is declared per case in flows.yaml.
- Ops: zsh `echo ======` is equals-expansion (use `---`); quote heredocs; stage paths explicitly in the engine repo (`git add -A` sweeps the untracked `.code-workspace`).

## 2026-09-08 — flowbench#52 bypassPermissions (PR #55 `2ea32b7`); flowbench#54 stall watchdog (PRs #57 `7e696c7`, #58, #63; #60)
- Decision (owner): `bypassPermissions` for every flow in every case; launch args are exactly `--disallowedTools AskUserQuestion --permission-mode bypassPermissions`; `ALLOWED_TOOLS` deleted. A prompt has nobody to answer it, so the only honest postures are never-prompt or detect-and-stop; `auto` rejected (a second non-deterministic model between flow and tools).
- Watchdog on omnigent 0.13.0.dev0 signals: `pending_elicitations`/`terminal_pending` on two consecutive polls ⇒ `stalled/prompt`; `updated_at` heartbeat silent for `stall_s` (300 s, per flow) ⇒ `stalled/no_progress`; session records `stall_reason` + `pane_tail` (tmux `capture-pane`, 5 s `wait_for`). Never auto-answers.
- #58: `omnigent_client.Session` (the detail object) has neither `updated_at` nor the elicitation count — they exist only on the list item; `_wait_idle` polls the raw `GET /v1/sessions/{id}`. A signal proved on one endpoint is not proved on another; probe the exact call the code makes.
- #63: a healthy simulator turn shows `pending_inputs` for one poll → two-poll arm. Process rule 7: gate/probe follow-ups land on the open PR; ledger entries ship in the item's paired scenarios PR. #60: todo_app `turn_timeout_s: 3000`.
- Live todo-app-002: acceptance 1.0/1.0, E01 done. todo-app-003 inconclusive: Mac idle sleep killed the claude session (`native_turn_error: computer went to sleep`) → wrap every live run in `caffeinate -i` (lid close still sleeps). todo-app-004: watchdog live gate PASSED, 0 false stalls over 66 min; grader died on lid-close → hand rescore → `--rescore` need (#59).
- Ops: a peer session switched the shared checkout's branch mid-gate → sibling worktree mandatory in both repos (scenarios #67); `uv sync --extra dev --extra live` in each fresh worktree before `uv run ruff`; `gh pr merge --auto` is disabled on scenarios.

## 2026-09-08 — scenarios#68 flowbench as a git source; flowbench#42 #56 apm 0.30.0 pin (scenarios#66; dotagents#19; agent-skills#34)
- Homebrew apm 0.29.1 shadowed the mise pin 0.26.0, so `agent-sync --frozen` diverged and pre-push hooks failed. Pin `github:microsoft/apm = 0.30.0` in all repos, brew apm removed, mise shims first in PATH; VPS `~/.bashrc` PATH block above the interactive guard. `apm.yml ^0.4.0` restores 26 skills incl. `implement-spec`.
- #68: `[tool.uv.sources] flowbench` is a git source on `master` pinned by `uv.lock` (supersedes the 08-20 "one tracked path stays"); CI clone step removed; dependabot uv jobs resolvable. Bump with `uv lock --upgrade-package flowbench`; for simultaneous engine work `uv pip install -e <checkout>` after sync. The lock records which engine a scenarios commit was gated on.
- `jdx/mise-action` "latest" resolved to a mise tag with no release asset → pinned `2026.9.2`.
- A `.git/hooks/pre-commit` in pre-commit "migration mode" silently refuses every commit — `git log -1` after every scripted commit; `pre-commit install -f --hook-type pre-commit` repairs it.

## 2026-09-09 — flowbench#59 run.json artifact vocabulary + `--rescore` (PR #74; scenarios#78)
- `plans_missing`/`plan_lines` assumed every deliverable is a plan; todo_app's `tasks.json` is runtime state created by `acceptance.py` AFTER capture, so two acceptance-1.0 flows read as total failures. Now `artifact_name: str | None` on `run_case`/`run_case_n`/`omni_factories`: set → `artifact_missing` + `artifact_lines`; `None` → neither key and no grace poll. `run_case` rejects `artifact_name=None` + `judge.md`; `flow_card` guards the artifact read.
- `rescore_run(case_dir, run_root, *, score_flow)` + `--rescore <run_id>`: re-runs `score_flow` from `<flow>/session.json`, rewrites `scorecard.json` and `flow_stats.score_error`, never touches `session.json`/`transcript.md`; a flow gone from flows.yaml is recorded as `KeyError`. Validated on a copy of todo-app-004.
- `loop.md` was a reader too (Phase 9.5's "no plans_missing") — grep for executing procedures, not only code. `cp -R` of a run dir does not detach the embedded git worktree (`gitdir:` still points at the original). This repo's CI gate is diff-cover 100 %, not total coverage.

## 2026-09-09 — flowbench#62 onboarding docs + meta-harness decision (PR #66; addendum #72 `a02afd1`)
- `docs/onboarding.md` and `docs/design/decisions/2026-09-09-omnigent-as-the-meta-harness.md`. Topology: the `live` extra installs only the PyPI CLIENT into the venv; the server runs from an editable uv-tool checkout (0.13.0.dev0 then) — the pane-scanning bridge that runs is the server's.
- `scripts/patch_omnigent.py` deleted: upstream anchors prompt-ready detection on the input-box rule (`_is_box_rule`), and todo-app-001..004 ran unpatched.
- Readiness probe = `GET :6767/v1/hosts` for an `online` host with `configured_harnesses["claude-native"]`. There is NO health/version endpoint: unknown paths return the web UI with HTTP 200.
- herdr rejected as meta-harness: no per-session skill/MCP bundle (skills would come from host config — the hidden asymmetry the benchmark forbids), pane text instead of a normalized transcript, TUI-derived state machine. `HERDR_ENV=1` is herdr's guidance, not an API gate (`env -u HERDR_ENV herdr agent list` works).
- `deadline_s` is the run-level budget (`--deadline-s`); only `turn_timeout_s`/`stall_s` come off the flow. Process: a silent reviewer is not an absent one — wait for it or record the gate as skipped; never let the merge decide by default.

## 2026-09-09 — flowbench#69 "web UI lost per-run grouping": not reproducible (PR #71)
- All 371 sessions carry `labels.omni_project`; the server's `GET /v1/sessions/projects` returns label folders (`"id": null`) beside first-class ones and dual-reads the legacy label; the UI groups. Likely cause: a degraded `session_updates` websocket after a server restart (fork fix `60dca164`) — hard-reload. #71 adds `project` assertions for the sim and grader factories (mutation-checked).
- Triage rule: probe `GET :6767/v1/sessions/projects` before touching the driver; recorded in `docs/knowledge/omnigent.md`.

## 2026-09-09 — flowbench#49 GIT_* leak (PR #70 `871419a`); flowbench#46 acceptance invoker (PR #73 `4a05a2e`)
- #49: `git_init_repo` inherited `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` from the pre-push hook and redirected the nested `git commit` onto the outer repo (once flipping the shared checkout to `core.bare=true` and corrupting its index; `git config core.bare false` repairs). Fix strips every `GIT_*` key; the test snapshots the outer index bytes and runs `status --porcelain`. The `--no-verify` push workaround is obsolete.
- #46: `resolve_invoker` string-matched `"No module named todo.__main__"`; a console-only build says `"No module named todo"`, so a faithful build scored 0.0. Now a `find_spec` probe decided on returncode. The console-script shim discarded `_entry()`'s return (every shim app exited 0 = a free 3/7) → `raise SystemExit(_entry())`.
- Ops: two implementers in ONE worktree is a data-loss hazard (files swept into the other's amend). One worktree per branch per agent.

## 2026-09-09 — flowbench#64 E02 S02.1 `flowbench/types.py` (PR #75 `5418488`)
- `TurnStatus(StrEnum)` with five members (idle/timeout/failed/running/stalled — `running` surfaces when the per-turn cap hits mid-work), typed `TurnResult`, `UserModel`/`Completion` protocols. `StrEnum`, not `(str, Enum)`: only `StrEnum` formats as the bare value in f-strings (json.dumps hides the difference). An undocumented server status passes through verbatim, no coercion — narrowing is S02.6.
- `uv run` silently undoes `uv pip install -e` (it re-syncs the locked env first), so a V2 gate against the git-pinned engine validates the wrong code. Use `uv run --with-editable <engine>` or `uv run --no-sync`, and print `flowbench.__file__`.
- A stale base is a gate failure: #68 had rewritten `_wait_idle`, the exact sweep region; the rebase left `TurnResult.child_busy` dead (dropped). Touching an untested line pulls it into diff-cover's scope.

## 2026-09-09 — flowbench#67 todo-app-004 post-mortem: the hour was the driver, not superpowers (PRs #68 `d41cb1b`, #76 `668defb`)
- Of 3961 s the app was complete at 30.7 min; 33.5 min were the driver: `_list_items` read one 200-item page, so past item #200 the settle check's assistant count froze and every turn burned the full `turn_timeout_s`. The loop's `Continue.` nudge sentinel collided with the simulator answering `Continue.` (relay cursor froze, quadratic resend) and ~25 nudges ate ~50 items.
- #68: `_list_items` pages with `after` (closes #4); idle main + busy child (`GET /child_sessions`, paged) counts as running, children's `updated_at` join the heartbeat; the nudge path deleted outright.
- Live todo-app-005 false `stalled/prompt`: `pending_inputs` means "un-consumed web-composer user messages" (our own queued inject), never a human prompt. #76: `pending_inputs` out of `_PROMPT_KEYS`; after children clear, idle is reported only once the wake-up turn ran or `child_wake_s` (20 s) passed; a cap during that wait is `timeout`.
- Live todo-app-007: both `idle`, acceptance 1.0/1.0, superpowers 665 s (was 3961). The child-wait path is covered by unit tests + 005's failure shape, not yet by a passing SDD-shaped run.
- Ops: launch live runs with `nohup … &` (harness background jobs die at 600 s or to the memory reaper); handoffs are issue comments, not ledger entries; `codex_review.py` once printed an intermediate message as the verdict — read the session.

## 2026-09-09 — flowbench#65 #77 dependabot backlog cleared (`7ac3780`, `1324132`); flowbench#78 filed and retired
- #30/#31 each rewrote `uv.lock` and conflicted with each other → one manual relock; #33 was red only from a `setup-uv` v8.2.0 manifest-fetch timeout. Bound the lockfile diff in acceptance criteria (a `secretstorage` marker hunk slipped through unnoticed).
- omnigent-client 0.1.1 → 0.2.0 (#77): `omnigent` pins `omnigent-client==<its own version>` so both pins move together; the driver's reach-ins are unchanged across the bump; 0.2.0 defaults `Origin: omnigent://internal`. The live server is 0.13.0.dev0, so the pins sit ~12 minors behind by design until E02 S02.5.
- deps-002 went red (superpowers `stalled`, simulator answering `Continue.`) → #78 against #68, but #76 had merged 3 min after the run started and fixes exactly that gap. Closed as fixed, no duplicate written. deps-003 clean: superpowers `idle` at 489 s — `deadline_s` is no longer the binding budget on this case.
- Rules: a live gate is valid only against the master it ran on; before fixing a live-run regression, run `git log <base>..origin/master`.

## 2026-09-09 — flowbench#80 E02 S02.2 driver split (PR #84 `3e8f77e`; scenarios#84)
- `runner/driver.py` → `flowbench/driver/{base,bundle,omnigent}.py` (`bundle.py` = pure functions of a `BundleSpec` protocol); `runner/loop.py` → `flowbench/loop.py`; old paths are import-only shims for one release, pinned by `tests/test_compat_reexports.py` (identity + `ast`). Goldens captured from a detached `origin/master` worktree: `render_config` strings, tar members as sha256.
- Purity test calls the bundle functions with a `SimpleNamespace` of exactly the protocol fields, so any extra attribute read raises. A rename costs the whole file's diff-cover — `start()` got its first tests (the net S02.5 needs). Epic's "~350 lines" amended to 484 with the reason (settle machinery from #68/#76).
- `verification.md` makes a live run mandatory for any driver/loop change; the blanket rule wins over a story's Verify line. Live `swe_planning/s022-0909-0959`: claude/codex/plain all idle, winner codex.
- `detect-secrets` flags a bare sha256 in fixtures or markdown tables: derive it in code, or `# pragma: allowlist secret` in docs.

## 2026-09-09 — flowbench#88 issues hierarchy + Kanban; flowbench#121 M1 closeout
- Epics E00–E07 = flowbench #89–#96 (`type:epic`), stories are sub-issues (#97–#119 + #41/#2/#64/#80, scenarios #57). Board https://github.com/users/kzarzycki/projects/1 spans both repos with `Status`/`Kind`/`Phase`; the loop runs `board.sh <issue-url> <PHASE>` on every phase write. Rejected: Plane/Linear/beads (second source of truth), ZenHub-class overlays.
- #121: E01 marked done in roadmap/epic, #90/#102/#2 closed. The pre-push hook ran plain `uv run pytest` — a fresh worktree venv lacks the extras and 52 async tests fail → hook syncs `--extra dev --extra live` like ci.yml.
- Kept on purpose: flowbench `feat/todo-app-run-case`, `docs/tau2-inspirations`; scenarios `docs/erratum-bteq-xport-findings`, `--unpin` (PR #85), `--dwh-divergence-traps` (#47).

## 2026-09-09 — flowbench#105 E02 S02.5 part 1: omnigent private-API inventory (docs-only)
- `docs/design/omnigent-api-inventory.md`: R1 raw `POST /v1/sessions` via `sessions._http` — blocked-upstream (no client version sends `terminal_launch_args`); R2 `_sessions_chat` import — migrate-now; R3 `omnigent.host.daemon_launch` — keep + `# UPSTREAM:`; R4 raw `GET /v1/hosts` — keep. The watchdog GET must stay raw (0.2.0 `Session` lacks `updated_at`/pending signals).
- `rg` honours `.gitignore` and silently skips `.venv` — use `--no-ignore`. Schema acceptance ≠ behaviour: 0.2.0 accepts `host_id` in create metadata and ignores it; launch-on-create exists only at HEAD. Upstream ask filed as omnigent-ai/omnigent#6822.

## 2026-09-09 — flowbench#103 E02 S02.3 one retry policy, one budget per send (PR #126 `f4cb85e`; scenarios#97)
- `OmnigentDriver.send` owns the retry policy (five-row table in `docs/design/runner.md` → "Send/retry policy") under ONE `asyncio.timeout(turn_timeout_s)` with soft deadline checks before every wait and inject; expiry ⇒ `TIMEOUT`, never re-sent. Rows 1/3 are the only re-sends (`model_error` non-retryable); row 2 FAILED + new NON-EMPTY text ⇒ `IDLE, flaked=True` (`session["flaked_turns"]`); `settle_timeout_s` and the `SessionModel.generate` retry removed (generate = send, raise on non-idle or empty).
- Old worst case per send was `(1+retries)×3×T + waits` = 36 090 s on todo_app's T=3000 inside a 3600 s deadline. Gate 3 found `_resend_allowed` reading labels off non-2xx bodies (401/404/500 each authorized four sends).
- Gate 1 parked after five codex rounds, then closed by owner authority; roadmap files carry no done-marks or policy copies (flowbench #122). Test the gate, not the outcome: stub the next step to raise. `detect-secrets` rejects a 40-hex SHA in `state.json` — store the short SHA.
- Live: `coding_workflow/s023-1653` acceptance 1.0/1.0, 0 flaked; `swe_planning/s023-plan-1727` all idle, winner codex.

## 2026-09-09 — flowbench#105 E02 S02.5 part 2: the migrate-now set (PRs #129 `620b16b`, #130 `1a6a714`)
- `SessionsChat` from the `omnigent_client` root export; `_resend_allowed`/`_context_tokens` read `sessions.get(id).labels` under `asyncio.timeout(60)`; `# UPSTREAM: omnigent-ai/omnigent#6822` on R1 and R3, which stay raw with the `live` pin bump.
- The SDK is not a drop-in for raw httpx: `omnigent_client.raise_for_status` returns for any status < 400, and `OmnigentClient` ignores its `timeout` argument (600 s SSE budget). Diff the SDK's error and timeout semantics, not just the field it returns.
- Live attempt 1: the Claude session-limit banner was read as a completed reply 18 times, flow ran 30 turns to `failed` → #131. Attempt 2 `coding_workflow/s025p2-620b16b-r2` PASS, `context_tokens` populated via the SDK read.
- Ops: a Claude Code `Bash` background job dies at 600 s → `nohup`; an orphan session is disposed with `DELETE /v1/sessions/{id}`.

## 2026-09-09 — flowbench#104 E02 S02.4 artifact probe out of the driver (PR #132 `85e6f33`)
- Driver lost `artifact_name`/`artifact_path()`/artifact capture keys; `run_agent_session(artifact_probe=)` polls in a worker thread every 2 s under `asyncio.timeout(artifact_grace_s)`; `run.py` owns `find_artifact`; `omni_factories(scenario, *, git_init=False)`; the `__none__` sentinel is gone. Contract: `docs/design/runner.md` → "Artifact probe".
- A fake that stops "existing" costs a real wait: the suite went 14 s → 9 min until every `FakeDriver` site passed `run_dir=`. Re-apply (rerun the script on upstream's file), don't merge, a conflicted mechanical test edit. `scenarios.coding_workflow` lives in the engine repo: launch its live run from the engine checkout with `--runs-root $RUNS/coding_workflow`.
- Live `coding_workflow/s024-1925` 1.0/1.0, `artifact_exists: false` (no-probe path); `swe_planning/s024-plan-2010` all idle, `artifact_exists: true`, winner codex.

## 2026-09-09 — flowbench#106 E02 S02.6 error taxonomy (PR #133 `512e711`)
- Every `except Exception` is narrow or a waiver with the reason on the line, and every swallowed exception is logged at DEBUG. Label reads catch `(OmnigentError, httpx.HTTPError, TimeoutError, KeyError, ValueError, TypeError, OverflowError)`: `Session.from_dict` coerces non-dict labels to `{}`, raises `KeyError` on a partial body and `OverflowError` via `int()`. Resend row 1 requires a `str` message. `BLE` on in ruff.
- A rebase that conflicts in the changed region is a substrate change: re-spec and re-run gates 1–3 (the SDK migration made half the malformed-body cases unreachable). Test through `httpx.MockTransport` + the installed `SessionsNamespace`; keep doubles for injected failures only. Regenerate a document whole rather than splice it.
- Live `coding_workflow/s026-1954` 1.0/1.0; `swe_planning/s026-plan-2012` all idle, winner codex. Left for the owner: sharpening the RUNNING-vs-TIMEOUT race at the cap is a loop-semantics change the epic lists as a non-goal.

## 2026-09-10 — flowbench#131 a CLI limit banner is `QUOTA`, not a reply (PR #134 `f8d39b6`)
- Claude Code emits `You've hit your session limit · resets HH:MM (…)` as an ordinary assistant item, the session flips `failed`, and every `omnigent.last_task_error_*` label stays empty. Retry row 2 read it as a completed turn; the simulator (same subscription) echoed its own banner; 30 turns traded (`s025p2-620b16b`).
- `TurnStatus.QUOTA`; `transcript.is_quota_banner` (anchored to message start, ≤240 chars, banner wording pinned — only the Claude wording is evidence-backed, codex-native unverified); checked before every other row, returned with the banner as text, never re-sent; the loop stops with `exit_status: "quota"`; `RunWatch` reads a session's last item only when `updated_at` moved and prints one `QUOTA:` line. Why not STALLED: a quota turn completed and lifts on its own — a different operator action. Sim/judge quota surfaces as `SessionModel` raising; wait-for-reset is deliberately not taken.
- A new HTTP read inside a tick loop must be gated on a change signal or it is one round-trip per session per tick, and tests that stub the list but not the new seam go online silently — prove offline by forbidding `urlopen`.
- Live `coding_workflow/s131-f8d39b6`: 0 false positives over 19 real turns; superpowers then `stalled/prompt` on a permission card despite bypassPermissions → #135.

## 2026-09-10 — flowbench#135 post-mortem: the permission card was a server restart, not Claude Code
- Not the bridge flag (argv identical to a clean session) and not Claude Code 2.1.267: the omnigent server restarted at 06:20:35, 24 s before the stall — the `dev.zarz.omnigent-autosync` launchd job re-synced the editable tool install to 0.14.0.dev0. The bridge relays every `PreToolUse` policy evaluation to the server; in the gap it failed *ask* by design (`policy_eval_relay_failure … falling back to fail-closed`), and Claude Code honours a hook's ask over the permission mode.
- The job's "agent active" guard watched `~/.omnigent/logs/host-runner/*.log`, empty since 2026-08-19. Fix in fork `mine` `b0674b43` + `889a60b3`: `busy()` asks `GET /v1/sessions` (any session touched < 10 min, audit excluded — status alone is no signal, parked sessions stay `running`), a sync under active sessions writes `restart-pending` for the first quiet tick; 4 h starve rule kept. flowbench docs: onboarding live-run rule "No server restart under a run".
- Check `ps -o lstart -p $(cat ~/.omnigent/local_server.pid)` against the stall time before reading changelogs; the editable tool install changes hook code under running sessions the moment the fork re-syncs. Live `s135-repro-1`: both idle, 0 stalls, 0 prompts.
- E02/M2 closed: S02.1 #75, S02.2 #84, S02.3 #126 `f4cb85e`, S02.3b #67, S02.4 #132 `85e6f33`, S02.5 #129/#130 `620b16b` (R1/R3 + `live` pin bump blocked on omnigent-ai/omnigent#6822), S02.6 #133 `512e711`, #131 #134 `f8d39b6`. Next: M3 (E03, flow schema v1 first).

## 2026-09-10 — flowbench#143 a phase is written from the artifact that proves it (PR #145)
- `board.sh CLOSED` writes `Status=Done` and skips the Phase edit, so a story closed without shipping keeps the last phase it actually reached; the README's `## Phases` preamble states the rule once. No new Phase option — `Status=Done` plus the last true Phase already say "closed, never shipped", and a new single-select value is a schema edit every reader must learn.
- `MERGED` is written from the commit the story's own PR landed on the base branch, found by the PR's head branch: SHIP squash-merges, so "a merge commit on the story's branch" — the wording the incident report proposed — never exists. Gate 3 caught it; a rule has to name evidence the loop's own shipping step produces.
- First runnable check for `board.sh` (`tests/test_board_sh.py`, `gh` stubbed on `PATH`). Deriving an expected option id from a sibling keyword is a circular oracle; anchor it. `[ -n "$x" ] && cmd` does *not* exit under `set -e` — the `if` is style, not necessity.
- Prose criteria can be tested after all: assert placement and uniqueness (`count == 1` inside the owning section), which also catches a restatement elsewhere. Gate 2 excused this criterion; gate 3 was right to overrule.
- No live run: the diff touches no runner, flow, case or scenario orchestration.

## 2026-09-11 — flowbench#149 E04 S04.9 antigravity-native (agy): a case can run on Gemini 3.8 Flash (PR #154)
- `_resolve_claude_host` → `_resolve_host`, matching `self.harness`; error names it. `is True`, not truthiness: a host reports each harness as `true`, `false` or the diagnostic STRING `"binary-missing"` (six of them there), and the string is truthy. `session_metadata` gains an `antigravity-native` row with agy's unattended flag — omnigent's runner-owned launch passes `permission_mode=None, headless=False`, so the bundle's `permission_mode: bypassPermissions` never reaches agy and the launch args are the only route.
- Probe first, design second: 3 turns with only the host lookup patched gave turn 1 `stalled`/empty (the todo-app-001 freeze, now proven not assumed), turn 3 `<<DONE>>`. That settled the open question — the loop, transcript reader and send/settle need no harness branch — before a line was written.
- What a harness's bridge does NOT carry is now stated and warned about, not silent: bundle skills/MCPs reach only the Claude bridges (`inner/bundle_skills.py`; agy seeds the HOST's global skills instead, #151), and agy drops `reasoning_effort` (effort is in the model id). Two capability sets, not one — codex honours effort and gets no bundle. Warning not raise, because `agent_review.py` sends effort unconditionally (#152) and gate 3 forbids editing it; the reject belongs to Flow schema v1.
- **`antigravity-native` is a qualified cross-vendor reviewer** — gates 1–3 ran on it while codex was out of quota. It rejected its brief twice with findings the author had missed. Narrower than "it works": read-only review turns pass, tool-writing turns stall, so it needs a written brief with every input as a LOCAL FILE — a brief saying "run `gh issue view`" stalls the turn. Reported on #147.
- Gate 2 caught `is True` against a fixture writing `1` (every `start()` test would have gone red). Gate 3 rejected an `agy` flow committed into `scenarios/smoke/hello`: that case is the ONBOARDING gate and `flowbench run` has no flow filter, so it would fail on any host without the harness. A regression guard belongs where its dependency is already required.
- Live `hello/s149-agy-2`: `ended_by: done`, `idle`, 0 flaked, 47.8 s, acceptance 1.0 — the agent asked for both facts, the simulator answered, the file landed. Run 1 died first: `runs_root` defaults to the relative `runs` and omnigent rejects a non-absolute workspace, so the onboarding command in `docs/onboarding.md` §7 cannot launch ANY harness → #155. Offline tests all pass an absolute `tmp_path`, so only a live run reaches it.
