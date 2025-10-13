import re
import sys
import textwrap
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path
from typing import Iterator, Literal, Mapping, Optional, Sequence, Union, cast
import warnings

import requests
import semver
import urllib3
import yaml
from jsonschema import Draft7Validator, ValidationError, validators
from jsonschema.protocols import Validator
from jsonschema_specifications import REGISTRY
from referencing import Registry, Resource
from termcolor import colored

# Disable insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# We subclass the validator to be able to intercept descend() call and track the current path
# jsonschema doesn't like that, but until they implement it, we need to suppress the warning
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*Subclassing validator classes is not intended.*"
)

###############################################################################
# Constants and Configuration
###############################################################################

SCHEMA_BASE_URL = "https://kp-helmchart-stable-shared-main.s3.eu-west-1.amazonaws.com/schema/platform-managed-chart"
GITOPS_DIR = Path("gitops")

SCHEMA_HEADER_REGEXP = re.compile(
    rf"^ *# yaml-language-server: \$schema={SCHEMA_BASE_URL}/v(?P<version>[^/]+)/schema-platform-managed-chart.json",
    re.MULTILINE
)

# Validate topic names follow pattern: (private.)?serviceName.topic(-version)?(.suffix)?
TOPIC_NAME_REGEXP = re.compile(
    r"^(private\.)?(?P<serviceName>[a-z][a-z0-9-]*)\.[a-z][a-z0-9-]*(-[0-9]+)?(\.[a-z0-9]+)?$"
)

TWINGATE_DOC_URL = "https://kpler.atlassian.net/wiki/spaces/KSD/pages/243562083/Install+and+configure+the+Twingate+VPN+client"

# Environment variables that should not be overridden
FORBIDDEN_ENVIRONMENT_VARIABLES = {
    "KAFKA_APPLICATION_ID": """KAFKA_APPLICATION_ID is automatically set in your container and should not be overridden.
More info at https://kpler.atlassian.net/l/cp/jb4uJQs3#Use-connection-information-in-environment-variables""",
    "KAFKA_BOOTSTRAP_SERVERS": """KAFKA_BOOTSTRAP_SERVERS is automatically set in your container and should not be overridden.
More info at https://kpler.atlassian.net/l/cp/jb4uJQs3#Use-connection-information-in-environment-variables""",
    "SCHEMA_REGISTRY_URL": """SCHEMA_REGISTRY_URL is automatically set in your container and should not be overridden.
More info at https://kpler.atlassian.net/l/cp/jb4uJQs3#Use-connection-information-in-environment-variables""",
}

# Topics with special max local bytes limits
ALLOWED_MAX_LOCAL_TOPIC_BYTES_BY_TOPIC_AND_ENV = {
    "ais-listener.nmea": {
        "prod": {
            "max_limit": 697_932_185_600,  # 650GB
        }
    },
    "ais-listener.error.station": {
        "prod": {
            "max_limit": 536_870_912_000,  # 500GB
        }
    }
}

###############################################################################
# Generic Helper functions and classes
###############################################################################

Color = Literal["black", "grey", "red", "green", "yellow", "blue", "magenta", "cyan"]
Attribute = Literal["bold", "dark", "underline", "blink", "reverse", "concealed"]

def colorize(text: str, color: Color | None = None, bold: bool = False) -> str:
    """Apply color and formatting to text"""
    attrs: list[Attribute] = ["bold"] if bold else []
    return colored(text, color, attrs=attrs)

def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case"""
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()

def deep_merge(*sources: dict) -> dict:
    """Recursively merge dictionaries"""
    result = {}
    for dictionary in sources:
        for key, value in dictionary.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = deep_merge(result[key], value)
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
def download_json_schema(url: str) -> dict:
    """Download and cache JSON schema from URL"""
    response = requests.get(url, timeout=10, verify=True)
    if response.status_code == 403:
        raise UnauthorizedToDownloadSchema(url)
    if response.status_code == 404:
        raise MissingSchema(url)
    response.raise_for_status()
    return response.json()

# Registry for resolving schema references
SCHEMA_REGISTRY = REGISTRY.combine(
    Registry(retrieve=lambda uri: Resource.from_contents(download_json_schema(uri)))
)

###############################################################################
# Core Classes
###############################################################################

@dataclass
class HelmChart:
    name: str
    version: str
    dependencies: list["HelmChart"] = field(default_factory=list)

    def get_dependency(self, dependency_name: str) -> Optional["HelmChart"]:
        """Get dependency chart by name"""
        return next((d for d in self.dependencies if d.name == dependency_name), None)

    @cached_property
    def json_schema(self) -> dict:
        """Get JSON schema for chart version"""
        if self.platform_managed_chart_version and semver.VersionInfo.parse(self.platform_managed_chart_version).compare("0.1.35") >= 0:
            schema_url = f"{SCHEMA_BASE_URL}/v{self.platform_managed_chart_version}/schema-platform-managed-chart-strict.json"
            return download_json_schema(schema_url)
        return {}

    @cached_property
    def platform_managed_chart_version(self) -> Optional[str]:
        """Get platform managed chart version"""
        platform_managed_chart = self.get_dependency("platform-managed-chart")
        return platform_managed_chart.version if platform_managed_chart else None

    @staticmethod
    def from_chart_file(chart_file: Path, env: Optional[str] = None):
        """Create HelmChart from Chart.yaml and optional Chart-{env}.yaml"""
        chart_files = [chart_file]

        if env:
            env_specific_chart = chart_file.parent / f"Chart-{env}.yaml"
            if env_specific_chart.exists():
                chart_files.append(env_specific_chart)

        charts_data = [yaml.safe_load(f.read_text()) for f in chart_files]
        merged = deep_merge(*charts_data)

        return HelmChart(
            name=merged["name"],
            version=merged["version"],
            dependencies=[HelmChart(dep["name"], dep["version"]) for dep in merged.get("dependencies", [])],
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

    def __str__(self) -> str:
        return str(self.path.name)

    @cached_property
    def values(self) -> dict:
        """Load YAML values"""
        return yaml.safe_load(self.path.read_text()) or {}

    @cached_property
    def header_schema_version(self) -> Optional[str]:
        """Get schema version from file header"""
        match = SCHEMA_HEADER_REGEXP.search(self.path.read_text())
        return match.group("version") if match else None

    def set_header_schema_version(self, version: str) -> None:
        """Update schema version in file header"""
        if self.header_schema_version == version:
            return
        header = f"# yaml-language-server: $schema={SCHEMA_BASE_URL}/v{version}/schema-platform-managed-chart.json"
        content = self.path.read_text()
        if self.header_schema_version is None:
            self.path.write_text(header + "\n" + content)
        else:
            self.path.write_text(SCHEMA_HEADER_REGEXP.sub(header, content))

    @staticmethod
    def merge_values(values_files: list["ValuesFile"]) -> dict:
        """Merge multiple values files"""
        return deep_merge(*[v.values for v in values_files])

@dataclass
class ServiceInstanceConfig:
    application_name: str
    service_name: str
    env: str
    instance: str
    path: Path
    gitops_repository: GitOpsRepository

    @property
    def service_group(self) -> str:
        return self.service_name

    def __str__(self) -> str:
        return f"{self.application_name}/{self.service_name} {self.instance} instance {self.env} configuration"

    @property
    def rel_path(self) -> Path:
        """Get path relative to gitops root"""
        return self.path.relative_to(self.gitops_repository.gitops_path)

    @property
    def configuration(self) -> dict:
        """Get merged configuration"""
        return ValuesFile.merge_values(self.values_files)

    @property
    def values_files(self) -> list[ValuesFile]:
        """Get list of values files"""
        candidate_files = [
            "values.yaml",
            f"values-{self.env}.yaml",
            f"values-{self.env}-{self.instance}.yaml"
        ]
        return [
            ValuesFile(self.path.joinpath(file))
            for file in candidate_files
            if self.path.joinpath(file).exists()
        ]

    @property
    def helm_chart(self) -> HelmChart:
        """Get HelmChart from Chart.yaml and optional Chart-{env}.yaml"""
        return HelmChart.from_chart_file(self.path / "Chart.yaml", env=self.env)

    def sync_values_files_schema_header_version(self) -> None:
        """Sync schema version in all values files"""
        if self.helm_chart.platform_managed_chart_version is None:
            return
        for value_file in self.values_files:
            value_file.set_header_schema_version(self.helm_chart.platform_managed_chart_version)


class ServiceInstanceConfigValidator:

    IGNORED_VALIDATION_ERRORS = {
        # These below project have service names are longer than the maximum allowed (36 characters)
        # or have application name not prefixed with the service name
        # but we ignore these errors as these services were created before the rule was in place
        "flows-staticdata-consumer": {
            "$.platform-managed-chart.serviceName": [
                "'flows-staticdata-consumer-commodities' does not match the service folder name 'flows-staticdata-consumer'",
                "'flows-staticdata-consumer-coal' does not match the service folder name 'flows-staticdata-consumer'",
                "'flows-staticdata-consumer-lpg' does not match the service folder name 'flows-staticdata-consumer'",
                "'flows-staticdata-consumer-lng' does not match the service folder name 'flows-staticdata-consumer'",
                "'flows-staticdata-consumer-commodities' is too long, the maximum length is 36",
            ]
        },
        "stream-merge-and-apply-matches-import-bol": {
            "$.platform-managed-chart.serviceName": [
                "'stream-merge-and-apply-matches-import-bol' is too long, the maximum length is 36"
            ]
        },
        "stream-merge-and-apply-matches-export-bol": {
            "$.platform-managed-chart.serviceName": [
                "'stream-merge-and-apply-matches-export-bol' is too long, the maximum length is 36"
            ]
        },
        "earth-observation-product-catalog-api": {
            "$.platform-managed-chart.serviceName": [
                "'earth-observation-product-catalog-api' is too long, the maximum length is 36"
            ]
        },
        "apply-edits-exportbol-jdbc": {
            "$.platform-managed-chart.serviceName": ["'sink' does not match the service folder name 'apply-edits-exportbol-jdbc'"]
        },
        "apply-edits-importbol-jdbc": {
            "$.platform-managed-chart.serviceName": ["'sink' does not match the service folder name 'apply-edits-exportbol-jdbc'"]
        },
        "maritime-news-strapi-api": {"$": ["Additional properties are not allowed ('extra' was unexpected)"]},
        # These below projects use images from legacy MT Docker repository that doesn't follow kpler conventions
        "cnt-data-pipelines-static-data": {
            "$.platform-managed-chart.image.repository": ["'cnt2_data_pipelines_static_data' does not match '^(dev|stable)/'"]
        },
        "trips-central": {"$.platform-managed-chart.image.repository": ["'trips-central' does not match '^(dev|stable)/'"]},
        "product-usage-metrics": {
            "$.platform-managed-chart.image.repository": ["'product_usage_metrics' does not match '^(dev|stable)/'"]
        },
        "fleet-manager": {
            "$.platform-managed-chart.image.repository": ["'intransit-fleet-manager' does not match '^(dev|stable)/'"]
        },
        "underway-v2": {"$.platform-managed-chart.image.repository": ["'underway' does not match '^(dev|stable)/'"]},
        "eta-picker": {
            "$.platform-managed-chart.image.repository": [
                "'eta_picker' does not match '^(dev|stable)/'",
                "'eta-picker-stage' does not match '^(dev|stable)/'",
            ],
            "$.platform-managed-chart.api.secrets": [
                "'cnt-analytics-prod-dbInstanceIdentifier', 'cnt-analytics-prod-engine', 'cnt-analytics-prod-host', 'cnt-analytics-prod-password', 'cnt-analytics-prod-port', 'cnt-analytics-prod-username' do not match any of the regexes: '^[a-zA-Z0-9_]+$'",
                "'cnt-analytics-dev-dbInstanceIdentifier', 'cnt-analytics-dev-engine', 'cnt-analytics-dev-host', 'cnt-analytics-dev-password', 'cnt-analytics-dev-port', 'cnt-analytics-dev-username' do not match any of the regexes: '^[a-zA-Z0-9_]+$'",
            ],
        },
        "api-consumer": {"$.platform-managed-chart.image.repository": ["'apiconsumer' does not match '^(dev|stable)/'"]},
        "waiting-production": {
            "$.platform-managed-chart.image.repository": ["'waiting-production' does not match '^(dev|stable)/'"]
        },
        "waiting-mt-data": {"$.platform-managed-chart.image.repository": ["'waiting-mt-data' does not match '^(dev|stable)/'"]},
        "cnt-db-migrations": {
            "$.platform-managed-chart.image.repository": ["'cnt_db_migrations' does not match '^(dev|stable)/'"]
        },
        "l2-data-models": {"$.platform-managed-chart.image.repository": ["'l2_data_models' does not match '^(dev|stable)/'"]},
        "graph-data-model": {"$.platform-managed-chart.image.repository": ["'graph_data_model' does not match '^(dev|stable)/'"]},
        "scac-gpt": {"$.platform-managed-chart.image.repository": ["'scac_gpt' does not match '^(dev|stable)/'"]},
        "cnt-data-pipelines-dynamic-data": {
            "$.platform-managed-chart.image.repository": ["'cnt2_data_pipelines_dynamic_data' does not match '^(dev|stable)/'"]
        },
        "cnt-fetch-calls-api": {"$.platform-managed-chart.image.repository": ["'fetchcallsapi' does not match '^(dev|stable)/'"]},
        "waiting-training": {"$.platform-managed-chart.image.repository": ["'waiting_training' does not match '^(dev|stable)/'"]},
        "linescape-schedules": {
            "$.platform-managed-chart.image.repository": ["'linescape_schedules' does not match '^(dev|stable)/'"]
        },
        "eta-batch-snap": {"$.platform-managed-chart.image.repository": ["'etabatchsnap' does not match '^(dev|stable)/'"]},
        "north-star": {"$.platform-managed-chart.image.repository": ["'north_star_metrics' does not match '^(dev|stable)/'"]},
        "cnt-tnt-data-cleaning": {
            "$.platform-managed-chart.image.repository": ["'tntdatacleaning' does not match '^(dev|stable)/'"]
        },
        "demo-shipments": {"$.platform-managed-chart.image.repository": ["'demo_shipments' does not match '^(dev|stable)/'"]},
        "next-port-prediction": {
            "$.platform-managed-chart.image.repository": ["'next_port_prediction' does not match '^(dev|stable)/'"]
        },
        "waiting-statistics": {
            "$.platform-managed-chart.image.repository": ["'waiting_statistics' does not match '^(dev|stable)/'"]
        },
        "route-finder-api": {
            "$.platform-managed-chart.api.startupProbe.initialDelaySeconds": ["2400 is greater than the maximum of 300"]
        },
        "mt-tropical-storm-service": {
            "$.platform-managed-chart.api.ingress": ["Additional properties are not allowed ('enable_ssl_redirect' was unexpected)"]
        },
        "mcp-test": {
            "$.platform-managed-chart.api.deployment": [
                "Additional properties are not allowed ('nodeSelector', 'tolerations' were unexpected)"
            ]
        },
        "platform-webhooks": {
            "$.platform-managed-chart.api.deployment": [
                "Additional properties are not allowed ('tolerations' was unexpected)"
            ]
        }
    }

    def __init__(self, service_instance_config: ServiceInstanceConfig):
        self.service_instance_config = service_instance_config
        self._current_path = []

    @cached_property
    def validator(self) -> Validator:
        """Create JSON schema validator"""

        base_validator_class = validators.extend(
            Draft7Validator,
            validators={"additionalChecks": self.validate_additional_checks}
        )

        # We wrap the validator to intercept descend() and track the current path
        # as this information is not provided by json schema otherwise
        outer_self = self
        class PathTrackingValidator(base_validator_class):
            def descend(self, instance, schema, path=None, schema_path=None, resolver=None):
                outer_self._current_path.append(path)
                try:
                    yield from super().descend(instance, schema, path, schema_path, resolver)
                finally:
                    outer_self._current_path.pop()

        validator_class = validators.validates("draft7")(PathTrackingValidator)
        return validator_class(
            self.service_instance_config.helm_chart.json_schema,
            registry=SCHEMA_REGISTRY
        )

    def validate_configuration(self) -> Sequence[Union[ValidationError, SchemaValidationError]]:
        """Validate service configuration"""
        try:
            raw_validation_errors = [
                self.enrich_error_message(error)
                for error in self.validator.iter_errors(self.service_instance_config.configuration)
            ]
            validation_errors = [error for error in raw_validation_errors if not self.is_ignored_error(error)]
            schema_validation_errors = list(self.iter_schema_validation_errors())
            return validation_errors + schema_validation_errors

        except MissingSchema as error:
            version = self.service_instance_config.helm_chart.platform_managed_chart_version
            return [
                SchemaValidationError(
                    f"Missing JSON schema for platform managed chart version {version} in Chart.yaml",
                    location=error.schema_url,
                )
            ]

    def iter_schema_validation_errors(self) -> Iterator[SchemaValidationError]:
        """Check schema version consistency"""
        version = self.service_instance_config.helm_chart.platform_managed_chart_version
        for values_file in self.service_instance_config.values_files:
            if values_file.header_schema_version != version:
                yield SchemaValidationError(
                    f"JSON schema version in header ({values_file.header_schema_version}) does not match version in Chart.yaml ({version})",
                    location=f"values file {values_file}",
                    hint="This pre-commit hook will auto-fix this issue. Please commit the values files changes.",
                )

    def enrich_error_message(self, error: ValidationError) -> ValidationError:
        if error.message.endswith("is too long") and isinstance(error.schema, Mapping) and error.schema.get("maxLength"):
            error.message += f', the maximum length is {error.schema["maxLength"]}'
        return error

    def is_ignored_error(self, error: ValidationError) -> bool:
        ignored_errors_for_service = self.IGNORED_VALIDATION_ERRORS.get(self.service_instance_config.service_name, {})
        return error.message in ignored_errors_for_service.get(error.json_path, [])

    def validate_additional_checks(self, validator, additional_checks, value, schema):
        for check in additional_checks:
            if check_method := getattr(self, f"validate_{camel_to_snake(check)}", None):
                yield from check_method(value, schema)

    def validate_service_name_matches_service_folder(self, value, schema):
        folder_name = self.service_instance_config.path.name
        if folder_name != value and not value.startswith(f"{folder_name}-"):
            yield ValidationError(
                f"'{value}' does not match the service folder name '{folder_name}'"
                f" Must be either '{folder_name}' or '{folder_name}-<suffix>'"
            )

    def validate_service_keys_match_service_folder(self, value, schema):
        if not isinstance(value, dict):
            return

        folder_name = self.service_instance_config.path.name
        for service_key in value:
            if folder_name != service_key and not service_key.startswith(f"{folder_name}-"):
                yield ValidationError(
                    f"'{service_key}' does not match the service folder name '{folder_name}'"
                    f" Must be either '{folder_name}' or '{folder_name}-<suffix>'"
                )

    def validate_topic_name_compliance(self, value, schema):
        service_name = self._get_current_service_name()
        match = TOPIC_NAME_REGEXP.match(str(value))
        if match and match["serviceName"] not in (service_name, self.service_instance_config.service_group):
            yield ValidationError(f"topicName '{value}' it not compliant, it should contain the service name '{service_name}'")

    def validate_max_local_topic_bytes_compliance(self, value, schema):

        topic_max_local_bytes = value.get("maxLocalTopicBytes")
        if topic_max_local_bytes is None:
            return

        topic_name = value.get("topicName")
        topic_env = self.service_instance_config.env

        max_allowed_values = ALLOWED_MAX_LOCAL_TOPIC_BYTES_BY_TOPIC_AND_ENV.get(topic_name, {}).get(topic_env, {}).get("max_limit")
        if not max_allowed_values:
            yield ValidationError(
                "maxLocalTopicBytes can only be used with allowed topics"
                f" and topic '{topic_name}' is not allowed for environment '{topic_env}'."
                " See https://kpler.atlassian.net/wiki/x/BgGKS for more information."
            )
        elif topic_max_local_bytes > max_allowed_values:
            yield ValidationError(
                f"maxLocalTopicBytes exceeds the allowed maximum of {max_allowed_values} "
                f"for topic '{topic_name}' in environment '{topic_env}'.\n"
                " See https://kpler.atlassian.net/wiki/x/BgGKS for more information."
            )


    def validate_forbidden_environment_variables(self, value, schema):
        if not isinstance(value, dict):
            return
        for env_variable, forbidden_reason in FORBIDDEN_ENVIRONMENT_VARIABLES.items():
            if env_variable in value:
                yield ValidationError(
                    f"Environment variable `{env_variable}` is not allowed to be manually set",
                    schema={"description": f"Remove `{env_variable}` from your environment variables.\n{forbidden_reason}"},
                )

    def _get_current_path(self) -> list[str]:
        return [part for part in self._current_path if part is not None]

    def _get_current_service_name(self) -> str:
        current_path = self._get_current_path()
        if len(current_path) > 2 and current_path[:2] == ["platform-managed-chart", "services"]:
            return current_path[2]

        service_configuration = self.service_instance_config.configuration
        if service_name := service_configuration.get("platform-managed-chart", {}).get("serviceName"):
            return service_name

        return self.service_instance_config.service_group

def format_error(error: Union[ValidationError, SchemaValidationError]) -> str:
    """Format validation error message"""
    if isinstance(error, SchemaValidationError):
        error_message = f"{colorize('ERROR:', 'red')} {error.message}\n   at: {colorize(error.location, bold=True)}"
        if error.hint:
            error_message += f"\n\n {colorize('Hint:', bold=True)} {error.hint}\n"
    else:
        location = "/".join(map(str, error.absolute_path))
        error_message = f"{colorize('ERROR:', 'red')} {error.message}\n   at: {colorize(location, bold=True)}"

        if isinstance(error.schema, Mapping) and "description" in error.schema:
            title, _, description = error.schema["description"].partition("\n")
            error_message += f"\n\n {colorize('Hint:', bold=True)} {title}\n\n"
            if description:
                error_message += textwrap.indent(description, prefix=" " * 7)

    return error_message

def display_errors(
    service_instance_config: ServiceInstanceConfig,
    errors: Sequence[Union[ValidationError, SchemaValidationError]]
) -> None:
    """Display validation errors"""
    values_files = ", ".join(str(v) for v in service_instance_config.values_files)
    print(
        f"\nThe following error(s) were found in the files {values_files}\n"
        f"under {service_instance_config.rel_path}:\n"
    )
    for error in errors:
        print(textwrap.indent(format_error(error), prefix=" " * 2) + "\n")


###############################################################################
# Main Entry Point
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
                print(colorize("PASSED", "green"))
            else:
                errors_found = True
                print(colorize("FAILED", "red"))
                display_errors(service_instance_config, errors)
                # We always try to sync the schema header version, in case it was one of the error detected
                service_instance_config.sync_values_files_schema_header_version()

        sys.exit(1 if errors_found else 0)

    except UnauthorizedToDownloadSchema as error:
        print(
            f"\n\n{colorize('FATAL:', 'red')} Unauthorized to download schema at {error.schema_url}\n"
            "       Please check that your Twingate VPN Client is up and running configured.\n"
            f"       More info at {TWINGATE_DOC_URL}\n\n"
        )
        sys.exit(1)
