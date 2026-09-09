#!/bin/sh
# One worktree, one branch. Each worktree is bound to one branch: the main
# checkout to the default branch (origin/HEAD), a linked worktree to the first
# branch checked out in it (the one `git worktree add` gave it). A later switch
# to any other branch is reverted and fails. Git has no pre-checkout hook, so
# this runs after the switch and undoes it.
#
# Installed by pre-commit (`pre-commit install`, post-checkout stage in
# .pre-commit-config.yaml). Move a binding on purpose: GIT_REBIND=1 git switch <branch>
#
# git passes <prev HEAD> <new HEAD> <flag>; pre-commit passes the flag as
# PRE_COMMIT_CHECKOUT_TYPE instead. flag=1 is a branch checkout, 0 a file checkout.
[ "${3:-$PRE_COMMIT_CHECKOUT_TYPE}" = "1" ] || exit 0
branch=$(git symbolic-ref --quiet --short HEAD) || exit 0 # detached (rebase, bisect): allow
git_dir=$(git rev-parse --git-dir)
bind_file="$git_dir/worktree-branch" # per-worktree: .git/worktrees/<name>/ for linked ones
if [ -n "$GIT_REBIND" ] || [ ! -f "$bind_file" ]; then
    bound=$branch
    if [ -z "$GIT_REBIND" ] && [ "$git_dir" = "$(git rev-parse --git-common-dir)" ]; then
        # main checkout: bind the default branch, not whatever was checked out first
        bound=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
        bound=${bound:-$branch}
    fi
    printf '%s\n' "$bound" >"$bind_file"
    [ "$branch" = "$bound" ] && exit 0
else
    bound=$(cat "$bind_file")
    [ "$branch" = "$bound" ] && exit 0
fi

echo "post-checkout: this worktree is bound to '$bound'; switching to '$branch' is not allowed." >&2

# `checkout -B` / `switch -C` reset the target branch before we run. Its old tip is
# reflog @{1}; the reset shows as a "branch: Reset to" entry written just now.
# ponytail: 5s freshness window instead of exact attribution; git gives us nothing better.
now=$(date +%s)
entry=$(git reflog show --date=unix --format='%gd %gs' "refs/heads/$branch" -1 2>/dev/null)
case "$entry" in
"$branch@{"*"} branch: Reset to "*)
    at=${entry#*@\{}; at=${at%%\}*}
    if [ $((now - at)) -le 5 ] && old=$(git rev-parse --verify --quiet "$branch@{1}"); then
        git update-ref "refs/heads/$branch" "$old" && echo "  restored '$branch' to $old (it was reset by -B/-C)." >&2
    fi
    ;;
esac

if git switch --quiet "$bound"; then
    echo "  reverted to '$bound'." >&2
else
    echo "  REVERT FAILED: HEAD is still on '$branch'. Fix by hand (git switch <branch>) or rebind: GIT_REBIND=1 git switch $branch" >&2
fi
cat >&2 <<MSG
  One worktree, one branch:  git worktree add ../$(basename "$(git rev-parse --show-toplevel)")--<slug> $branch
MSG
exit 1
