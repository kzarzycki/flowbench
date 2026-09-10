#!/usr/bin/env bash
# Mirror a loop phase onto the Project board (https://github.com/users/kzarzycki/projects/1)
# and claim the issue for the calling agent session.
# usage: board.sh <issue-url> <PHASE>
#   PHASE: TRIAGED|SPEC|SPEC_APPROVED|PLAN|PLAN_APPROVED|IMPLEMENTED|BRANCH_APPROVED|GATES_GREEN|MERGED|PARKED
#          CLOSED — closed without shipping: Status Done, Phase left at the last phase actually reached
# env:   AGENT_SESSION=<harness>:<id>   this session's identity (auto: claude-code:$CLAUDE_CODE_SESSION_ID)
#        AGENT_PARENT_SESSION=<harness>:<id>   the session that spawned this one (optional)
# Effects: Status + Phase fields set; Session field = AGENT_SESSION (latest wins); once per session an
# append-only comment "session <id> started <utc> parent=<pid> cwd=<dir>" — the issue's session history.
set -euo pipefail
url=$1; phase=$2
PROJECT=PVT_kwHOAD9xXM4Bi7ga
STATUS=PVTSSF_lAHOAD9xXM4Bi7gazhhxwZI
PHASE=PVTSSF_lAHOAD9xXM4Bi7gazhhxwoo
SESSION=PVTF_lAHOAD9xXM4Bi7gazhhyF5o
# ponytail: macOS ships bash 3.2 (no associative arrays) — one case does both lookups
case $phase in
  TRIAGED)         opt=6f4e3ac5; status=98fc5d88 ;;  # Todo
  SPEC)            opt=e05b5eae; status=09ff9594 ;;  # In progress
  SPEC_APPROVED)   opt=3dffb5ce; status=09ff9594 ;;
  PLAN)            opt=3a066acb; status=09ff9594 ;;
  PLAN_APPROVED)   opt=98340852; status=09ff9594 ;;
  IMPLEMENTED)     opt=388039d9; status=09ff9594 ;;
  BRANCH_APPROVED) opt=a25c1eba; status=19c88bde ;;  # In review
  GATES_GREEN)     opt=9f024e85; status=19c88bde ;;
  MERGED)          opt=55791a58; status=c25c871f ;;  # Done
  PARKED)          opt=52181f3c; status=8cde8890 ;;  # Backlog
  CLOSED)          opt=;         status=c25c871f ;;  # Done, and no phase written
  *) echo "unknown phase: $phase" >&2; exit 2 ;;
esac
sid=${AGENT_SESSION:-${CLAUDE_CODE_SESSION_ID:+claude-code:$CLAUDE_CODE_SESSION_ID}}
item=$(gh project item-add 1 --owner kzarzycki --url "$url" --format json -q .id)
if [ -n "$opt" ]; then  # CLOSED writes no phase; an `&&` guard would trip `set -e` on the skip
  gh project item-edit --project-id $PROJECT --id "$item" --field-id $PHASE --single-select-option-id "$opt" >/dev/null
fi
gh project item-edit --project-id $PROJECT --id "$item" --field-id $STATUS --single-select-option-id "$status" >/dev/null
if [ -n "$sid" ]; then
  gh project item-edit --project-id $PROJECT --id "$item" --field-id $SESSION --text "$sid" >/dev/null
  if ! gh issue view "$url" --json comments -q '.comments[].body' | grep -q "^session $sid started"; then
    gh issue comment "$url" --body "session $sid started $(date -u +%Y-%m-%dT%H:%MZ) parent=${AGENT_PARENT_SESSION:-none} cwd=$(basename "$PWD")" >/dev/null
  fi
fi
what=${opt:+Phase=$phase}; what=${what:-"Status=Done (Phase unchanged)"}
echo "$url → $what${sid:+ Session=$sid}"
