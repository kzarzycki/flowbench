# Acceptance scenario (black-box, mirrors acceptance.py)

Run in the finished workspace; each step is one point (7 total).
1. `python -m todo add "buy milk"` exits 0.
2. `add "pay rent"` and `add "call mom"` exit 0.
3. `list` output contains all three texts.
4. `done 1` exits 0.
5. `list` shows task 1 with a done marker.
6. Fresh-process `list` still shows 3 tasks, task 1 done (persistence).
7. `rm 2` exits 0; `list` drops "pay rent" only.
