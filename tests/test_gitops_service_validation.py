from typing import Callable

from kp_pre_commit_hooks.gitops_values_validation import \
    GitOpsRepository, ServiceInstanceConfig

def test_unique_service_names_validation_with_existing_data() -> None:
    # GIVEN
    from pathlib import Path
    test_data_path = Path(__file__).parent / "test_data" / "gitops_data"
    repo = GitOpsRepository(test_data_path)

    def test_iter():
        for instance_values_file in test_data_path.glob("*/*/values-*-*.yaml"):
            application_name = instance_values_file.parent.parent.name
            service_name = instance_values_file.parent.name
            _, env, instance = instance_values_file.stem.split("-", maxsplit=2)
            yield ServiceInstanceConfig(application_name, service_name, env, instance, instance_values_file.parent, repo)

    repo.iter_service_instances_config = test_iter

    # WHEN
    errors = repo.validate_unique_service_names()

    # THEN
    assert len(errors) == 0, "Expected no validation errors for unique service names"

def test_duplicate_service_names_detection() -> None:
    # GIVEN
    from pathlib import Path
    test_data_path = Path(__file__).parent / "test_data" / "gitops_data"
    repo = GitOpsRepository(test_data_path)

    # Mock the iter method to simulate duplicate service names
    def mock_iter():
        # Simulate service1 in both app1 and app2
        yield ServiceInstanceConfig("app1", "service1", "dev", "instance1", test_data_path / "app1" / "service1", repo)
        yield ServiceInstanceConfig("app2", "service1", "dev", "instance1", test_data_path / "app2" / "service1", repo)
        yield ServiceInstanceConfig("app1", "unique-service", "dev", "instance1", test_data_path / "app1" / "unique-service", repo)

    repo.iter_service_instances_config = mock_iter

    # WHEN
    errors = repo.validate_unique_service_names()

    # THEN
    assert len(errors) == 1, "Expected exactly one validation error for duplicate service names"
    error = errors[0]
    assert "service1" in error.message
    assert "app1, app2" in error.message
    assert "Service names must be unique across all applications" in error.message
