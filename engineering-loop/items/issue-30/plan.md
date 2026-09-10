# Codex-native flow with bundled superpowers skills — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** todo_app benchmarks the same vendored superpowers planning workflow on codex-native (flow A) vs claude-native (flow B), with zero host-skill dependence.

**Architecture:** Skills are vendored into the repo and shipped per-flow via the existing bundle mechanism (`OmnigentDriver.skill_dirs` → `<bundle>/skills/`); a paired flowbench change gates `terminal_launch_args` on harness so the codex binary stops receiving claude-only flags (today: exit 2, flow can't boot).

**Tech Stack:** Python 3.12, pytest, PyYAML; repos: `flowbench` (engine, base `master`) + `flowbench-scenarios` (this worktree, branch `loop/issue-30-codex-flow-bundled-skills`).

## Global Constraints (verbatim from spec)

- Vendored skills are verbatim copies of superpowers **6.1.1**; never hand-edited (re-vendor to change).
- claude-native launch args stay **byte-identical** to today's; codex-native gets `["--ask-for-approval", "never", "--sandbox", "workspace-write"]`; any other harness `[]`.
- Flow B keeps `model: haiku` + `reasoning_effort: medium` (the issue's "existing model").
- `feature_flag_service/flows.yaml`, judge/simulator config: untouched.
- Merge order: flowbench PR first, then scenarios PR.
- Working dirs: scenarios work happens in `/Users/zarz/dev/xebia/flowbench-scenarios/.claude/worktrees/loop+issue-30-codex-flow-bundled-skills`; flowbench work in `/Users/zarz/dev/flowbench`.

---

### Task 1: flowbench — harness-gated terminal launch args

**Files:**
- Modify: `/Users/zarz/dev/flowbench/src/flowbench/runner/driver.py:324-349` (`_create_metadata`)
- Test: `/Users/zarz/dev/flowbench/tests/runner/test_driver_config.py`

**Interfaces:**
- Consumes: `OmnigentDriver.harness` (existing field, default `"claude-native"`, driver.py:262).
- Produces: `_create_metadata()["terminal_launch_args"]` — claude-native: existing list byte-identical; codex-native: `["--ask-for-approval", "never", "--sandbox", "workspace-write"]`; other: `[]`. Task 4's flows.yaml relies on the codex-native behavior.

- [ ] **Step 1: Branch from up-to-date master**

```bash
cd /Users/zarz/dev/flowbench
git status --porcelain   # expect empty; if not, STOP and report
git fetch origin && git checkout master && git pull -q origin master
git checkout -b loop/issue-30-codex-launch-args
```

- [ ] **Step 2: Write the failing tests** — append to `tests/runner/test_driver_config.py`:

```python
def test_create_metadata_codex_native_gets_codex_flags(tmp_path):
    # codex rejects claude-only flags (--disallowedTools etc.) with exit 2,
    # so codex-native sessions get codex's own unattended stance instead.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md", harness="codex-native")
    args = d._create_metadata()["terminal_launch_args"]
    assert args == ["--ask-for-approval", "never", "--sandbox", "workspace-write"]


def test_create_metadata_unknown_harness_gets_no_flags(tmp_path):
    # No foreign flags for harnesses we haven't mapped: empty is the safe default.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md", harness="qwen-native")
    assert d._create_metadata()["terminal_launch_args"] == []


def test_create_metadata_claude_native_flags_unchanged(tmp_path):
    # Byte-identical to the pre-change list — comparability of past runs holds.
    d = OmnigentDriver(run_dir=tmp_path, artifact_name="plan.md", harness="claude-native")
    args = d._create_metadata()["terminal_launch_args"]
    assert args[:2] == ["--disallowedTools", "AskUserQuestion"]
    assert args[2:4] == ["--permission-mode", "acceptEdits"]
    assert args[4] == "--allowedTools"
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `cd /Users/zarz/dev/flowbench && uv run pytest tests/runner/test_driver_config.py -v`
Expected: `test_create_metadata_codex_native_gets_codex_flags` and `test_create_metadata_unknown_harness_gets_no_flags` FAIL (codex/unknown currently get the claude flags); the claude one passes.

- [ ] **Step 4: Implement** — in `driver.py`, replace the body of `_create_metadata` (keep the docstring; keep the permission-flags comment with the claude block):

```python
    def _create_metadata(self) -> dict[str, Any]:
        """Metadata form part for `POST /v1/sessions`. Launch args are gated on
        the harness — omnigent passes them verbatim to the native CLI, and codex
        rejects claude-only flags (exit 2). Adds a short `title` and an
        `omni_project` label — the field the web UI groups sessions on — only
        when set, so an unset field leaves the server default untouched."""
        if self.harness == "claude-native":
            launch_args = [
                "--disallowedTools",
                "AskUserQuestion",
                # Permission config MUST ride CLI flags, not the workspace
                # .claude/settings.json: a flow with skills "none" launches with
                # --setting-sources "" (the bridge's host-skill filter), which
                # drops ALL settings files — todo-010's plain flow prompted for
                # Write while superpowers (skills "all") sailed. Flags survive
                # that and are identical for every flow, so comparability holds.
                "--permission-mode",
                "acceptEdits",
                "--allowedTools",
                ",".join(ALLOWED_TOOLS),
            ]
        elif self.harness == "codex-native":
            # Codex's unattended stance: never prompt, sandboxed to the workspace.
            launch_args = ["--ask-for-approval", "never", "--sandbox", "workspace-write"]
        else:
            launch_args = []
        meta: dict[str, Any] = {"terminal_launch_args": launch_args}
        if self.session_title is not None:
            meta["title"] = self.session_title
        if self.project is not None:
            meta["labels"] = {"omni_project": self.project}
        return meta
```

- [ ] **Step 5: Run the flowbench suite**

Run: `cd /Users/zarz/dev/flowbench && uv run pytest -q`
Expected: all green (the two pre-existing metadata tests pass unchanged — they construct with the default harness `claude-native`).

- [ ] **Step 6: Commit**

```bash
cd /Users/zarz/dev/flowbench
git add src/flowbench/runner/driver.py tests/runner/test_driver_config.py
git commit -m "fix: gate terminal_launch_args on harness (codex rejects claude flags)"
```

---

### Task 2: scenarios — vendor the superpowers skills

**Files:**
- Create: `scenarios/swe_planning/skills/using-superpowers/` (copied dir)
- Create: `scenarios/swe_planning/skills/brainstorming/` (copied dir)
- Create: `scenarios/swe_planning/skills/writing-plans/` (copied dir)
- Create: `scenarios/swe_planning/skills/VERSION.md`
- Test: `tests/test_swe_planning_flows.py` (append)

**Interfaces:**
- Produces: the three skill dirs Task 4's flows.yaml points at via `../../skills/<name>`.

All paths below relative to the scenarios worktree
(`/Users/zarz/dev/xebia/flowbench-scenarios/.claude/worktrees/loop+issue-30-codex-flow-bundled-skills`).

- [ ] **Step 1: Write the failing test** — append to `tests/test_swe_planning_flows.py`:

```python
def test_vendored_superpowers_skills_present():
    skills = Path(__file__).parent.parent / "scenarios" / "swe_planning" / "skills"
    for name in ("using-superpowers", "brainstorming", "writing-plans"):
        assert (skills / name / "SKILL.md").is_file(), name
    version = (skills / "VERSION.md").read_text()
    assert "6.1.1" in version
```

Add at the top of the file (after the existing imports):

```python
from pathlib import Path
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_swe_planning_flows.py::test_vendored_superpowers_skills_present -v`
Expected: FAIL (`AssertionError: using-superpowers` — dir doesn't exist).

- [ ] **Step 3: Vendor the skills**

```bash
mkdir -p scenarios/swe_planning/skills
for s in using-superpowers brainstorming writing-plans; do
  cp -R "/Users/zarz/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/$s" \
        "scenarios/swe_planning/skills/$s"
done
```

- [ ] **Step 4: Write the provenance note** — `scenarios/swe_planning/skills/VERSION.md`:

```markdown
# Vendored superpowers skills

Verbatim copies from the `superpowers` Claude plugin, marketplace
`claude-plugins-official`, version **6.1.1**
(`~/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/`),
copied 2026-07-03 for issue #30.

Never hand-edit these copies — re-vendor from a newer upstream version instead
(pre-commit whitespace normalization on copy is expected and fine). They exist
so both todo_app flows load identical skills from the flow bundle
(`flows.yaml` `skill_dirs`) with no host-skill dependence.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_swe_planning_flows.py::test_vendored_superpowers_skills_present -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scenarios/swe_planning/skills tests/test_swe_planning_flows.py
git commit -m "feat: vendor superpowers 6.1.1 planning skills for bundle-loaded flows"
```

Note: pre-commit (end-of-file/whitespace fixers, gitleaks) runs on commit; if a fixer
modifies vendored files, `git add` the fixes and re-commit — whitespace-only
normalization is expected (VERSION.md says so). If gitleaks flags a vendored file,
STOP and report (do not add to `.gitleaks.toml` without review).

---

### Task 3: scenarios — `load_flows` resolves `skill_dirs`

**Files:**
- Modify: `scenarios/swe_planning/helpers.py:28-29` (`load_flows`)
- Test: `tests/test_swe_planning_helpers.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `load_flows(path) -> list[dict]` where each flow's optional `skill_dirs`
  becomes `list[pathlib.Path]` (absolute); raises `ValueError` naming the entry when a
  dir is missing or lacks `SKILL.md`. Task 4's `make_flow_driver_omni` passes this list
  straight to `OmnigentDriver.skill_dirs`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_swe_planning_helpers.py`:

```python
def test_load_flows_resolves_skill_dirs(tmp_path):
    skill = tmp_path / "skills" / "brainstorming"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# s")
    case = tmp_path / "cases" / "x"
    case.mkdir(parents=True)
    (case / "flows.yaml").write_text(
        "flows:\n  - name: a\n    skill_dirs: [../../skills/brainstorming]\n"
    )
    flows = load_flows(case / "flows.yaml")
    assert flows[0]["skill_dirs"] == [skill.resolve()]


def test_load_flows_missing_skill_dir_raises(tmp_path):
    case = tmp_path / "c"
    case.mkdir()
    (case / "flows.yaml").write_text("flows:\n  - name: a\n    skill_dirs: [../nope]\n")
    with pytest.raises(ValueError, match="nope"):
        load_flows(case / "flows.yaml")


def test_load_flows_without_skill_dirs_unchanged(tmp_path):
    (tmp_path / "flows.yaml").write_text("flows:\n  - name: a\n    skills: none\n")
    flows = load_flows(tmp_path / "flows.yaml")
    assert "skill_dirs" not in flows[0]
```

If the file doesn't already import `pytest` or `load_flows`, add:

```python
import pytest
from scenarios.swe_planning.helpers import load_flows
```

- [ ] **Step 2: Run to verify the first two fail**

Run: `uv run pytest tests/test_swe_planning_helpers.py -v -k skill_dir`
Expected: `test_load_flows_resolves_skill_dirs` FAIL (skill_dirs stays a list of strings), `test_load_flows_missing_skill_dir_raises` FAIL (no ValueError).

- [ ] **Step 3: Implement** — replace `load_flows` in `scenarios/swe_planning/helpers.py`:

```python
def load_flows(path) -> list[dict]:
    path = Path(path)
    flows = yaml.safe_load(path.read_text())["flows"]
    for flow in flows:
        if "skill_dirs" in flow:
            resolved = []
            for entry in flow["skill_dirs"]:
                skill_dir = (path.parent / entry).resolve()
                if not (skill_dir / "SKILL.md").is_file():
                    raise ValueError(
                        f"skill_dirs entry {entry!r} in {path}: no SKILL.md at {skill_dir}"
                    )
                resolved.append(skill_dir)
            flow["skill_dirs"] = resolved
    return flows
```

(`Path` and `yaml` are already imported in helpers.py.)

- [ ] **Step 4: Run to verify all pass**

Run: `uv run pytest tests/test_swe_planning_helpers.py -v`
Expected: PASS (all, including pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add scenarios/swe_planning/helpers.py tests/test_swe_planning_helpers.py
git commit -m "feat: load_flows resolves per-flow skill_dirs, fails fast on missing skill"
```

---

### Task 4: scenarios — thread `skill_dirs` + the codex/claude flows.yaml

**Files:**
- Modify: `scenarios/swe_planning/run.py:291-304` (`make_flow_driver_omni`)
- Modify: `scenarios/swe_planning/cases/todo_app/flows.yaml` (full rewrite)
- Test: `tests/test_swe_planning_run.py` (append), `tests/test_swe_planning_flows.py` (append)

**Interfaces:**
- Consumes: Task 3's `load_flows` (absolute `skill_dirs`), Task 1's harness-gated args
  (transparent — no scenarios code change needed for it), `OmnigentDriver.skill_dirs`
  (existing flowbench field).
- Produces: the shipped todo_app matchup.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_swe_planning_run.py`:

```python
def test_make_flow_driver_threads_skill_dirs(tmp_path):
    flow = {"name": "codex", "harness": "codex-native", "model": "gpt-5.5",
            "skill_dirs": [tmp_path / "skills" / "brainstorming"]}
    d = make_flow_driver_omni(flow, tmp_path)
    assert d.skill_dirs == [tmp_path / "skills" / "brainstorming"]
    assert d.harness == "codex-native"
    assert d.model == "gpt-5.5"


def test_make_flow_driver_defaults_no_skill_dirs(tmp_path):
    d = make_flow_driver_omni({"name": "x"}, tmp_path)
    assert d.skill_dirs == []
```

Append to `tests/test_swe_planning_flows.py`:

```python
def test_todo_app_flows_are_codex_vs_claude_same_skills():
    case = Path(__file__).parent.parent / "scenarios" / "swe_planning" / "cases" / "todo_app"
    flows = yaml.safe_load((case / "flows.yaml").read_text())["flows"]
    a, b = flows
    assert (a["name"], a["harness"], a["model"]) == ("codex", "codex-native", "gpt-5.5")
    assert (b["name"], b["harness"], b["model"]) == ("claude", "claude-native", "haiku")
    assert b["reasoning_effort"] == "medium"
    # skills filter: list on codex ("none" would drop bundle skills), none on claude
    assert a["skills"] == ["using-superpowers", "brainstorming", "writing-plans"]
    assert b["skills"] == "none"
    for f in flows:
        assert f.get("skills") != "all"
    # the whole point: identical skills content and identical prompts
    assert a["skill_dirs"] == b["skill_dirs"]
    assert len(a["skill_dirs"]) == 3
    assert a["prepend"] == b["prepend"] and a["append"] == b["append"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_swe_planning_run.py -v -k skill_dirs` then
`uv run pytest tests/test_swe_planning_flows.py::test_todo_app_flows_are_codex_vs_claude_same_skills -v`
Expected: first — FAIL (`OmnigentDriver` gets no skill_dirs → `d.skill_dirs == []` for the first test); second — FAIL (flows still named superpowers/plain).

- [ ] **Step 3: Thread skill_dirs in `run.py`** — add one line to `make_flow_driver_omni`'s `OmnigentDriver(...)` call, after `skills=flow.get("skills", "all"),`:

```python
        skill_dirs=flow.get("skill_dirs", []),
```

- [ ] **Step 4: Rewrite `scenarios/swe_planning/cases/todo_app/flows.yaml`** (full content):

```yaml
# A flow = a whole approach: harness + skills + how it's told to plan + model/effort.
# Flow order defines the judge's A/B: A = first, B = second.
# Both flows load the SAME vendored superpowers skills from the bundle
# (scenarios/swe_planning/skills/, see VERSION.md) — no host-skill dependence.
# The skills filter differs by harness on purpose: codex-native needs the
# explicit name list ("none" stages nothing, bundle included); claude-native
# needs "none" (host suppressed via --setting-sources "", bundle skills ride
# --plugin-dir; a list would NOT suppress host skills there).
flows:
  - name: codex
    harness: codex-native
    model: gpt-5.5
    skills: [using-superpowers, brainstorming, writing-plans]
    skill_dirs:
      - ../../skills/using-superpowers
      - ../../skills/brainstorming
      - ../../skills/writing-plans
    prepend: |
      Use /brainstorming to clarify my need and interview me.
    append: |
      Write the final plan to plan.md, then answer "plan is complete", then wait for my instructions.
      Do NOT implement the feature — no code, no scaffolding, no dependency
      installs. plan.md is the only deliverable.
  - name: claude
    harness: claude-native
    model: haiku             # the issue pins "existing model"; flagship pairing = issue #27
    reasoning_effort: medium
    skills: none
    skill_dirs:
      - ../../skills/using-superpowers
      - ../../skills/brainstorming
      - ../../skills/writing-plans
    prepend: |
      Use /brainstorming to clarify my need and interview me.
    append: |
      Write the final plan to plan.md, then answer "plan is complete", then wait for my instructions.
      Do NOT implement the feature — no code, no scaffolding, no dependency
      installs. plan.md is the only deliverable.
```

- [ ] **Step 5: Run to verify all pass**

Run: `uv run pytest tests/test_swe_planning_run.py tests/test_swe_planning_flows.py -v`
Expected: PASS (all; note `test_flows_shape` pins the untouched feature_flag_service case and must still pass).

- [ ] **Step 6: Commit**

```bash
git add scenarios/swe_planning/run.py scenarios/swe_planning/cases/todo_app/flows.yaml \
        tests/test_swe_planning_run.py tests/test_swe_planning_flows.py
git commit -m "feat: todo_app A/B = codex-native vs claude-native, identical bundled superpowers"
```

---

### Task 5: full suites green in both repos

**Files:** none (verification only).

- [ ] **Step 1: scenarios suite**

Run: `uv run pytest -q` (in the scenarios worktree)
Expected: all green (baseline was 100 passed, 1 skipped; now +6 new tests).

- [ ] **Step 2: flowbench suite**

Run: `cd /Users/zarz/dev/flowbench && uv run pytest -q`
Expected: all green.

- [ ] **Step 3: pre-commit over everything (scenarios worktree)**

Run: `pre-commit run --all-files`
Expected: pass (or auto-fixed whitespace only → `git add -u && git commit -m "chore: pre-commit normalization of vendored skills"`).

Then report IMPLEMENTED to the loop controller (it updates state.json / LOG.md and
runs Phases 7-9: adversarial review, gates, PRs — flowbench PR first).
