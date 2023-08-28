#!/usr/bin/env python3

import sys
from pathlib import Path

import requests
import urllib3
from jsonschema import validate
from ruamel.yaml import YAML

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA_BASE_URL = (
    "https://kp-helmchart-stable-shared-main.s3.eu-west-1.amazonaws.com/schema/"
)
GITOPS_DIR = Path("gitops")


def download_schema_json(version):
    """
    Download json schema for chart version.
    """
    schema_url = (
        f"{SCHEMA_BASE_URL}/v${version}/schema-platform-managed-chart-strict.json"
    )
    schema_json = requests.get(schema_url, timeout=10, verify=False).json()
    return schema_json


def verify_schema_version(version, directory=Path(".")):
    """
    Verify if schema version in the values yaml are correct.
    """
    for filename in directory.iterdir():
        if (not filename.name.startswith("values")) or (
            not filename.name.endswith(".yaml")
        ):
            continue

        value_file = filename.read_text(encoding="utf8")
        for line in value_file.splitlines():
            if line.startswith("# yaml-language-server: $schema="):
                schema_version = line.split("=")[1].split("/")[-2].replace("v", "")
                if schema_version != version:
                    print(
                        f"JSON schema version {line} in {filename} is not match with Chart.yaml, exiting..."
                    )
                    sys.exit(3)
    return True


def delete_error_files(directory=Path(".")):
    """
    Delete error files.
    """
    for filename in directory.iterdir():
        if (not filename.name.startswith("error-merged-values-")) or (
            not filename.name.endswith(".yaml")
        ):
            continue

        try:
            filename.unlink()
        except Exception as err:
            print(f"Error deleting {filename}. Reason: {err}")


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
    base_file = (svc_path / "values.yaml").read_text(encoding="utf8")
    merged_data.update(yaml.load(base_file))

    # Environment file
    env = "dev" if "dev" in instance_file else "prod"
    env_file_path = svc_path / f"values-{env}.yaml"
    if env_file_path.exists():
        env_file = env_file_path.read_text(encoding="utf8")
        env_data = yaml.load(env_file)
        deep_merge(env_data, merged_data)

    # Instance file
    instance_f = (svc_path / instance_file).read_text(encoding="utf8")
    instance_data = yaml.load(instance_f)
    deep_merge(instance_data, merged_data)

    return merged_data


def main():
    """
    Main function.
    """
    if not GITOPS_DIR.exists():
        print(f"{GITOPS_DIR} directory is missing, exiting...")
        sys.exit(0)

    for app in GITOPS_DIR.iterdir():
        app_path = GITOPS_DIR / app
        if not app_path.exists():
            print(f"{app_path} directory does not exist, exiting...")
            continue

        for svc in app_path.iterdir():
            svc_path = app_path / svc
            if not svc_path.is_dir():
                print(f"{svc_path} is not a directory, skipping...")
                continue

            chart_file = svc_path / "Chart.yaml"
            value_file = svc_path / "values.yaml"
            if (not chart_file.is_file()) or (not value_file.is_file()):
                print(
                    f"Chart.yaml or values.yaml file is missing in {svc_path}, skipping..."
                )
                continue

            chart_content = chart_file.read_text(encoding="utf8")
            yaml = YAML()
            chart_data = yaml.load(chart_content)

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
                value_file.name
                for value_file in svc_path.iterdir()
                if value_file.name.startswith("values-dev-")
                or value_file.name.startswith("values-prod-")
            ]

            for instance_file in instance_files:
                merged_values = merge_yaml_files(svc_path, instance_file)
                try:
                    validate(instance=merged_values, schema=schema_data)
                    delete_error_files(svc_path)
                except Exception as err:
                    print(f"Validation error for {instance_file}: {err}")
                    output_file = svc_path / f"error-merged-{instance_file}"
                    with output_file.open("w", encoding="utf8") as out:
                        out.write(
                            f"# yaml-language-server: $schema={SCHEMA_BASE_URL}/v${chart_version}/schema-platform-managed-chart-strict.json\n"
                        )
                        yaml = YAML()
                        yaml.dump(merged_values, out)
                    sys.exit(err)


if __name__ == "__main__":
    main()
