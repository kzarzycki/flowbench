# Verification procedures

Named checks the epic stories reference as `V1`…`V8`. A story's "Verify" line cites the
procedures it needs plus its story-specific assertions. Run from the flowbench repo root
unless stated.

## V1 — engine offline suite

```bash
uv run pytest -q
```

Green, no unexpected skips beyond the `live_agent`-marked tests. This is the default
gate for every PR.

## V2 — scenarios-repo offline suite

```bash
cd ../xebia/flowbench-scenarios && uv sync && uv run pytest -q
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
# from ../xebia/flowbench-scenarios; needs a running omnigent server, ANTHROPIC_API_KEY unset
uv run --extra spike python -m scenarios.swe_planning.run --run-id <id> &
uv run python -m scenarios.swe_planning.watch <id> --pid $!
```

(Extra renames `spike` → `live` in S01.4; update this file in that PR.) Success: the
watcher exits on `run.json`, no failed sessions, `winner` parsed (not `unknown` unless
the judge genuinely refused), and each flow dir holds `plan.md` + `transcript.md` +
`session.json`. This is mandatory after any change to `driver.py`, `loop.py`, or the
send/retry policy.

## V5 — live todo_app run

Until S01.3 (Inspect era):

```bash
RUN_LIVE_AGENT=1 TODO_RUN_ID=<id> uv run inspect eval \
  scenarios/coding_workflow/cases/todo_app/eval.py --model claudesub/sonnet \
  --model-role user=claudesub/sonnet --model-role grader=claudesub/sonnet
```

After S01.3: the `run_case` entrypoint (`flowbench run --scenario coding_workflow
--case todo_app` once S03.3 lands; the interim `python -m` entrypoint before that).
Success: both flow dirs hold `scorecard.json`, and
`uv run flowbench compare --run-base ../flowbench-runs/todo-app-eval --run-id <id>`
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
