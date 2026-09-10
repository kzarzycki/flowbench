# Gate 1 — spec review (Claude, fresh context)

Attempt 1: REVISE — 5 objections (fixture case missing; GENERATE_* placement cycle; watch main vs required runs_root; runs_root.name derivation not behavior-preserving; AC2 lacked --exact / AC3 grep too narrow). All fixed in spec.md/decisions.md.

Attempt 2: APPROVE. Verified all five fixes. Implementer notes: also repoint the `run_agent_session` monkeypatch (test line 332) to `flowbench.run.run_agent_session`; `uv run --exact` prunes spike deps — re-sync before running the scenarios suite.
