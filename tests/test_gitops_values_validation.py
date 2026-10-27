from typing import Callable

from kp_pre_commit_hooks.gitops_values_validation import (
    ServiceInstanceConfigValidator,
    HelmChart,
)
from pathlib import Path


def test_topic_with_unauthorized_max_local_topic_bytes(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-dev-topic_with_unauthorized_max_local_topic_bytes.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 1, "Expected exactly one validation error"
    assert "maxLocalTopicBytes can only be used with allowed topics" in errors[0].message

def test_topic_with_no_max_local_topic_bytes_set(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-dev-topic_with_no_max_local_topic_bytes_set.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 0, "Expected no validation errors"

def test_topic_with_authorized_max_local_topic_bytes(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-dev-topic_with_authorized_max_local_topic_bytes.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    # Expect no errors related to maxLocalTopicBytes for the whitelisted topic
    assert len(errors) == 0, "Expected no validation errors"


def test_topic_with_max_local_topic_bytes_above_authorized_value(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-dev-topic_with_max_local_topic_bytes_above_authorized_value.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 1, f"Expected exactly one validation error"
    assert "maxLocalTopicBytes exceeds the allowed maximum of" in errors[0].message

def test_topic_with_authorized_max_local_topic_bytes_not_on_current_env(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-prod-topic_with_authorized_max_local_topic_bytes_not_on_current_env.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 1, "Expected exactly one validation error"
    assert "maxLocalTopicBytes can only be used with allowed topics" in errors[0].message


def test_env_specific_chart_version_is_used_for_validation(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN - A dev environment configuration
    validator_dev = create_validator_for_test_file("app1/service1/values-dev-topic_with_no_max_local_topic_bytes_set.yaml")

    # WHEN - We check the chart version used for validation
    chart_version_dev = validator_dev.service_instance_config.helm_chart.platform_managed_chart_version

    # THEN - Should use the dev-specific version from Chart-dev.yaml
    assert chart_version_dev == "0.1.225", f"Expected dev chart version '0.1.225', got '{chart_version_dev}'"

    # GIVEN - A prod environment configuration
    validator_prod = create_validator_for_test_file("app1/service1/values-prod-topic_with_authorized_max_local_topic_bytes_not_on_current_env.yaml")

    # WHEN - We check the chart version used for validation
    chart_version_prod = validator_prod.service_instance_config.helm_chart.platform_managed_chart_version

    # THEN - Should use the base version from Chart.yaml (no Chart-prod.yaml exists)
    assert chart_version_prod == "0.1.224", f"Expected prod chart version '0.1.224', got '{chart_version_prod}'"


def test_kafka_streams_changelog_topic_is_accepted(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service3/values-dev-changelog.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 0, f"Kafka Streams changelog topics should be accepted, got: {errors}"


def test_kafka_streams_repartition_topic_is_accepted(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service3/values-dev-repartition.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 0, f"Kafka Streams repartition topics should be accepted, got: {errors}"


def test_kafka_streams_internal_topic_with_wrong_prefix_is_rejected(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service3/values-dev-wrong-prefix.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert any("must start with 'service3-wrong-prefix-'" in e.message for e in errors), (
        f"Expected internal topic prefix error, got: {errors}"
    )


def test_topic_with_wrong_service_name_is_rejected(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service2/values-dev-topic_with_wrong_service_name.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert any("it not compliant" in e.message for e in errors), f"Expected topic name compliance error, got: {errors}"


def test_kafka_streams_internal_topic_from_foreign_service_is_rejected(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service3/values-dev-foreign-service.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert any("must start with 'service3-foreign-service-'" in e.message for e in errors), (
        f"Expected internal topic prefix error for foreign service topic, got: {errors}"
    )


def test_versioned_topic_with_v_prefix_is_accepted(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-dev-versioned-topic.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 0, f"Topic with -vN version suffix should be accepted, got: {errors}"


def test_topic_with_hyphenated_suffix_is_accepted(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN
    validator = create_validator_for_test_file("app1/service1/values-dev-hyphenated-suffix.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 0, f"Topic with hyphenated suffix should be accepted, got: {errors}"


def test_a_secret_named_by_its_full_self_service_path_is_accepted(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN a chart whose published schema only allows k8s/ paths in secretsManagerPath
    validator = create_validator_for_test_file("app1/service1/values-dev-selfservice-secret-path.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert errors == [], f"Expected no validation errors, got {[e.message for e in errors]}"


def test_a_malformed_self_service_path_is_still_refused(
    create_validator_for_test_file: Callable[[str], ServiceInstanceConfigValidator],
) -> None:
    # GIVEN an unknown environment and a missing level
    validator = create_validator_for_test_file("app1/service1/values-dev-malformed-selfservice-secret-path.yaml")

    # WHEN
    errors = validator.validate_configuration()

    # THEN
    assert len(errors) == 1 and "does not match" in errors[0].message


def test_only_legacy_secret_path_patterns_are_widened() -> None:
    from kp_pre_commit_hooks.gitops_values_validation import accept_selfservice_secret_paths
    import re

    schema = {
        "properties": {
            "secretsManagerPath": {"type": "string", "pattern": "^k8s/(dev|prod)/(common|main)/"},
            "okta": {"properties": {"secretsManagerPath": {"pattern": "^selfservice/k8s/(dev|prod)/"}}},
        }
    }
    widened = accept_selfservice_secret_paths(schema)["properties"]
    pattern = widened["secretsManagerPath"]["pattern"]

    assert re.match(pattern, "k8s/dev/common/my-app/db")
    assert re.match(pattern, "selfservice/k8s/dev/my-app/my-svc/env")
    assert re.match(pattern, "selfservice/k8s/prod/my-app/_shared/db-credentials")
    assert not re.match(pattern, "selfservice/k8s/dev/my-app/env")
    assert not re.match(pattern, "selfservice/k8s/dev/my-app/my-svc/env/extra")
    assert not re.match(pattern, "other/k8s/dev/common/x")
    assert widened["okta"]["properties"]["secretsManagerPath"]["pattern"] == "^selfservice/k8s/(dev|prod)/"
