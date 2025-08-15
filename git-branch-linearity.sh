#!/bin/sh

# Use parameter passed to the script or default to master
TARGET_BRANCH="${1:-main}"

echo "Target branch: $TARGET_BRANCH"
git fetch --no-tags --depth=1 origin $TARGET_BRANCH 2> /dev/null
target_sha=$(git rev-parse origin/${TARGET_BRANCH})

# If in a github PR, base from tip of branch, not the merge commit
if [ -n "$GITHUB_HEAD_REF" ]; then
    git fetch --no-tags --shallow-exclude="$target_sha" origin "$GITHUB_HEAD_REF"  2> /dev/null
    tip=$(git rev-parse origin/$GITHUB_HEAD_REF)
else
    tip="HEAD"
fi

out=$(git log ${target_sha}..${tip} --merges --oneline)
exit_status=$?

if [ -n  "$out" ]
then
    echo "Please rebase your branch" >&2
    echo "If your branch or its base branch is a release branch then ignore this error" >&2
    echo >&2
    echo "Merge commit(s):" >&2
    echo "$out" >&2
    # Disclaimer: current version of the check doesn't work well with release branches
    exit_status=1
fi
exit ${exit_status}
