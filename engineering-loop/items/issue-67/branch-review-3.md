(wrapper captured an intermediate message; verdict copied from the codex session)

REVISE

1. driver.py:475: `had_children` not cleared when a real wake-up `running` poll is observed; idle+busy -> running -> idle re-arms `cleared_at` and waits `child_wake_s` anyway.
2. driver.py:501: timeout fallthrough returns the last raw `st`, so it can return `idle` while the wake wait is still unmet -> next simulator inject hits the same race.
