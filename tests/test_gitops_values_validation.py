from typing import Callable

from kp_pre_commit_hooks.gitops_values_validation import \
    ServiceInstanceConfigValidator


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
