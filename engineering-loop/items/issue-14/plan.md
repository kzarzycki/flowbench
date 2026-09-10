# issue-14 Implementation Plan — contradiction injection (todo_app)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** todo_app's simulated user states two contradicting requirements about done tasks; simulator delivers both halves naturally; judge scores detection/resolution as a 5th criterion.

**Architecture:** content-only edits to three prompt files under `scenarios/swe_planning/cases/todo_app/` plus guard tests. No Python changes — `helpers.parse_scores` (`([a-z_]+)\s*=\s*(\d+)`) and the aggregation/report paths handle arbitrary criteria keys.

**Tech Stack:** markdown prompt files, pytest.

## Global Constraints

- Diff touches ONLY `scenarios/swe_planning/cases/todo_app/{knowledge,simulator,judge}.md` and `tests/test_swe_planning_flows.py` (spec AC5).
- knowledge.md line "MUST: add tasks, see them, mark them done, remove them. Done tasks stay visible as done (mark-and-keep, NOT deleted)." stays byte-identical (spec AC1).
- judge.md final-lines block still ends `SCORES A: ... / SCORES B: ... / WINNER: <A|B|tie> / A: ... / B: ...` (spec AC3); `WINNER:` string preserved.
- Half Y exact remark everywhere it's quoted: "honestly, when I finish something I just want it out of my list."
- The volunteer rule is an explicit EXCEPTION to simulator.md's "answer ONLY the specific question" base rule (gate-1 reviewer note 2).
- `scenario.CASES` staleness is OUT OF SCOPE — do not touch scenario.py (gate-1 reviewer note 1).
- Suite green after every task (baseline 105 passed, 1 skipped).
- Work in worktree `.claude/worktrees/loop+issue-14-contradiction-injection`, branch `loop/issue-14-contradiction-injection`.

---

### Task 1: knowledge.md — the contradiction pair + resolution (AC1)

**Files:**
- Modify: `scenarios/swe_planning/cases/todo_app/knowledge.md` (append section at end)
- Test: `tests/test_swe_planning_flows.py` (append)

**Interfaces:**
- Produces: exact remark string "honestly, when I finish something I just want it out of my list." reused verbatim by Task 2's simulator rule.

- [ ] **Step 1: Write the failing test** — append to `tests/test_swe_planning_flows.py`:

```python
def test_todo_app_contradiction_pair_in_knowledge():
    text = (scenario.CASE_DIR("todo_app") / "knowledge.md").read_text()
    # half X: the mark-and-keep MUST, byte-identical
    assert "Done tasks stay\n  visible as done (mark-and-keep, NOT deleted)." in text
    # half Y: the offhand early remark
    assert "out of my list" in text
    # resolution gated on the agent confronting the conflict
    assert "ONLY if the agent" in text
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/test_swe_planning_flows.py::test_todo_app_contradiction_pair_in_knowledge -q`
Expected: FAIL on `"out of my list" in text`.

- [ ] **Step 3: Append to `scenarios/swe_planning/cases/todo_app/knowledge.md`** (after the `## Target` section, end of file):

```markdown

## A tension you carry (deliberate — never smooth it over yourself)
- Early in the conversation — within your first few replies, unprompted — you
  say, offhand: "honestly, when I finish something I just want it out of my
  list."
- That remark and your mark-and-keep MUST above genuinely conflict. You do not
  notice this yourself; both feel true to you.
- ONLY if the agent points out the conflict and asks you to resolve it: done
  tasks must be KEPT forever — they're your record of what got done — but you
  want them out of the way in the everyday view; being able to see them on
  demand is what "visible as done" really meant.
- If the agent silently picks one side, never volunteer the resolution. React
  only per your normal rules (push back if a proposal DELETES done tasks —
  that breaks your MUST).
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest tests/test_swe_planning_flows.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/cases/todo_app/knowledge.md tests/test_swe_planning_flows.py
git commit -m "feat(swe_planning): todo_app contradiction pair in knowledge.md (#14)"
```

### Task 2: simulator.md — delivery rules (AC2)

**Files:**
- Modify: `scenarios/swe_planning/cases/todo_app/simulator.md` (insert into Rules list)
- Test: `tests/test_swe_planning_flows.py` (append)

**Interfaces:**
- Consumes: Task 1's exact remark string.

- [ ] **Step 1: Write the failing test** — append:

```python
def test_todo_app_simulator_delivers_contradiction():
    text = (scenario.CASE_DIR("todo_app") / "simulator.md").read_text()
    # explicit exception to the answer-only-what-is-asked base rule
    assert "Exception" in text and "out of my list" in text
    # never flags the contradiction unprompted
    assert "NEVER point" in text
    # resolution only when the agent raises the conflict
    assert "only if the agent" in text.lower()
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/test_swe_planning_flows.py::test_todo_app_simulator_delivers_contradiction -q`
Expected: FAIL on the `"Exception" in text and "out of my list" in text` assert.

- [ ] **Step 3: Edit `scenarios/swe_planning/cases/todo_app/simulator.md`** — in the `Rules:` list, insert these two bullets immediately after the first bullet ("- Answer ONLY the specific question ... Keep it to a sentence or two."):

```markdown
- Exception to "answer ONLY what is asked": within your first few replies,
  volunteer once, offhand and unprompted: "honestly, when I finish something I
  just want it out of my list." Say it naturally in passing; do not repeat it.
- Your knowledge holds a deliberate tension around done tasks. NEVER point it
  out yourself and never present it as a puzzle. Give the resolution from your
  knowledge only if the agent explicitly notices the conflict and asks; if the
  agent silently picks a side, react only per your normal MUST rules.
```

- [ ] **Step 4: Run the suite, verify green**

Run: `uv run pytest tests/test_swe_planning_flows.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/cases/todo_app/simulator.md tests/test_swe_planning_flows.py
git commit -m "feat(swe_planning): todo_app simulator delivers both contradiction halves (#14)"
```

### Task 3: judge.md — conflict criterion + SCORES key (AC3)

**Files:**
- Modify: `scenarios/swe_planning/cases/todo_app/judge.md`
- Test: `tests/test_swe_planning_flows.py` (append)

**Interfaces:**
- Consumes: nothing new. `conflict` key is parsed by existing `helpers.parse_scores` with no code change.

- [ ] **Step 1: Write the failing test** — append:

```python
def test_todo_app_judge_scores_conflict():
    text = (scenario.CASE_DIR("todo_app") / "judge.md").read_text()
    assert "5. Conflict handling" in text
    assert text.count("conflict=<0-5>") == 2  # both SCORES lines
    assert "WINNER:" in text
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/test_swe_planning_flows.py::test_todo_app_judge_scores_conflict -q`
Expected: FAIL on `"5. Conflict handling" in text`.

- [ ] **Step 3: Edit `scenarios/swe_planning/cases/todo_app/judge.md`** — two edits:

(a) after the criterion `4. Scope discipline ...` block, insert:

```markdown
5. Conflict handling — the user's statements contain a deliberate
   contradiction about done-task behavior (an early "out of my list" remark
   vs. a keep-done-tasks need). Reward the agent that notices the conflict
   and resolves it with the user; penalize silently picking a side, planning
   both behaviors at once, or never uncovering the second half.
```

(b) replace the two SCORES lines:

```
SCORES A: fulfillment=<0-5> discovery=<0-5> design=<0-5> scope=<0-5>
SCORES B: fulfillment=<0-5> discovery=<0-5> design=<0-5> scope=<0-5>
```

with:

```
SCORES A: fulfillment=<0-5> discovery=<0-5> design=<0-5> scope=<0-5> conflict=<0-5>
SCORES B: fulfillment=<0-5> discovery=<0-5> design=<0-5> scope=<0-5> conflict=<0-5>
```

- [ ] **Step 4: Run the FULL suite, verify green**

Run: `uv run pytest -q`
Expected: 108 passed, 1 skipped (baseline 105 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/cases/todo_app/judge.md tests/test_swe_planning_flows.py
git commit -m "feat(swe_planning): todo_app judge conflict criterion + SCORES key (#14)"
```

## AC traceability

| AC | Task | Test |
|----|------|------|
| AC1 knowledge.md pair + gated resolution | 1 | test_todo_app_contradiction_pair_in_knowledge |
| AC2 simulator delivery rules | 2 | test_todo_app_simulator_delivers_contradiction |
| AC3 judge criterion + conflict= ×2 + WINNER intact | 3 | test_todo_app_judge_scores_conflict |
| AC4 tests fail pre-change, suite green | 1-3 | each task's Step 2 (red) + Step 4 (green) |
| AC5 diff scope | 1-3 | file lists above; gate-3 diff check |
