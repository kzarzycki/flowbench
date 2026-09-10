Gate 2, attempt 1 — verdict REVISE (Claude reviewer, opus, fresh context).

Reviewer independently rebuilt the literal inventory (23 sites in `src/`) and, for
objection (d), mutated the sense of every swept comparison one at a time: all nine
mutations are caught by the existing suite (`driver.py:443` detected as a hang, not a
failure). Confirmed on this interpreter that `json.dumps` emits `"idle"` for BOTH
`StrEnum` and `(str, Enum)` — so `test_fstring_is_bare_value` is the load-bearing guard.

Objections, all fixed in plan.md (and decisions.md for #6):
1. AC6 had no test — `test_user_model_implementations` proves AC5 and passes whether or
   not the signature was touched. Added `test_user_model_annotation_and_docstring`
   (`get_type_hints(run_agent_session)["user_model"] is UserModel`, docstring check).
2. (Sharpest catch.) The V2 gate as written validates **master**, not the branch:
   `$SCENARIOS/pyproject.toml:36` sources flowbench from `{ git = ..., branch = "master" }`
   with the commit pinned in `uv.lock`, so `uv sync && pytest` never loads
   `flowbench/types.py`. Gate 5 now mandates `uv pip install -e <engine worktree>` and
   records that line in `gates.md` as evidence.
3. T2's site list omitted `driver.py:443` (the `seen_running` latch — the one whose
   mutation hangs the suite) and the comments at 169/176. Replaced with the verified
   14-site list plus "the grep is the definition of done".
4. T3's list was incomplete and the tests/ sweep had no completeness gate (AC2's grep is
   `src/`-only). Added the full verified inventory and gate 2 (`rg ... tests/` → only
   `tests/report/test_run_report.py:122,128`).
5. T4's "if such prose exists" was conditional where the fact is knowable:
   `docs/design/runner.md:57-59`. Named, with the replacement specified as a
   member → meaning → producer table.
6. decisions.md #4's premise was false — `$SCENARIOS` does consume this in live code
   (`scripts/codex_review.py:76`, `tests/test_codex_review.py:7`). Corrected in place;
   that consumer is now named as the reason the re-export must stay and the reason
   objection 2 matters.
7. (Non-blocking) `runtime_checkable` isinstance checks attribute presence only. Added the
   negative control `assert not isinstance(object(), UserModel)`.

Ordering (b) confirmed sound; T1's interfaces confirmed implementable without judgment;
`flowbench.types` imports nothing from `flowbench`, so no cycle.
