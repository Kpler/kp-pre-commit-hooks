#!/bin/sh
out=$(git log origin/master..HEAD --merges --oneline)

exit_status=$?
if [ -n  "$out" ]
then
    echo "Please rebase your branch" >&2
    echo "If your branch or its base branch is a release branch then ignore this error" >&2
    echo "\nMerge commit(s):" >&2
    echo "$out" >&2
    # Disclaimer: current version of the check doesn't work well with release branches
exit_status=1
fi

exit ${exit_status}
