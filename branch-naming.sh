#!/bin/bash

exit_status=0
currentbranch=$(git symbolic-ref --short HEAD)
dependabot="dependabot"
mergequeue="gh-readonly-queue"
# NOTE: Branches created by Dependabot does not have any limit, according to
# https://github.com/dependabot/dependabot-core/issues/396, that's why we allow them
if [ "$(expr length "$currentbranch")" -gt 70 ] && [[ ! "$currentbranch" =~ $dependabot ]] && [[ ! "$currentbranch" =~ $mergequeue ]]
then
  exit_status=1
  echo "Branch name too long, should be less than 70 characters."
fi
exit ${exit_status}
