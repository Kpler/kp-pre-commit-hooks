#!/usr/bin/env bash

API_PACKAGE="${1}"
SPEC_FILE_PATH="${2}"

if uv lock --check --quiet 2>/dev/null ; then
    cmd="uv run --locked"
elif poetry check --lock --quiet 2>/dev/null ; then
    cmd="poetry run"
else
    cmd=""
fi
$cmd python -c '
import json
import sys

api_package = sys.argv[1]
spec_file_path = sys.argv[2]

app = getattr(__import__(api_package, fromlist=["app"]), "app")

new_spec = app.openapi()

with open(spec_file_path) as f:
    old_spec = json.load(f)

should_update_spec = old_spec != new_spec

if should_update_spec:
    print("OpenAPI specification has changed, writing the new one...")
    with open(spec_file_path, "w") as f:
        json.dump(app.openapi(), f, indent=4, sort_keys=True)
    exit(1)
print("OpenAPI specification has not changed")
exit(0)
' "$API_PACKAGE" "$SPEC_FILE_PATH"
