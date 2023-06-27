#!/usr/bin/env bash

API_PACKAGE="${1}"
SPEC_FILE_PATH="${2}"

poetry run python -c '
import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_package", required=True)
    parser.add_argument("--spec_file_path", required=True)
    args, _ = parser.parse_known_args()

    app = getattr(__import__(args.api_package, fromlist=["app"]), "app")

    new_spec = app.openapi()

    with open(args.spec_file_path) as f:
        old_spec = json.load(f)

    should_update_spec = old_spec != new_spec

    if should_update_spec:
        print("OpenAPI specification has changed, writing the new one...")
        with open(args.spec_file_path, "w") as f:
            json.dump(app.openapi(), f, indent=4, sort_keys=True)
        exit(1)
    print("OpenAPI specification has not changed")
    exit(0)


if __name__ == "__main__":
    main()
' --api_package $API_PACKAGE --spec_file_path $SPEC_FILE_PATH
