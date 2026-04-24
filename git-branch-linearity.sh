#!/bin/sh

# Use parameter passed to the script or default to master
TARGET_BRANCH="${1:-main}"

echo "Target branch: $TARGET_BRANCH"

# Only fetch shallowly if the clone is already shallow. On a full local clone
# (typical dev setup), `--depth=1` would truncate origin/$TARGET_BRANCH to a
# single commit and write a `.git/shallow` file, leaving the developer's main
# detached from prior history.
if [ -f "$(git rev-parse --git-dir)/shallow" ]; then
    fetch_depth="--depth=1"
else
    fetch_depth=""
fi

git fetch --no-tags $fetch_depth origin "$TARGET_BRANCH"
target_sha=$(git rev-parse FETCH_HEAD)

# If in a github PR, base from tip of branch, not the merge commit.
if [ -n "$GITHUB_HEAD_REF" ]; then
    # --shallow-exclude requires a ref name (branch/tag), not a SHA: the value
    # is forwarded to the server as `deepen-not <ref>` in protocol v2, which
    # rejects commit ids.
    if ! git fetch --no-tags --shallow-exclude="$TARGET_BRANCH" origin "$GITHUB_HEAD_REF"; then
        # Fallback for remotes that do not honor shallow-exclude.
        git fetch --no-tags origin "$GITHUB_HEAD_REF"
    fi
    # Read from FETCH_HEAD rather than origin/$GITHUB_HEAD_REF: the origin
    # remote in a CI clone (actions/checkout, clone --depth=1) has a narrow
    # refspec that does not map arbitrary branches into refs/remotes/origin/*.
    tip=$(git rev-parse FETCH_HEAD)
else
    tip="HEAD"
fi

out=$(git log "${target_sha}..${tip}" --merges --oneline)
exit_status=$?

if [ -n "$out" ]
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
