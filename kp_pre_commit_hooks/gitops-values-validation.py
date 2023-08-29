#!/usr/bin/env python3

import json
import sys
from itertools import chain
from pathlib import Path

import requests
import urllib3
from jsonschema import Draft7Validator
from ruamel.yaml import YAML

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA_BASE_URL = "https://kp-helmchart-stable-shared-main.s3.eu-west-1.amazonaws.com/schema/platform-manager-chart"
GITOPS_DIR = Path("gitops")

yaml = YAML()


def download_json_schema_for_chart_version(version):
    schema_url = f"{SCHEMA_BASE_URL}/v{version}/schema-platform-managed-chart-strict.json"
    response = requests.get(schema_url, timeout=10, verify=False)

    if response.status_code != 200:
        print(
            f"Error fetching schema url {schema_url}. HTTP Status Code: {response.status_code}\nPlease enable VPN first."
        )
        sys.exit(4)

    try:
        schema_json = response.json()
        return schema_json
    except json.JSONDecodeError:
        print(f"Error decoding JSON. Response content:\n{response.text}")
        sys.exit(4)


def verify_values_files_schema_version(version, directory=Path(".")):
    for filename in directory.glob("values*.yaml"):
        value_file = filename.read_text(encoding="utf8")
        for line in value_file.splitlines():
            if line.startswith("# yaml-language-server: $schema="):
                schema_version = line.split("=")[1].split("/")[-2].replace("v", "")
                if schema_version != version:
                    print(f"ERROR: validation failure for {directory}/{filename}")
                    print(
                        f"reason: JSON schema version in '{line}' does not match version in Chart.yaml"
                    )
                    return False
    return True


def delete_error_files(directory=Path(".")):
    for filename in directory.glob("error-merged-values-*.yaml"):
        try:
            filename.unlink()
        except Exception as err:
            print(f"Error deleting {filename}. Reason: {err}")


def deep_merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            # Get node or create one
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value

    return destination


def merge_service_values_files(service_path, instance_file):
    """Merge values.yaml, values-env.yaml and values-env-instance.yaml files."""
    merged_data = {}

    # Base file
    base_file = (service_path / "values.yaml").read_text(encoding="utf8")
    merged_data.update(yaml.load(base_file))

    # Environment file
    env = "dev" if "dev" in instance_file else "prod"
    env_file_path = service_path / f"values-{env}.yaml"
    if env_file_path.exists():
        env_file = env_file_path.read_text(encoding="utf8")
        env_data = yaml.load(env_file)
        deep_merge(env_data, merged_data)

    # Instance file
    instance_f = (service_path / instance_file).read_text(encoding="utf8")
    instance_data = yaml.load(instance_f)
    deep_merge(instance_data, merged_data)

    return merged_data


def find_full_error_path(error):
    if error.parent:
        return find_full_error_path(error.parent) + error.path
    else:
        return error.path


def main():
    if not GITOPS_DIR.exists():
        print(f"{GITOPS_DIR} directory is missing, exiting...")
        sys.exit(0)

    error_found = False

    # Iterate over direct subdirectories inside GITOPS_DIR
    for service_path in GITOPS_DIR.glob("*/*"):
        chart_file = service_path / "Chart.yaml"
        value_file = service_path / "values.yaml"
        if not (chart_file.is_file() and value_file.is_file()):
            print(f"Chart.yaml or values.yaml file is missing in {service_path}, skipping...")
            continue

        chart_data = yaml.load(chart_file.read_text(encoding="utf8"))
        chart_version = next(
            (
                dep["version"]
                for dep in chart_data.get("dependencies", [])
                if dep["name"] == "platform-managed-chart"
            ),
            None,
        )

        if not chart_version:
            print(
                f"Chart.yaml {chart_file} is missing platform-managed-chart dependency, skipping..."
            )
            continue

        if not verify_values_files_schema_version(chart_version, service_path):
            error_found = True
            continue

        schema_data = download_json_schema_for_chart_version(chart_version)
        if not schema_data:
            print(f"JSON schema for version {chart_version} is not supported, skipping...")
            continue

        for instance_file_path in chain(
            service_path.glob("values-dev-*.yaml"),
            service_path.glob("values-prod-*.yaml"),
        ):
            instance_file = instance_file_path.name
            merged_values = merge_yaml_files(service_path, instance_file)

            validator = Draft7Validator(schema_data)
            errors = list(validator.iter_errors(merged_values))

            if errors:
                base_file = "-".join(instance_file.split("-")[:2]) + ".yaml"
                print(
                    f"Validation errors for {instance_file} or {base_file} or values.yaml:"
                )
                for error in errors:
                    print(f"- {error.message}")
                output_file = service_path / f"error-merged-{instance_file}"
                with output_file.open("w", encoding="utf8") as out:
                    out.write(
                        f"# yaml-language-server: $schema={SCHEMA_BASE_URL}/v${chart_version}/schema-platform-managed-chart-strict.json\n"
                    )
                    yaml.dump(merged_values, out)
                sys.exit(1)

            delete_error_files(service_path)


if __name__ == "__main__":
    main()

