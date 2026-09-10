# Plan — flowbench #105 part 2
1. Edit `omnigent.py`: import, two label reads, two UPSTREAM markers. Update `tests/driver/test_omnigent.py`
   fakes (`_patch_start` patches `omnigent_client.SessionsChat`; label tests stub `_client.sessions.get`).
2. Gate 1+2 folded (S): codex review of spec+diff. Gate 3: codex whole-branch. Gate 4: suite + ruff + rebase.
3. PR → merge; V4 `todo_app` live run under `caffeinate -i`; ledger + HANDOFF in the paired scenarios PR.
