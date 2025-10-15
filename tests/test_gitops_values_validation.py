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

    # THEN - Should use the dev-specific version from Chart-dev.yaml (same as base for now)
    assert chart_version_dev == "0.1.157-pr195", f"Expected dev chart version '0.1.157-pr195', got '{chart_version_dev}'"

    # GIVEN - A prod environment configuration
    validator_prod = create_validator_for_test_file("app1/service1/values-prod-topic_with_authorized_max_local_topic_bytes_not_on_current_env.yaml")

    # WHEN - We check the chart version used for validation
    chart_version_prod = validator_prod.service_instance_config.helm_chart.platform_managed_chart_version

    # THEN - Should use the base version from Chart.yaml (no Chart-prod.yaml exists)
    assert chart_version_prod == "0.1.157-pr195", f"Expected prod chart version '0.1.157-pr195', got '{chart_version_prod}'"
