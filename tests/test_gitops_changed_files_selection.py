import subprocess
from pathlib import Path

import pytest

from kp_pre_commit_hooks import gitops_values_validation
from kp_pre_commit_hooks.gitops_values_validation import (
    GitOpsRepository, ServiceInstanceConfig, get_staged_deleted_files, main, parse_args)


@pytest.fixture
def gitops_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitOpsRepository:
    """Creates a gitops repository with two services, each with a dev and a prod instance,
    with pre-commit running from its root."""
    for service in ["service1", "service2"]:
        service_path = tmp_path / "gitops" / "app1" / service
        service_path.mkdir(parents=True)
        for file in ["Chart.yaml", "values.yaml", "values-dev.yaml", "values-dev-main.yaml", "values-prod-main.yaml"]:
            (service_path / file).touch()
    monkeypatch.chdir(tmp_path)
    return GitOpsRepository(tmp_path)


def affected_instances(gitops_repository: GitOpsRepository, *changed_files: Path) -> set[str]:
    return {
        f"{config.service_name}/{config.env}-{config.instance}"
        for config in gitops_repository.iter_service_instances_config_affected_by(changed_files)
    }


@pytest.mark.parametrize(
    "changed_file, expected_instances",
    [
        ("gitops/app1/service1/values-dev-main.yaml", {"service1/dev-main"}),
        ("gitops/app1/service1/values-dev.yaml", {"service1/dev-main"}),
        ("gitops/app1/service1/Chart-prod.yaml", {"service1/prod-main"}),
        ("gitops/app1/service1/values.yaml", {"service1/dev-main", "service1/prod-main"}),
        ("gitops/app1/service1/Chart.yaml", {"service1/dev-main", "service1/prod-main"}),
        ("gitops/app1/service1/README.md", set()),
        ("README.md", set()),
    ],
)
def test_only_instances_depending_on_changed_file_are_selected(
    gitops_repository: GitOpsRepository, changed_file: str, expected_instances: set[str]
) -> None:
    assert affected_instances(gitops_repository, gitops_repository.gitops_path / changed_file) == expected_instances


def test_relative_changed_file_paths_are_matched(gitops_repository: GitOpsRepository) -> None:
    # pre-commit passes paths relative to the repository root, its current directory
    assert affected_instances(gitops_repository, Path("gitops/app1/service2/values-prod-main.yaml")) == {
        "service2/prod-main"
    }


def test_parse_args_without_arguments_validates_whole_current_repository() -> None:
    assert parse_args([]) == (Path.cwd(), None)


def test_parse_args_with_a_directory_validates_whole_given_repository(tmp_path: Path) -> None:
    assert parse_args([str(tmp_path)]) == (tmp_path, None)


def test_parse_args_with_several_paths_without_changed_files_flag_fails() -> None:
    with pytest.raises(SystemExit):
        parse_args(["gitops/a/b/values.yaml", "gitops/a/b/Chart.yaml"])


def test_parse_args_with_changed_files_flag_returns_given_files() -> None:
    assert parse_args(["--changed-files", "gitops/app1/service1/values.yaml"]) == (
        Path.cwd(),
        [Path("gitops/app1/service1/values.yaml")],
    )


def test_parse_args_with_changed_files_flag_and_no_file_returns_no_changed_file() -> None:
    # pre-commit calls the hook without any file when always_run is set and no file matches
    assert parse_args(["--changed-files"]) == (Path.cwd(), [])


def git(repository_path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repository_path, check=True, capture_output=True)


@pytest.fixture
def committed_gitops_repository(gitops_repository: GitOpsRepository) -> GitOpsRepository:
    """The gitops repository fixture committed in git."""
    path = gitops_repository.gitops_path
    git(path, "init", "-q")
    git(path, "add", ".")
    git(path, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "init")
    return gitops_repository


def test_staged_deleted_files_affect_their_instances(committed_gitops_repository: GitOpsRepository) -> None:
    # GIVEN a commit only deleting an env values file, which pre-commit does not pass to hooks
    git(committed_gitops_repository.gitops_path, "rm", "-q", "gitops/app1/service2/values-dev.yaml")

    # WHEN
    deleted_files = get_staged_deleted_files(Path.cwd())

    # THEN
    assert deleted_files == [Path.cwd() / "gitops/app1/service2/values-dev.yaml"]
    assert affected_instances(committed_gitops_repository, *deleted_files) == {"service2/dev-main"}


def test_staged_moved_files_affect_the_instances_of_their_old_location(
    committed_gitops_repository: GitOpsRepository,
) -> None:
    # GIVEN an env values file moved out of its service, which pre-commit reports with its new path only
    git(committed_gitops_repository.gitops_path, "mv", "gitops/app1/service1/values-dev.yaml", "gitops/app1/")

    # THEN
    assert get_staged_deleted_files(Path.cwd()) == [Path.cwd() / "gitops/app1/service1/values-dev.yaml"]


def test_staged_deleted_files_are_relative_to_current_directory(
    committed_gitops_repository: GitOpsRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GIVEN the hook runs from a subdirectory, as for a nested project in a prek workspace
    git(committed_gitops_repository.gitops_path, "rm", "-q", "gitops/app1/service2/values-dev.yaml")
    monkeypatch.chdir(committed_gitops_repository.gitops_path / "gitops")

    # THEN
    assert get_staged_deleted_files(Path.cwd()) == [Path.cwd() / "app1/service2/values-dev.yaml"]


@pytest.fixture
def validated_instances(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Records the instances validated by main(), every instance being valid."""
    validated = []

    class FakeValidator:
        def __init__(self, config: ServiceInstanceConfig):
            validated.append(f"{config.service_name}/{config.env}-{config.instance}")

        def validate_configuration(self) -> list:
            return []

    monkeypatch.setattr(gitops_values_validation, "ServiceInstanceConfigValidator", FakeValidator)
    return validated


def test_main_without_changed_files_validates_every_instance(
    committed_gitops_repository: GitOpsRepository, validated_instances: list[str]
) -> None:
    assert main([]) == 0
    assert sorted(validated_instances) == ["service1/dev-main", "service1/prod-main", "service2/dev-main", "service2/prod-main"]


def test_main_with_changed_files_flag_and_no_change_only_checks_repository_constraints(
    committed_gitops_repository: GitOpsRepository, validated_instances: list[str]
) -> None:
    assert main(["--changed-files"]) == 0
    assert validated_instances == []


def test_main_with_changed_files_validates_instances_affected_by_changed_and_deleted_files(
    committed_gitops_repository: GitOpsRepository, validated_instances: list[str]
) -> None:
    # GIVEN a commit changing a service1 file, deleting a service2 env values file and a service2 instance file
    git(committed_gitops_repository.gitops_path, "rm", "-q", "gitops/app1/service2/values-dev.yaml")
    git(committed_gitops_repository.gitops_path, "rm", "-q", "gitops/app1/service2/values-prod-main.yaml")

    # WHEN
    exit_code = main(["--changed-files", "gitops/app1/service1/values-prod-main.yaml"])

    # THEN the deleted instance is not validated anymore
    assert exit_code == 0
    assert sorted(validated_instances) == ["service1/prod-main", "service2/dev-main"]
