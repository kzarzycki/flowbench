# Verification procedures

Named checks the epic stories reference as `V1`…`V8`. A story's "Verify" line cites the
procedures it needs plus its story-specific assertions. Run from the flowbench repo root
unless stated. `$SCENARIOS` is the scenarios checkout — per-developer path, recorded in
`CLAUDE.local.md`.

## V1 — engine offline suite, then the smoke case

```bash
uv run pytest -q
```

Green, no unexpected skips beyond the `live_agent`-marked tests. This is the default
gate for every PR.

Any change to the case, run, loop or CLI path adds the engine's own smoke case — two minutes,
one flow, one file, and it exercises the kickoff, a simulator relay, the deliverable probe,
`score` and the run dir (needs a live omnigent server, `ANTHROPIC_API_KEY` unset):

```bash
uv run --extra live flowbench run scenarios/smoke/hello --run-id <id>
```

Success: `<runs_root>/hello/<id>/claude/` holds `hello.txt`, `scorecard.json` with
`objective.acceptance == 1.0`, and a `session.json` whose `ended_by` is `done`.

## V2 — scenarios-repo offline suite

```bash
cd "$SCENARIOS" && uv sync && uv run pytest -q
```

Run after any engine change that touches modules the downstream repo imports
(`flowbench.runner.*`, later `flowbench.run/model/judge/transcript/flowspec`). The repo
is an editable path dep — a green engine suite does not prove downstream still imports.

## V3 — hooks / lint

```bash
pre-commit run --all-files
```

## V4 — live planning run (the standard live validation)

```bash
# from $SCENARIOS; needs a running omnigent server, ANTHROPIC_API_KEY unset
uv run --extra live flowbench run scenarios/swe_planning/cases/smoke_todo_app --run-id <id> &
uv run flowbench watch <id> --pid $!    # once the run dir exists
```

Success: the watcher exits on `run.json`, no failed sessions, `winner` parsed (not
`unknown` unless the judge genuinely refused), and each flow dir holds `plan.md` +
`transcript.md` + `session.json`. This is mandatory after any change to the driver, the
loop, or the send/retry policy.

## V5 — live todo_app run

```bash
uv run --extra live flowbench run scenarios/swe_e2e/cases/todo_app --run-id <id>
```

Success: both flow dirs hold `scorecard.json`, and
`uv run flowbench compare --run-base $RUNS/todo_app --run-id <id>`
renders both columns without a FAILED banner.

## V6 — vocabulary sweep

```bash
rg -in '\ban flow\b|arm_name|\bSUT\b|PROBE' src tests scenarios docs
```

Empty output, except deliberate mentions (the glossary's retired-terms section, this
file, and historical notes in `docs/roadmap/`).

## V7 — wheel contents

```bash
uv build && unzip -l dist/*.whl | grep -c '^.*scenarios/' ; rm -rf dist
```

Count must be 0 after S01.4 (the wheel ships `flowbench/` only).

## V8 — coverage gate

```bash
uv run pytest -q --cov=src/flowbench --cov-report=xml
uv run diff-cover coverage.xml --compare-branch origin/master --fail-under=90
```

Changed lines ≥ 90 % covered (S00.2 sets the enforced number in CI; keep this file in
sync with CI).
