# Self-answered questions (loop rule 3) — issue #62

1. **Does the patch section describe a patch, or its absence?** Its absence. Probed: the
   script cannot locate the bridge in the installed layout and the upstream fix is
   structural (rule-anchored scan). Documenting a patch step that is not needed would be
   the worst outcome for onboarding.
2. **Delete `scripts/patch_omnigent.py` in a docs item?** Yes. E02 S02.5 already recorded
   the owner-approved trigger ("when a release carries it, delete `scripts/patch_omnigent.py`
   and its README mention, and bump the pin"); the trigger is verified met. Leaving dead
   code that the new doc has to explain away is the leaf fix.
3. **Bump the `live` pins (0.1.1 → 0.13.x) too?** No. The driven version is a source
   checkout, not a PyPI release, and a pin bump is a runtime change needing live
   validation — out of a docs item. S02.5 keeps the pin item; onboarding states the split
   (client pin vs driven server) as current truth.
4. **Which path variable for run dirs?** `$RUNS`, matching the existing `$SCENARIOS` /
   `$FLOWBENCH` convention (08-20 path policy), defined in CLAUDE.md and given a concrete
   value only in untracked `CLAUDE.local.md`.
5. **Does onboarding duplicate `$SCENARIOS/docs/knowledge/omnigent.md`?** No — it links it
   for operational gotchas and carries only what an engine contributor needs to get a run
   going. The knowledge file stays the operations note; it is in the private repo, so the
   public-facing subset (key rule, readiness, topology) is restated here on purpose.
