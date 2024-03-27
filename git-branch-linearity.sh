#!/bin/sh

# Use parameter passed to the script or default to master
TARGET_BRANCH="${1:-main}"

echo "Target branch: $TARGET_BRANCH"
git fetch origin $TARGET_BRANCH 2> /dev/null


# Detection of (PR) merge commits at tip of HEAD:
target_sha=$(git rev-parse origin/${TARGET_BRANCH})
# Get SHA of parent commit
merge_target=$(git log --merges --oneline --parents --no-abbrev-commit HEAD^..HEAD | cut -d" " -f2)
# If parent is the target branch, start from the commit before the merge commit
if [ "$target_sha" = "$merge_target" ] ; then
    tip="HEAD^"
else
    tip="HEAD"
fi

out=$(git log origin/${TARGET_BRANCH}..${tip} --merges --oneline)
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
