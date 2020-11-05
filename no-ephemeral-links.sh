#!/usr/bin/env bash
exit_status=0

for i
do
  grep "$i" -e "://kpler.slack.com" -e "://kpler1.atlassian.net/browse" -e "://app.clubhouse.io/kplertechnology" --with-filename --line-number | awk '{print "- "$1}'
  if [ ${PIPESTATUS[0]} -eq 0 ]
  then
    exit_status=1
  fi
done
exit ${exit_status}
