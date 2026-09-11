# Onboarding: getting a live run working

Everything in this repo runs offline against test doubles. A **live** run — a real coding
agent, driven turn by turn — needs a working [omnigent](design/decisions/2026-09-09-omnigent-as-the-meta-harness.md)
server on the same machine. That part is not discoverable from the code, so it lives here.

Read [`GLOSSARY.md`](GLOSSARY.md) first for the vocabulary (Scenario → Case → Flow → Run →
Scorecard → Comparison), and [`design/runner.md`](design/runner.md) for what the runtime does
with it.

## 1. What you need

| Thing | Why |
| --- | --- |
| Python 3.12+, [`uv`](https://docs.astral.sh/uv/) | the engine |
| Node ≥ 22, `tmux` | omnigent's harness runners drive real CLIs inside tmux panes |
| A Claude Code install and a **Claude subscription** | the system under test is vanilla Claude Code, billed to the subscription |
| An omnigent install that runs a server | see the next paragraph — this is the part that has no default |

Offline first, before any of the above:

```bash
uv sync --extra dev --extra live   # live = the omnigent client the driver imports
pre-commit install                 # once per clone: lint/secret hooks + "one worktree, one branch"
uv run pytest -q                   # live-agent tests skip themselves without RUN_LIVE_AGENT=1
```

### One worktree, one branch

Several agents work this repo at once, and `git switch` in a shared checkout mutates every
one of their working trees. So: the main checkout stays on `master`, every branch gets its own
sibling worktree (`../flowbench--<slug>`, sibling not nested — scenarios resolves the engine by
relative path), and the worktree is removed when the branch merges.

`scripts/post-checkout.sh` (installed by `pre-commit install` as the post-checkout hook)
enforces it: the main checkout is bound to the default branch, a
linked worktree to the first branch checked out in it, and any later switch to another branch
is reverted and fails. Git has no pre-checkout hook, so the switch happens and is undone; the
net effect is a block (a `checkout -B`/`switch -C` that reset the target branch is undone too).
File checkouts, detached HEAD (rebase, bisect) and `GIT_REBIND=1 git switch <branch>` pass.
Tests: `tests/test_githooks.py`.

### Installing omnigent

omnigent lives at [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) and publishes
to PyPI. Two ways in, and the choice matters later (§2, §5):

```bash
# a) the published release — enough to run the benchmark
uv tool install 'omnigent==0.12.0'

# b) a source checkout — what you want if you also work on omnigent itself
uv tool install --editable <path-to-your-omnigent-checkout>
```

Then, once:

```bash
omnigent setup            # first-time flow: harness extras, credentials
omnigent start            # server + this machine's host, in the background
omnigent --version        # what you actually installed
omnigent diagnose         # read-only environment snapshot, good for bug reports
```

`omnigent stop` tears it down again. Pin whatever version you install: this repo drives
omnigent through private-API reach-ins (`roadmap/current-state.md` #3), so a surprise upgrade
is a real risk, not a theoretical one.

## 2. The topology (two omnigents, and only one of them drives the agent)

```
your shell ─ uv run --extra live flowbench run <case_dir>
                │  imports omnigent_client + omnigent.host.daemon_launch   ← (a) venv copy
                │  HTTP :6767
                ▼
        omnigent server ──► host daemon ──► harness runner ──► tmux pane ──► `claude` CLI
                                                                              (vanilla, host ~/.claude)
        └────────────────── (b) the install the server runs from ─────────────┘
```

- **(a) the venv copy** comes from this repo's `live` extra (`omnigent`, `omnigent-client`,
  pinned in `pyproject.toml`). The distribution is complete — it contains the harness bridge
  module too — but **flowbench only ever imports the client side of it**: `omnigent_client` to
  POST a session and poll, and `omnigent.host.daemon_launch` to ask the host daemon for a
  runner. No code path in a flowbench process scans a tmux pane.
- **(b) the install the server runs from** is what spawns runners and drives the CLI. See it
  for yourself — `ps ax | grep omnigent` shows every runner, harness and bridge process running
  under that install's interpreter (`~/.local/share/uv/tools/omnigent/bin/python3 -m
  omnigent.runner._entry`, `-m omnigent.runtime.harnesses._runner`, and the claude-native bridge
  under whichever module path this version uses — see the table in §5). Which install is it?
  `cat ~/.local/share/uv/tools/omnigent/uv-receipt.toml`: an `editable = <path>` line means it
  tracks a source checkout and can be far ahead of the pinned client. **The two versions differ,
  and the pin does not constrain the server.** When you debug harness behaviour — prompt
  detection, permission mode, injection — read the server's install, not the venv's, and check
  `omnigent --version` rather than `pyproject.toml`.
- The server usually runs as a background service (`launchctl list | grep omni` on macOS);
  its logs are `~/.omnigent/logs/launchd-omnigent.out.log` (server) and
  `~/.omnigent/logs/host-runner/runner-*.log` (runners).

## 3. Is it ready? Ask the same question the driver asks

`OmnigentDriver._resolve_host` needs one host that is online **and** reports the flow's
harness as exactly `true` — `claude-native` for a default flow, `antigravity-native` for an
agy one. A harness the host reports as `"binary-missing"` does not count. That is the only
readiness check worth running:

```bash
curl -s http://127.0.0.1:6767/v1/hosts | python3 -m json.tool | less   # or, per harness:
HARNESS=claude-native   # antigravity-native for an agy flow
curl -s http://127.0.0.1:6767/v1/hosts \
  | HARNESS=$HARNESS python3 -c 'import json,os,sys;h=os.environ["HARNESS"];print([(x["status"],x["configured_harnesses"].get(h)) for x in json.load(sys.stdin)["hosts"]])'
```

You want `('online', True)`. Anything else — including `'binary-missing'`, which is truthy but
not a working harness — and the run dies at `start()` with
`no online host with <harness> configured`, naming the harness the flow asked for. That is also
what you get if the machine sleeps mid-run (the host daemon drops off).

There is **no health or version endpoint**: unknown paths return the web UI with HTTP 200, so
`/healthz`-style probes always "pass". Use `/v1/hosts`.

Override the address with `OMNIGENT_SERVER` if it is not on `127.0.0.1:6767`.

## 4. `ANTHROPIC_API_KEY` must be UNSET

`OmnigentDriver.start()` raises if it is set, before doing anything else:

```
RuntimeError: ANTHROPIC_API_KEY is set — would defeat subscription billing.
```

This is not hygiene, it is the measurement. With the key set, Claude Code bills the API and
runs as an API client; unset, it runs exactly as the product a developer uses, on subscription
billing — which is the thing the benchmark claims to compare. A benchmark whose runs differ
from the product in billing mode differs from it in rate limits, defaults and availability too,
so the guard is a hard failure rather than a warning.

The cost of that choice, worth knowing before a long run: **runs consume the operator's
subscription quota.** When the quota runs out, agents do not error — they stall mid-turn, turns
hang until the websocket ping timeout (~20 min), and no artifact lands. Everything stalling at
once is a quota symptom, not a code bug. Check your quota before a multi-hour run.

## 5. If a 2nd+ turn fails with "terminal did not become ready"

omnigent's claude-native bridge detects the prompt by scanning the tmux pane. Since 0.12.0 it
anchors on the input box's own rule (`_is_box_rule`), so a tall Claude Code footer cannot hide
the `❯` glyph. If you see this failure, check the bridge in **the server's** install (not the
venv client, §2) for `_is_box_rule`; the module moved between versions:

| Version | Bridge module | Process you see in `ps` |
| --- | --- | --- |
| ≤ 0.12.0 (published) | `omnigent/claude_native_bridge.py` | `-m omnigent.claude_native_bridge` |
| 0.13.0.dev0 and later (source) | `omnigent/harnesses/claude_native/bridge.py` | `-m omnigent.harnesses.claude_native.bridge` |

Missing → the server runs a pre-0.12.0 omnigent; upgrade it.

## 6. Settings, and where runs land

Three settings, resolved by one layered object (`flowbench.settings.Settings`, pydantic-settings):

| Setting | Flag | Default |
| --- | --- | --- |
| `runs_root` | `--runs-root` | `runs` (resolved against the cwd; gitignored here) |
| `sim_model` | `--sim-model` | `opus` |
| `judge_model` | `--judge-model` | `opus` |

Precedence, highest first: **the flag** → **`FLOWBENCH_*` in the environment**
(`FLOWBENCH_RUNS_ROOT=…`) → **`.env` in the cwd** → **`[tool.flowbench]` in `pyproject.toml`** →
the default. A flag you did not pass never shadows a lower layer. Budgets are *not* settings:
`max_turns` and `deadline_s` belong to the case (`case.py`), because a cap the flow can or cannot
live inside is a variable of the benchmark, not of the machine.

Point `runs_root` **outside the repo** — the convention is a sibling
`<launching checkout>/../flowbench-runs/` (`$RUNS` in tracked docs), set once in the launching
repo's `[tool.flowbench]` or exported as `FLOWBENCH_RUNS_ROOT`; record the concrete path in your
untracked `CLAUDE.local.md`, per the no-per-developer-paths policy. Inside it, a run is
`<runs_root>/<case>/<run_id>` (plus `trial-XX/` when `--n > 1`) — a plain folder of files
(`run.json`, `<flow>/scorecard.json`, transcripts): every reader in this repo reads them, nothing
wraps execution.

## 7. Your first live run

Start with the engine's own smoke case: one flow, one file, a four-turn budget — a couple of
minutes, and it exercises the kickoff, a simulator relay, the deliverable probe, `score` and the
run dir. If this passes, the machine is wired up.

```bash
unset ANTHROPIC_API_KEY
uv run --extra live flowbench run scenarios/smoke/hello --run-id smoke-001
```

Then the real thing — the open reference case (`$SCENARIOS` has the private ones), which takes
about an hour per flow:

```bash
caffeinate -i uv run --extra live flowbench run \
  scenarios/swe_e2e/cases/todo_app --run-id <id>
```

Five rules learned the hard way:

- **`uv run --extra live`, always.** A bare `uv run` resyncs the env to the default deps and
  drops the extra; omnigent then vanishes mid-day (`ModuleNotFoundError: omnigent` at
  `driver.start()`).
- **`caffeinate -i`.** An idle Mac sleeps mid-turn and the agent dies on wake
  (`native_turn_error: "Your computer went to sleep mid-response"`). `-i` does not stop
  clamshell sleep — keep the lid open, or run headless.
- **Watch it.** From a second shell, once the run dir exists:

  ```bash
  uv run flowbench watch <id> --pid <runner-pid>
  ```

  One line per anomaly (permission prompts, run-scoped server errors, failed sessions,
  `STALLED (...)`, `QUOTA: ...` — a CLI limit banner, wait for the reset), until the run's
  `run.json` lands or the `--pid` you gave it dies. The run id alone is enough: which case wrote
  the dir is in the layout. Start it *after* the run dir exists — the watcher resolves the id
  against `runs_root` and exits with `no run dir …` if it is not there yet.
- **No server restart under a run.** The bridge gates every tool call through a
  `PreToolUse` hook that asks the omnigent server; when the server is down or restarting the
  hook fails *ask* by design, and Claude Code shows a permission card even under
  `bypassPermissions` (`Do you want to create <file>?`) — the flow ends `STALLED (prompt)`.
  Anything that restarts the server (the fork's `auto-sync` after an upstream rebase,
  `omnigent host stop`, a launchd kickstart) must wait for a quiet server: no session touched
  in the last 10 min.
- **Expect long turns.** A workflow-heavy flow can spend half an hour in one turn. All three
  budgets live with the case, because a cap the flow can or cannot live inside is a first-order
  variable of the benchmark: `turn_timeout_s` (per-turn cap) and `stall_s` (heartbeat watchdog)
  are per-flow fields in `flows.yaml`, and the whole-session budgets `max_turns` and `deadline_s`
  are `Case` attributes in `case.py`. The CLI has no flag for any of them.

Then read the scorecards side by side:

```bash
uv run flowbench compare --run-base $RUNS/todo_app --run-id <id>
```

The omnigent session, its runner and its tmux pane are **left alive on purpose** when a run
ends: `session.json` carries a `conversation_url` you can open to continue the agent the
simulator was driving.

## 8. Where to read next

- [`GLOSSARY.md`](GLOSSARY.md) — the vocabulary, in dependency order.
- [`design/case.md`](design/case.md) — the case folder format and the `Case` contract.
- [`design/runner.md`](design/runner.md) — driver/loop/run_case contracts, and the CLI.
- [`design/decisions/`](design/decisions/) — why a flow is the full configuration; why omnigent
  is the meta-harness.
- [`roadmap/current-state.md`](roadmap/current-state.md) — the known warts, each pointing at the
  epic that fixes it (private-API reach-ins and the version split are #3 there).
- `$SCENARIOS/docs/knowledge/omnigent.md` — operational gotchas from real runs, in the private
  scenarios repo.
