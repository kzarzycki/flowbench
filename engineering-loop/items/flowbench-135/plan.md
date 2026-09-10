# Plan — flowbench #135

- Task 1 (done, fork `b0674b43`): `auto-sync.sh` — `busy()`/`defer_or_go()`/`restart_server()`,
  `restart-pending` handling before the `last-run` check, restart guarded at the apply site.
  Check (AC3): extract the three functions with `sed` and run `defer_or_go restart` against the
  live server (expect rc 1 + tick line) and with `PORT=1` (expect rc 0, `busy` rc 1).
- Task 2: `docs/onboarding.md` fifth rule + `docs/design/runner.md` sentence (AC1, AC2).
  Check: `git diff origin/master --stat` lists only the two docs.
- Task 3 (V): the `s135-repro-1` run finishes with superpowers `idle`; record in gates.md.
