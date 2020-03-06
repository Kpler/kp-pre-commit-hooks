#!/bin/sh
out=$(git log origin/master..HEAD --merges)

exit_status=$?
if [ -n  "$out" ]
then
    echo "Please rebase your branch, merge commit(s):" >&2
    echo "$out" >&2
exit_status=1
fi

exit ${exit_status}
