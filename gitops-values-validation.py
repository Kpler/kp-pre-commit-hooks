#!/usr/bin/env python3

import os
import sys

import requests
import urllib3
from jsonschema import validate
from ruamel.yaml import YAML

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA_BASE_URL = (
    "https://kp-helmchart-stable-shared-main.s3.eu-west-1.amazonaws.com/schema/"
)
GITOPS_DIR = "gitops"


def download_schema_json(version):
    """
    Download json schema for chart version.
    """
    schema_url = (
        f"{SCHEMA_BASE_URL}/v${version}/schema-platform-managed-chart-strict.json"
    )
    schema_json = requests.get(schema_url, timeout=10, verify=False).json()
    return schema_json


def verify_schema_version(version, directory="."):
    """
    Verify if schema version in the values yaml are correct.
    """
    for filename in os.listdir(directory):
        if (not filename.startswith("values")) or (not filename.endswith(".yaml")):
            continue

        file_path = os.path.join(directory, filename)
        with open(file_path, "r", encoding="utf8") as value_file:
            for line in value_file:
                if line.startswith("# yaml-language-server: $schema="):
                    schema_version = line.split("=")[1].split("/")[-2].replace("v", "")
                    if schema_version != version:
                        print(
                            f"JSON schema version {line} in {file_path} is not match with Chart.yaml, exiting..."
                        )
                        sys.exit(3)
    return True


def delete_error_files(directory="."):
    """
    Delete error files.
    """
    for filename in os.listdir(directory):
        if (not filename.startswith("error-merged-values-")) or (
            not filename.endswith(".yaml")
        ):
            continue

        file_path = os.path.join(directory, filename)
        try:
            os.remove(file_path)
        except Exception as err:
            print(f"Error deleting {file_path}. Reason: {err}")
            continue


def deep_merge(source, destination):
    """
    Deep merge dictionaries.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # Get node or create one
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value

    return destination


def merge_yaml_files(svc_path, instance_file):
    """
    Merge values.yaml, values-env.yaml and values-env-instance.yaml files.
    """
    yaml = YAML()
    merged_data = {}

    # Base file
    with open(os.path.join(svc_path, "values.yaml"), "r", encoding="utf8") as base_file:
        merged_data.update(yaml.load(base_file))

    # Environment file
    env = "dev" if "dev" in instance_file else "prod"
    env_file_path = os.path.join(svc_path, f"values-{env}.yaml")
    if os.path.exists(env_file_path):
        with open(env_file_path, "r", encoding="utf8") as env_file:
            env_data = yaml.load(env_file)
        deep_merge(env_data, merged_data)

    # Instance file
    with open(
        os.path.join(svc_path, instance_file), "r", encoding="utf8"
    ) as instance_f:
        instance_data = yaml.load(instance_f)
    deep_merge(instance_data, merged_data)

    return merged_data


def main():
    """
    Main function.
    """
    if not os.path.exists(GITOPS_DIR):
        print(f"{GITOPS_DIR} directory is missing, exiting...")
        sys.exit(0)

    for app in os.listdir(GITOPS_DIR):
        app_path = os.path.join(GITOPS_DIR, app)
        if not os.path.exists(app_path):
            print(f"{app_path} directory does not exist, exiting...")
            continue

        for svc in os.listdir(app_path):
            svc_path = os.path.join(app_path, svc)
            if not os.path.isdir(svc_path):
                print(f"{svc_path} is not a directory, skipping...")
                continue

            chart_file = os.path.join(svc_path, "Chart.yaml")
            value_file = os.path.join(svc_path, "values.yaml")
            if (not os.path.isfile(chart_file)) or (not os.path.isfile(value_file)):
                print(
                    f"Chart.yaml or values.yaml file is missing in {svc_path}, skipping..."
                )
                continue

            with open(chart_file, "r", encoding="utf8") as chart:
                yaml = YAML()
                chart_data = yaml.load(chart)

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

            verify_schema_version(chart_version)
            schema_data = download_schema_json(chart_version)

            if not schema_data:
                print(
                    f"JSON schema for version {chart_version} is not supported, skipping..."
                )
                continue

            instance_files = [
                value_file
                for value_file in os.listdir(svc_path)
                if value_file.startswith("values-dev-")
                or value_file.startswith("values-prod-")
            ]

            for instance_file in instance_files:
                merged_values = merge_yaml_files(svc_path, instance_file)
                try:
                    validate(instance=merged_values, schema=schema_data)
                    delete_error_files(svc_path)
                except Exception as err:
                    print(f"Validation error for {instance_file}: {err}")
                    output_file = os.path.join(
                        svc_path, f"error-merged-{instance_file}"
                    )
                    with open(output_file, "w", encoding="utf8") as out:
                        out.write(
                            f"# yaml-language-server: $schema={SCHEMA_BASE_URL}/v${chart_version}/schema-platform-managed-chart-strict.json\n"
                        )
                        yaml = YAML()
                        yaml.dump(merged_values, out)
                    sys.exit(err)


if __name__ == "__main__":
    main()
