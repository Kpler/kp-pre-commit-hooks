#!/bin/bash

exit_status=0
currentbranch=`git symbolic-ref --short HEAD`
if [ $(expr length "$currentbranch") -gt 70 ]
then
  exit_status=1
  echo "Branch name too long, should be less than 70 characters."
fi
exit ${exit_status}
