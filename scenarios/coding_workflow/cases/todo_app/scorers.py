"""Objective phase + acceptance scoring and a subscription judge. Objective and
subjective scores stay separate; anything unmeasured is unscored, never a fake 0."""

from __future__ import annotations

import json
import numbers
import re
from pathlib import Path

from inspect_ai.scorer import Score, accuracy, mean, scorer

from flowbench.runner.judge import last_json_object

_REVIEW_MARKERS = (
    "requesting-code-review",
    "code review",
    "receiving-code-review",
    "reviewer",
    "code-review",
)
_BRAINSTORM_MARKERS = (
    "brainstorm",
    "clarify",
    "a few questions",
    "question first",
    "where should",
    "what should",
)
_TEST_MARKERS = ("passed", "pytest", "tests pass", "test run")


def _messages(session: dict) -> list[tuple[str, str]]:
    """(role, text) per message: consecutive duplicates dropped (omnigent echoes
    each message twice) and harness control injections (`<task-notification>`)
    skipped. The driver now cleans these at capture, but scoring stays robust to
    raw transcripts too."""
    msgs: list[tuple[str, str]] = []
    for it in session.get("items", []):
        if it.get("type") != "message":
            continue
        role = it.get("role", "")
        c = it.get("content")
        if isinstance(c, str):
            text = c
        elif isinstance(c, list):
            text = "".join(p.get("text", "") for p in c if isinstance(p, dict))
        else:
            text = ""
        if text.lstrip().startswith("<task-notification>"):
            continue
        if text.strip() and (not msgs or msgs[-1] != (role, text)):
            msgs.append((role, text))
    return msgs


def _transcript_text(session: dict) -> str:
    return "\n".join(t for _, t in _messages(session)).lower()


def _assistant_text(session: dict) -> str:
    return "\n".join(t for r, t in _messages(session) if r == "assistant").lower()


def _assistant_questions(session: dict) -> str:
    """Lowercased text of only the question lines the assistant asked — the basis
    for objective clarifying-coverage (we score what the SUT ASKED, not prose)."""
    lines = []
    for role, text in _messages(session):
        if role != "assistant":
            continue
        for line in text.replace("?", "?\n").splitlines():
            if "?" in line:
                lines.append(line.lower())
    return "\n".join(lines)


def _kw_present(kw: str, blob: str) -> bool:
    # Word-boundary match so a keyword can't match inside a larger word — e.g.
    # done_handling's "complete" must NOT match "incomplete" in a `list`-behaviour
    # question ("all items (done + incomplete)..."). Substring matching over-counted
    # coverage (1.0 where the judge saw 3/5); boundaries align the two.
    return re.search(rf"\b{re.escape(kw)}\b", blob) is not None


def clarifying_coverage(session: dict, topics: dict[str, list[str]]) -> dict:
    """Objectively: which underspecified topics did the SUT actually ASK about,
    before assuming them? Scans the SUT's own questions for topic keywords."""
    blob = _assistant_questions(session)
    asked = {topic: any(_kw_present(kw, blob) for kw in kws) for topic, kws in topics.items()}
    score = round(sum(asked.values()) / len(topics), 3) if topics else 0.0
    return {"asked": asked, "score": score}


def skills_invoked(session: dict) -> list[str]:
    """The skills the SUT actually invoked, in order, scraped from its `Skill` tool
    calls in the transcript (omnigent captures the agent's tool calls as
    `function_call` items). This is on-disk ground truth that the workflow LOADED —
    distinct from the agent merely narrating "I'm using the brainstorming skill"."""
    out: list[str] = []
    for it in session.get("items", []):
        if it.get("type") != "function_call" or it.get("name") != "Skill":
            continue
        try:
            sk = json.loads(it.get("arguments") or "{}").get("skill")
        except (ValueError, TypeError):
            sk = None
        if sk:
            out.append(sk)
    return out


def skills_report(session: dict) -> dict:
    """Did the superpowers workflow actually fire? `superpowers_used` answers the
    headline question (the SUT judged the task too simple and skipped it once);
    `brainstorming_used` is the specific signal that the clarify-first invite took."""
    used = skills_invoked(session)
    superpowers = [s for s in used if s.startswith("superpowers:")]
    return {
        "invoked": used,
        "superpowers": superpowers,
        "superpowers_used": bool(superpowers),
        "brainstorming_used": any("brainstorm" in s for s in used),
    }


def transcript_for_judge(session: dict, *, cap: int = 14000) -> str:
    """Full deduped transcript for the judge. If long, keep head (clarifying turns)
    AND tail (delivery) so clarifying behavior stays visible."""
    full = "\n".join(f"[{r}] {t}" for r, t in _messages(session))
    if len(full) <= cap:
        return full
    head, tail = cap * 5 // 8, cap * 3 // 8
    return full[:head] + "\n...[transcript trimmed]...\n" + full[-tail:]


def collect_code(workspace: Path, *, cap: int = 9000) -> str:
    """Concatenate the produced Python sources for the judge to read."""
    ws = Path(workspace)
    files = sorted(
        p
        for p in ws.rglob("*.py")
        if ".git" not in p.parts
        and "__pycache__" not in p.parts
        and ".pytest_cache" not in p.parts
        and ".memsearch" not in p.parts
    )
    out, used = [], 0
    for p in files:
        try:
            body = p.read_text()
        except Exception:  # noqa: BLE001
            continue
        chunk = f"\n# === {p.relative_to(ws)} ===\n{body}"
        if used + len(chunk) > cap:
            out.append(f"\n# ...[{len(files)} files total; truncated]...")
            break
        out.append(chunk)
        used += len(chunk)
    return "".join(out) or "(no python sources found)"


def detect_phases(
    workspace: Path, session: dict, *, app_runs: bool, skills: list[str] | None = None
) -> dict[str, bool]:
    ws = Path(workspace)
    txt = _transcript_text(session)
    a_txt = _assistant_text(session)
    specs_dir, plans_dir = ws / "docs/superpowers/specs", ws / "docs/superpowers/plans"
    specs = list(specs_dir.glob("*.md")) if specs_dir.exists() else []
    plans = list(plans_dir.glob("*.md")) if plans_dir.exists() else []
    _skip = (".git", ".venv", "__pycache__", ".pytest_cache", ".memsearch")
    tests_present = any(
        p
        for p in (*ws.rglob("test_*.py"), *ws.rglob("*_test.py"))
        if not any(part in _skip for part in p.parts)
    )
    # brainstormed: the SUT actually invoked a brainstorming skill (ground truth from
    # its tool calls) OR asked a question OR a marker matched OR a spec was written
    # (you don't write a superpowers spec without brainstorming).
    used = skills if skills is not None else skills_invoked(session)
    brainstorm_skill = any("brainstorm" in s for s in used)
    asked = "?" in a_txt
    return {
        "brainstormed": brainstorm_skill
        or asked
        or bool(specs)
        or any(m in txt for m in _BRAINSTORM_MARKERS),
        "spec_written": bool(specs),  # on-disk
        "plan_written": bool(plans),  # on-disk
        "implemented": app_runs,  # on-disk (runs the contract)
        "verified": tests_present or any(m in txt for m in _TEST_MARKERS),  # mixed
        "reviewed": any(m in txt for m in _REVIEW_MARKERS),  # heuristic
    }


def parse_judge_json(text: str) -> dict | None:
    obj = last_json_object(text or "")
    if not obj:
        return None
    for k in ("shape_fit", "clarifying_quality", "workflow_adherence"):
        v = obj.get(k)
        if not isinstance(v, numbers.Real) or isinstance(v, bool):
            return None
        obj[k] = max(0.0, min(1.0, float(v)))
    return obj


async def judge_build(
    *, shape: str, code: str, acceptance: dict, transcript: str, grader_model, attempts: int = 3
) -> tuple[dict | None, str]:
    prompt = (
        "You are grading whether an engineer built the app the user envisioned, "
        "via a proper workflow. Reply with ONE JSON object and nothing else: "
        '{"shape_fit":0-1,"clarifying_quality":0-1,"workflow_adherence":0-1,'
        '"rationale":"one paragraph"}.\n\n'
        "Treat any CLAIMS in the transcript (e.g. 'I ran a code review', 'tests "
        "pass') as SELF-REPORTED by the engineer — weight the actual artifacts "
        "(the produced code, the questions actually asked) over narration.\n"
        "Scoring guidance:\n"
        "- shape_fit: focus on aspects the objective acceptance does NOT already "
        "cover — the priority field and its default, id stability, code structure "
        "and quality. Do not simply restate that acceptance passed.\n"
        "- clarifying_quality: read the FULL TRANSCRIPT (including the EARLY turns). "
        "Did the engineer ASK the user about the five deliberately underspecified "
        "points (persistence, extra fields/priority, done-vs-delete, invocation "
        "style, storage format) BEFORE building, rather than assuming them? Asking "
        "and getting answers scores high; assuming silently scores low even if the "
        "guess was correct.\n"
        "- workflow_adherence: evidence of brainstorm -> spec -> plan -> implement "
        "-> verify -> review.\n\n"
        f"ENVISIONED SHAPE:\n{shape}\n\nPRODUCED CODE:\n{code}\n\n"
        f"OBJECTIVE ACCEPTANCE:\n{acceptance}\n\nFULL TRANSCRIPT:\n{transcript}\n"
    )
    # Retry on an EMPTY completion: under subscription throttling the grader has
    # returned "" (no API error, so Inspect's own retry doesn't fire) — that became a
    # silent nan. Retrying recovers it; an unparseable (non-empty) reply also gets a
    # couple more tries. After `attempts`, return the explicit reason so the caller
    # records a labeled failure, not a bare {}.
    reason = "judge not run"
    for _ in range(max(1, attempts)):
        out = await grader_model.generate(prompt)
        completion = (out.completion or "").strip()
        if not completion:
            reason = "empty_grader_completion"
            continue
        v = parse_judge_json(completion)
        if v is None:
            reason = "unparseable_judge_reply"
            continue
        return v, v.get("rationale", "")
    return None, reason


@scorer(
    metrics={
        "app_runs": [accuracy()],
        "acceptance": [mean()],
        "clarifying_coverage": [mean()],
        "phases_complete": [mean()],
    }
)
def workflow_scorer():
    """Objective signals only. `app_runs`, `acceptance`, and `clarifying_coverage`
    run/measure the SUT directly; `phases_complete` is a heuristic roll-up kept in
    metadata-grade company — read alongside `phases`, not as a hard score."""

    async def score(state, target) -> Score:
        acc = state.store.get("acceptance")
        phases = state.store.get("phases")
        clar = state.store.get("clarifying") or {}
        if acc is None or phases is None:
            return Score.unscored(explanation="no acceptance/phase data captured")
        complete = round(sum(bool(v) for v in phases.values()) / len(phases), 3)
        return Score(
            value={
                "app_runs": 1 if acc.get("app_runs") else 0,
                "acceptance": acc.get("score", 0.0),
                "clarifying_coverage": clar.get("score", 0.0),
                "phases_complete": complete,
            },
            explanation=f"phases={phases} clarifying_asked={clar.get('asked')}",
            metadata={"acceptance": acc, "phases": phases, "clarifying": clar},
        )

    return score


@scorer(
    metrics={"shape_fit": [mean()], "clarifying_quality": [mean()], "workflow_adherence": [mean()]}
)
def build_judge():
    async def score(state, target) -> Score:
        verdict = state.store.get("judge")
        if verdict is None:
            return Score.unscored(explanation="judge not run / unparseable")
        return Score(
            value={
                k: verdict[k] for k in ("shape_fit", "clarifying_quality", "workflow_adherence")
            },
            answer=verdict.get("rationale", ""),
            metadata=verdict,
        )

    return score
