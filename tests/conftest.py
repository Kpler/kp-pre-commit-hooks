import json
from pathlib import Path
from typing import Callable

import pytest

from kp_pre_commit_hooks import gitops_values_validation
from kp_pre_commit_hooks.gitops_values_validation import (
    GitOpsRepository, ServiceInstanceConfig, ServiceInstanceConfigValidator)

TEST_DATA_PATH = Path(__file__).parent / "test_data"
GITOPS_TEST_DATA_PATH = TEST_DATA_PATH / "gitops_data"
TEST_SCHEMA = json.loads((TEST_DATA_PATH / "schema-platform-managed-chart-strict.json").read_text())


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real-schema",
        action="store_true",
        help="download the real platform-managed-chart schemas (requires the Twingate VPN) instead of the minimal test one",
    )


@pytest.fixture(autouse=True)
def test_schema(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uses a minimal schema instead of downloading the real ones, which requires the Twingate VPN."""
    if not request.config.getoption("--real-schema"):
        monkeypatch.setattr(gitops_values_validation, "download_json_schema", lambda url: TEST_SCHEMA)


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