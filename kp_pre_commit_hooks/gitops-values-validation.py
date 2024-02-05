import re
import sys
import textwrap
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path
from typing import Iterator, Optional, Sequence, Union, cast

import requests
import semver
import urllib3
import yaml
from jsonschema import Draft7Validator, ValidationError, validators
from jsonschema.protocols import Validator
from jsonschema_specifications import REGISTRY
from referencing import Registry, Resource
from termcolor import colored

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

###############################################################################
# Main code
###############################################################################

SCHEMA_BASE_URL = "https://kp-helmchart-stable-shared-main.s3.eu-west-1.amazonaws.com/schema/platform-managed-chart"
GITOPS_DIR = Path("gitops")

SCHEMA_HEADER_REGEXP = re.compile(
    rf"^ *# yaml-language-server: \$schema={SCHEMA_BASE_URL}/v(?P<version>[^/]+)/schema-platform-managed-chart.json", re.MULTILINE
)
TOPIC_NAME_REGEXP = re.compile(r"^(private\.)?(?P<serviceName>[a-z][a-z0-9-]*)\.[a-z][a-z0-9]*(-[0-9]+)?(\.[a-z0-9]+)?$")

TWINGATE_DOC_URL = "https://kpler.atlassian.net/wiki/spaces/KSD/pages/243562083/Install+and+configure+the+Twingate+VPN+client"

###############################################################################
# Generic Helper functions and classes
###############################################################################

# Helper functions to colorize the output
red = lambda text: colored(text, "red")
green = lambda text: colored(text, "green")
bold = lambda text: colored(text, attrs=["bold"])


def camel_to_snake(name):
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def deep_merge(*sources) -> dict:
    result = {}
    for dictionary in sources:
        for key, value in dictionary.items():
            if isinstance(value, dict):
                result[key] = deep_merge(result.setdefault(key, {}), value)
            else:
                result[key] = value
    return result


###############################################################################
# Specific Helper functions and classes
###############################################################################


@dataclass
class UnauthorizedToDownloadSchema(Exception):
    schema_url: str


@dataclass
class MissingSchema(Exception):
    schema_url: str


@dataclass
class SchemaValidationError(Exception):
    message: str
    location: str
    hint: Optional[str] = None


@cache
def download_json_schema(url):
    response = requests.get(url, timeout=10, verify=False)
    if response.status_code == 403:
        raise UnauthorizedToDownloadSchema(url)
    if response.status_code == 404:
        raise MissingSchema(url)
    response.raise_for_status()
    return response.json()


# This is required so that jsonschema library can automatically download the schema references
SCHEMA_REGISTRY = REGISTRY.combine(Registry(retrieve=lambda uri: Resource.from_contents(download_json_schema(uri))))


@dataclass
class HelmChart:
    name: str
    version: str
    dependencies: list["HelmChart"] = field(default_factory=list)

    def get_dependency(self, dependency_name) -> Optional["HelmChart"]:
        return next((d for d in self.dependencies if d.name == dependency_name), None)

    @cached_property
    def json_schema(self) -> dict:
        if self.platform_managed_chart_version and semver.compare(self.platform_managed_chart_version, "0.1.35") >= 0:
            schema_url = f"{SCHEMA_BASE_URL}/v{self.platform_managed_chart_version}/schema-platform-managed-chart-strict.json"
            return download_json_schema(schema_url)
        else:
            return {}

    @cached_property
    def platform_managed_chart_version(self) -> Optional[str]:
        platform_managed_chart = self.get_dependency("platform-managed-chart")
        return platform_managed_chart.version if platform_managed_chart else None

    @staticmethod
    def from_chart_file(chart_file: Path):
        chart = cast(dict, yaml.safe_load(chart_file.read_text()))
        return HelmChart(
            name=chart["name"],
            version=chart["version"],
            dependencies=[HelmChart(dep["name"], dep["version"]) for dep in chart.get("dependencies", [])],
        )


class GitOpsRepository:
    def __init__(self, gitops_path: Path):
        self.gitops_path = gitops_path

    def iter_service_instances_config(self):
        for instance_values_file in self.gitops_path.glob("gitops/*/*/values-*-*.yaml"):
            application_name = instance_values_file.parent.parent.name
            service_name = instance_values_file.parent.name
            _, env, instance = instance_values_file.stem.split("-", maxsplit=2)
            yield ServiceInstanceConfig(application_name, service_name, env, instance, instance_values_file.parent, self)


@dataclass
class ValuesFile:
    path: Path

    def __str__(self):
        return str(self.path.name)

    @cached_property
    def values(self):
        return yaml.safe_load(self.path.read_text()) or {}

    @cached_property
    def header_schema_version(self) -> Optional[str]:
        match = SCHEMA_HEADER_REGEXP.search(self.path.read_text())
        return match.group("version") if match else None

    def set_header_schema_version(self, version):
        if self.header_schema_version == version:
            return
        header = f"# yaml-language-server: $schema={SCHEMA_BASE_URL}/v{version}/schema-platform-managed-chart.json\n"
        content = self.path.read_text()
        if self.header_schema_version is None:
            self.path.write_text(header + content)
        else:
            self.path.write_text(SCHEMA_HEADER_REGEXP.sub(header, content))

    @staticmethod
    def merge_values(values_files: list["ValuesFile"]) -> dict:
        return deep_merge(*[v.values for v in values_files])


@dataclass
class ServiceInstanceConfig:
    application_name: str
    service_name: str
    env: str
    instance: str
    path: Path
    gitops_repository: GitOpsRepository

    def __str__(self):
        return f"{self.application_name}/{self.service_name} {self.instance} instance {self.env} configuration"

    @property
    def rel_path(self) -> Path:
        return self.path.relative_to(self.gitops_repository.gitops_path)

    @property
    def configuration(self) -> dict:
        return ValuesFile.merge_values(self.values_files)

    @property
    def values_files(self) -> list[ValuesFile]:
        candidate_files = ["values.yaml", f"values-{self.env}.yaml", f"values-{self.env}-{self.instance}.yaml"]
        return [ValuesFile(self.path.joinpath(file)) for file in candidate_files if self.path.joinpath(file).exists()]

    @property
    def helm_chart(self) -> HelmChart:
        return HelmChart.from_chart_file(self.path / "Chart.yaml")

    def sync_values_files_schema_header_version(self):
        for value_file in self.values_files:
            value_file.set_header_schema_version(self.helm_chart.platform_managed_chart_version)


class ServiceInstanceConfigValidator:

    def __init__(self, service_instance_config: ServiceInstanceConfig):
        self.service_instance_config = service_instance_config

    @cached_property
    def validator(self) -> Validator:
        validator_class = validators.validates("draft7")(
            validators.extend(Draft7Validator, validators={"additionalChecks": self.validate_additional_checks})
        )
        return validator_class(self.service_instance_config.helm_chart.json_schema, registry=SCHEMA_REGISTRY)

    def validate_configuration(self) -> Sequence[Union[ValidationError, SchemaValidationError]]:
        try:
            validation_errors = list(self.validator.iter_errors((self.service_instance_config.configuration)))
            schema_validation_errors = list(self.iter_schema_validation_errors())
            return validation_errors + schema_validation_errors

        except MissingSchema as error:
            platform_managed_chart_version = self.service_instance_config.helm_chart.platform_managed_chart_version
            return [
                SchemaValidationError(
                    f"Missing JSON schema for platform managed chart version {platform_managed_chart_version} in Chart.yaml",
                    location=error.schema_url,
                )
            ]

    def iter_schema_validation_errors(self) -> Iterator[SchemaValidationError]:
        platform_managed_chart_version = self.service_instance_config.helm_chart.platform_managed_chart_version
        for values_file in self.service_instance_config.values_files:
            if values_file.header_schema_version != platform_managed_chart_version:
                yield SchemaValidationError(
                    f"JSON schema version in header ({values_file.header_schema_version}) does not match version in Chart.yaml ({platform_managed_chart_version})",
                    location=f"values file {values_file}",
                    hint="This pre-commit hook will auto-fix this issue. Please commit the values files changes.",
                )

    def validate_additional_checks(self, validator, additional_checks, value, schema):
        for check in additional_checks:
            if check_method := getattr(self, f"validate_{camel_to_snake(check)}", None):
                yield from check_method(value, schema)


def format_error(error: Union[ValidationError, SchemaValidationError]):
    if isinstance(error, SchemaValidationError):
        error_message = f"{red('ERROR:')} {error.message}\n   at: {bold(error.location)}"
        if error.hint:
            error_message += f"\n\n {bold('Hint:')} {error.hint}\n"

    else:
        location = "/".join(map(str, error.absolute_path))
        error_message = f"{red('ERROR:')} {error.message}\n   at: {bold(location)}"
        if description := error.schema and error.schema.get("description"):
            title, description = description.split("\n", maxsplit=1)
            error_message += f"\n\n {bold('Hint:')} {title}\n\n"
            error_message += textwrap.indent(description, prefix=" " * 7)

    return error_message


def display_errors(
    service_instance_config: ServiceInstanceConfig, errors: Sequence[Union[ValidationError, SchemaValidationError]]
):
    values_files = ", ".join([str(v) for v in service_instance_config.values_files])
    print(f"\nThe following error(s) were found in the files {values_files}\nunder {service_instance_config.rel_path}:\n")
    for error in errors:
        print(textwrap.indent(format_error(error), prefix=" " * 2) + "\n")


###############################################################################
# Main code
###############################################################################

if __name__ == "__main__":
    gitops_path = Path(sys.argv[1]) if len(sys.argv) >= 2 else Path.cwd()
    gitops_repository = GitOpsRepository(gitops_path)

    try:
        errors_found = False
        for service_instance_config in gitops_repository.iter_service_instances_config():
            print(f"Checking {service_instance_config} ", end="")

            validator = ServiceInstanceConfigValidator(service_instance_config)
            errors = validator.validate_configuration()
            if not errors:
                print(green("PASSED"))
            else:
                errors_found = True
                print(red("FAILED"))
                display_errors(service_instance_config, errors)
                # We always try to sync the schema header version, in case it was one of the error detected
                service_instance_config.sync_values_files_schema_header_version()

        sys.exit(1 if errors_found else 0)

    except UnauthorizedToDownloadSchema as error:
        print(
            f"\n\n{red('FATAL:')} Unauthorized to download schema at {error.schema_url}\n"
            "       Please check that your Twingate VPN Client is up and running configured.\n"
            f"       More info at {TWINGATE_DOC_URL}\n\n"
        )
        sys.exit(1)
