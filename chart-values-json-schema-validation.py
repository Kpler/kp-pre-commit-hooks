#!/usr/bin/env python3

import os
import sys

import requests
import urllib3
from jsonschema import validate
from ruamel.yaml import YAML

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA_BASE_URL = "https://raw.githubusercontent.com/vl-kp/json-schema/main"
GITOPS_DIR = "gitops"


def download_schema_json(version):
    """
    Download json schema for chart version.
    """
    version_url = f"{SCHEMA_BASE_URL}/version.json"
    version_json = requests.get(version_url, timeout=10, verify=False).json()
    return_version = next(
        (
            item["JSONSchemaVersion"]
            for item in version_json["ranges"]
            if item["end"] >= version >= item["start"]
        ),
        None,
    )
    if return_version:
        schema_url = f"{SCHEMA_BASE_URL}/v{return_version}/schema-platform-managed-chart-strict.json"
        schema_json = requests.get(schema_url, timeout=10, verify=False).json()
        return schema_json
    return None


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


def validate_json_schema(merged_values, schema_data):
    """
    Validate merged values against json schema.
    """
    validate(instance=merged_values, schema=schema_data)


def main():
    """
    Main function.
    """
    if not os.path.exists(GITOPS_DIR):
        print(f"{GITOPS_DIR} directory is missing, exiting...")
        sys.exit(0)

    for app in os.listdir(GITOPS_DIR):
        app_path = os.path.join(GITOPS_DIR, app)
        if os.path.isdir(app_path):
            for svc in os.listdir(app_path):
                svc_path = os.path.join(app_path, svc)
                if os.path.isdir(svc_path):
                    chart_file = os.path.join(svc_path, "Chart.yaml")
                    value_file = os.path.join(svc_path, "values.yaml")
                    if os.path.isfile(chart_file) and os.path.isfile(value_file):
                        with open(chart_file, "r", encoding="utf8") as chart:
                            yaml = YAML()
                            chart_data = yaml.load(chart)
                            version = next(
                                (
                                    dep["version"]
                                    for dep in chart_data.get("dependencies", [])
                                    if dep["name"] == "platform-managed-chart"
                                ),
                                None,
                            )
                            if version:
                                schema_data = download_schema_json(version)
                                if schema_data:
                                    instance_files = [
                                        value_file
                                        for value_file in os.listdir(svc_path)
                                        if value_file.startswith("values-dev-")
                                        or value_file.startswith("values-prod-")
                                    ]
                                    for instance_file in instance_files:
                                        merged_values = merge_yaml_files(
                                            svc_path, instance_file
                                        )
                                        try:
                                            validate_json_schema(
                                                merged_values, schema_data
                                            )
                                        except Exception as err:
                                            print(
                                                f"Validation error for {instance_file}: {err}"
                                            )
                                            output_file = os.path.join(
                                                svc_path,
                                                f"error-merged-{instance_file}",
                                            )
                                            with open(
                                                output_file, "w", encoding="utf8"
                                            ) as output:
                                                output.write(
                                                    "# yaml-language-server: $schema=schema-platform-managed-chart.json\n"
                                                )
                                                yaml = YAML()
                                                yaml.dump(merged_values, output)
                                            sys.exit(err)
                                else:
                                    print(
                                        f"Chart version {version} is not supported in json schema, skipping..."
                                    )
                                    continue
                    else:
                        print(
                            f"Chart.yaml or values.yaml file is missing in {svc_path}, skipping..."
                        )
                        continue


if __name__ == "__main__":
    main()

