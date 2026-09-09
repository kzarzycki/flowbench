#!/usr/bin/env bash
# Reject symlinks whose target does not resolve. pre-commit passes candidate
# symlink files as arguments.
set -eu
fail=0
for f in "$@"; do
  [ -L "$f" ] || continue
  if [ ! -e "$f" ]; then
    printf 'dangling symlink: %s -> %s\n' "$f" "$(readlink "$f")" >&2
    fail=1
  fi
done
exit "$fail"
