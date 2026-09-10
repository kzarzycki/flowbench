# Decisions — flowbench #104 (E02 S02.4)

1. **`TurnResult.artifact_exists` is removed, not re-fed from the probe.** The epic names
   it as a probe consumer, but nothing reads it: `rg artifact_exists` over both repos hits
   only constructions (`TurnResult(..., False)`), the field definition, and the *session
   dict* key (`normalize.py`, `run.py`), which stays. Keeping a driver-returned artifact
   field that the loop back-fills would leave the artifact concern in the driver's type —
   the thing the story removes — and add a per-turn filesystem probe nobody consumes.
   Source: issue title ("artifact concern out of the driver") + grep evidence.
2. **The session dict keeps `artifact_exists` / `artifact_path` / `artifact_text`, set by
   the loop.** Today `capture_session()` emits them for every session (`False/None/None`
   for `__none__`); `run.py` reads `artifact_text`, scenarios' `normalize.py` reads
   `artifact_exists`/`artifact_path`, and every `session.json` on disk carries them. The
   loop is where the probe lives, so it writes them — always, so `session.json`'s shape
   does not depend on whether a case declares an artifact.
3. **"Keep the S02.3 to_thread behaviour on the probe" = the probe runs in a worker thread
   under a wall-clock bound.** In the driver the check ran inside the send's
   `asyncio.timeout`. In the loop the DONE grace-poll is the bound: the poll runs under
   `asyncio.timeout(artifact_grace_s)`, so a hung filesystem ends the poll instead of the
   run (the abandoned thread finishes on its own, as S02.3 documents). The post-capture
   probe runs in a thread too, unbounded, exactly as `capture_session()`'s read was.
4. **`find_artifact` lives in `run.py`.** The orchestrator owns "which file proves
   delivery" (`docs/roadmap/target-architecture.md`); the loop only calls a `Callable`.
   Body = the old `artifact_path()` verbatim (top-level hit, else first `rglob` hit).
5. **`artifact_name` leaves `omni_factories`/`make_flow_driver_omni` too.** It was passed
   twice (to the factories for the driver, to `run_case` for the loop). One declaration
   remains: the `run_case`/`run_case_n` parameter. Scenario CLIs already pass it there.
6. **Fakes write the artifact to disk.** `FakeDriver` returned the plan as
   `capture_session()["artifact_text"]`; with the probe outside the driver that channel
   is gone, so `FakeDriver(plan, questions, run_dir=flow_dir)` writes `run_dir/plan.md`
   on `start()` and the real probe finds it — the fake models an agent, not a driver
   that knows about artifacts. `MissingPlanDriver` writes nothing.
7. **`rg __none__` scope.** Empty over both repos' code, tests, and current docs. Excluded:
   the scenarios ledger `LOG.md` (append-only history), `docs/superpowers/` and
   `.workflow/` in scenarios (archived plans/specs of shipped work), and gate
   artefacts under `.claude/engineering-loop/items/`. The roadmap line for S02.4 drops
   its `(kill artifact_name="__none__")` parenthetical; the epic's §S02.4 section is
   removed on ship (shipped sections are removed — flowbench #122, LOG 2026-09-09 lesson 2).
8. **Live gate.** The brief asks for one caffeinated todo_app run. todo_app declares no
   artifact, so its run exercises the `probe=None` path only. The probe path (DONE
   grace-poll + post-capture read) fires on swe_planning, so a `--n 1` swe_planning run is
   added as the second live gate.
