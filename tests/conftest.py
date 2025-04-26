from pathlib import Path
from typing import Callable

import pytest

from kp_pre_commit_hooks.gitops_values_validation import (
    GitOpsRepository, ServiceInstanceConfig, ServiceInstanceConfigValidator)

GITOPS_TEST_DATA_PATH = Path(__file__).parent / "test_data" / "gitops_data"


@pytest.fixture
def create_validator_for_test_file(
) -> Callable[[str], ServiceInstanceConfigValidator]:
    """Creates a validator for the given test data values file path."""

    def _create_validator(relative_values_path_str: str) -> ServiceInstanceConfigValidator:
        repo = GitOpsRepository(GITOPS_TEST_DATA_PATH)
        relative_values_path = Path(relative_values_path_str)

        service_dir_relative = relative_values_path.parent
        service_path_absolute = repo.gitops_path / service_dir_relative

        application_name, service_name = service_dir_relative.parts[:2]
        env, instance = relative_values_path.name.removesuffix(".yaml").split("-", maxsplit=2)[1:]

        config = ServiceInstanceConfig(
            application_name=application_name,
            service_name=service_name,
            env=env,
            instance=instance,
            path=service_path_absolute,
            gitops_repository=repo,
        )

        return ServiceInstanceConfigValidator(config)

    return _create_validator