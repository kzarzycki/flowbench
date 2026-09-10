# Decisions — flowbench #80 (E02 S02.2)

Questions the loop answered from the epic + code rather than escalating
(loop.md rule 3).

1. **`AgentDriver` lives in `driver/base.py`, not `driver/__init__.py`.**
   `target-architecture.md`'s module map comments the ABC onto `__init__.py`.
   Defining it there and re-exporting `OmnigentDriver` from the same file needs
   a bottom-of-file import (`omnigent.py` subclasses the ABC), which is a
   circular-import trick plus a `# noqa: E402`. `base.py` + a pure re-export
   `__init__.py` gives the same public surface with no cycle. The module map's
   comment is updated to match (AC10).

2. **`git_init_repo` stays with `OmnigentDriver`, not in `bundle.py`.**
   It seeds the *run dir* (the agent's cwd), not the agent bundle; its only
   caller is `OmnigentDriver.start`. `bundle.py` is defined by the epic as the
   AGENT_CONFIG template + the tar. A third module for 22 lines is not worth
   the file. Its test moves to `tests/driver/test_config.py` with the rest of
   that file, unchanged.

3. **`driver/omnigent.py` will not reach the epic's "~350 lines"; the epic line
   is amended instead of the scope widened.** The epic wrote that number
   against a 575-line driver. Since then #68 (paged `_list_items`, live
   `/child_sessions` read) and #76 (wake-up wait after children clear) added
   ~90 lines to exactly the code S02.2 must keep. Removing the ABC (19), the
   config/bundle/metadata block (~102), and `_to_jsonable` (12) leaves ~480.
   The only way to 350 is to split the polling machinery
   (`_wait_idle`/`_snapshot`/`_children`/`_read_retry`/`_list_items`, ~142
   lines) — which the epic explicitly assigns to `OmnigentDriver`
   ("keeps: lifecycle, send/settle, capture, URLs") and which S02.3 rewrites
   under a single wall-clock budget. Splitting it twice, once mechanically and
   once for real, is churn on the most incident-prone file in the repo
   (epic § Risks). Decision: report the real number, amend the epic's Verify
   line to it, and note S02.3 as where the rest goes.

4. **`_create_metadata` moves to `bundle.py` as `session_metadata(spec)`.**
   The epic names only `render_config` and `build_bundle`, but the harness-gated
   `terminal_launch_args` + title/label form part is the same concern: it is
   per-flow launch configuration derived from the same `Flow`-like fields
   (`harness`, `session_title`, `project`) that `render_config` reads. Leaving
   it behind would keep config rendering in two files. Behavior-preserving: the
   body moves verbatim.

5. **`BundleSpec` is a `Protocol`, not a new dataclass.** The epic says "pure
   functions of a `Flow`-like spec". `OmnigentDriver` already carries every
   field; a Protocol makes the three functions typed and testable without a
   parallel data class to keep in sync with `runner/flow.Flow` (which S03.1
   widens anyway). Not `runtime_checkable` — nothing does isinstance on it.

6. **`OmnigentDriver.render_config()` and `._build_bundle()` survive as
   one-line delegates.** `tests/driver/test_bundle.py`, `test_config.py` and
   `docs/design/runner.md:21` all name them. Deleting them would be a
   behavior change to the class's surface in a story whose contract is
   "behavior-preserving", and would churn the tests the epic says merely
   "move with them".

7. **`_to_jsonable` becomes public `transcript.to_jsonable`.** The epic says
   `transcript.py` "absorbs anything transcript-shaped still in the driver".
   It is the last such thing. Public (no underscore) because it now crosses a
   module boundary; `transcript.py`'s other members are public for the same
   reason.

8. **Both shims re-export; neither warns.** S02.1 set the precedent
   (`flowbench.runner.driver` re-exports `TurnResult`/`TurnStatus` with no
   `DeprecationWarning`) and the downstream consumers are two files in one
   private repo (`scripts/codex_review.py:23`, `tests/test_codex_review.py:7`),
   updated in the paired scenarios PR. A warning would fire in every live run's
   stderr for no reader.

9. **Downstream imports are updated in the same wave, not left on the shim.**
   The scenarios PR points `scripts/codex_review.py` and
   `tests/test_codex_review.py` at `flowbench.driver`. The shim exists for
   *unreleased* consumers and for the one-release policy, not as the steady
   state.

10. **V4 is run, not waived.** S02.2's Verify line names V1 and V2 only, but
    `docs/roadmap/verification.md:43-44` makes V4 mandatory "after any change to
    `driver.py`, `loop.py`, or the send/retry policy" — and this story moves both
    files. Two rules, one conflict. The blanket rule wins: it exists because
    "pure" driver changes killed runs #30/#34/#39, and an import-time or
    module-identity mistake in a package split is exactly the class of defect an
    offline suite can miss and a live run cannot. Running V4 (~10 min) is
    cheaper than amending a policy written from incident history. AC12.
    (Gate 1, objection 1.)

11. **The shims re-export names, not module internals.**
    `flowbench.runner.driver` after this story has no `asyncio` attribute, so
    `monkeypatch.setattr("flowbench.runner.driver.asyncio.sleep", ...)` stops
    patching the code under test — silently, since `setattr` on a missing
    attribute of an existing module raises but a *stale* patch on a re-exported
    module would not. Every such target is migrated to the canonical module and
    AC4b greps for regressions. Patching a module's private imports was never a
    supported surface; the one-release compat covers *imports*, which is what
    downstream actually does. (Gate 1, objection 3.)

12. **The pre-existing bundle/config tests are not sufficient evidence of
    "behavior-preserving".** They assert substrings and extracted paths, not the
    rendered bytes. AC7 adds golden assertions captured from `origin/master`
    *before* the move, for the config string, the tar member list, and both
    `_create_metadata` variants. Without them a `self.` → `spec.` transcription
    slip in a comment-heavy 100-line block could pass. (Gate 1, objection 4.)
