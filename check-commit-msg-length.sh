#!/usr/bin/env bash
exit_status=0

# Get the current branch and apply it to a variable
currentbranch=`git symbolic-ref --short HEAD`
echo $currentbranch
# Gets the commits for the current branch and outputs to file
git log $currentbranch --pretty=format:"%h" --not origin/master > shafile.txt

# loops through the file an gets the message
for i in `cat ./shafile.txt`;
do
  # gets the git commit message based on the sha
  gitmessage=`git log --format=%B -n 1 "$i"`
  firstline=`echo "$gitmessage" | head -n 1`

  if [[ $(expr length "$firstline") -gt 72 ]]
  then
    exit_status=1
    echo "Commit $i with message too long: $firstline"
  fi

done
rm shafile.txt
exit ${exit_status}
