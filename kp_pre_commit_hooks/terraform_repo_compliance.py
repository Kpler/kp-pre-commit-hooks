#!/usr/bin/env python3
"""
Pre-commit hook to check Terraform configuration file region consistency.

Rules:
- If any config file contains a region (e.g., dev-main.ireland.tfvars),
  then ALL main config files must specify a region.
- Files without region (e.g., dev-main.tfvars) are only allowed if NO files have regions.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ConfigFile:
    """Represents a Terraform configuration file."""

    path: Path
    environment: str
    workspace: Optional[str]
    region: Optional[str]

    @staticmethod
    def from_path(path: Path) -> "ConfigFile":
        match = re.match(
            r"^(?P<environment>[^-]+)(?:-(?P<workspace>[^.]+))?(?:\.(?P<region>[^.]+))?$",
            path.stem,
        )
        if not match:
            raise ValueError(f"Invalid config file path: {path}")

        return ConfigFile(
            path=path,
            environment=match.group("environment"),
            workspace=match.group("workspace"),
            region=match.group("region"),
        )


@dataclass
class CheckResult:
    """Represents a validation error."""

    check_name: str
    errors: list[str]
    solution_hint: str

    def success(self) -> bool:
        return len(self.errors) == 0


def find_config_files(service_folder: Path) -> list[ConfigFile]:
    """Find all .tfvars configuration files in services directories."""
    return [
        ConfigFile.from_path(config_file)
        for config_file in service_folder.glob("config/*/*.tfvars")
    ]


def find_services_folders(root_dir: Path) -> list[Path]:
    return sorted(
        [folder.relative_to(root_dir) for folder in root_dir.rglob("services/*") if folder.is_dir()]
    )


def check_region_consistency(root_dir: Path) -> CheckResult:
    errors = []

    for service_folder in find_services_folders(root_dir):
        service_name = service_folder.name

        service_workspace_config_files = [
            c for c in find_config_files(service_folder) if c.workspace
        ]
        config_with_region = [c for c in service_workspace_config_files if c.region]
        config_without_region = [c for c in service_workspace_config_files if not c.region]
        if len(config_with_region) > 0 and len(config_without_region) > 0:
            errors.append(
                f"\n❌ Service '{service_name}' has inconsistent region configuration:\n"
                f"  Files WITH region:\n"
                + "\n".join(f"    - {f.path}" for f in config_with_region)
                + f"\n  Files WITHOUT region (must add region):\n"
                + "\n".join(f"    - {f.path}" for f in config_without_region)
            )

    return CheckResult(
        check_name="Region Usage Consistency",
        errors=errors,
        solution_hint=(
            "When using multi-region setup, ALL workspace config files\n"
            "   must specify a region (e.g., dev-main.ireland.tfvars)\n"
            "   You cannot mix files with and without regions"
        ),
    )


def main() -> int:
    """Main entry point for the pre-commit hook."""
    # Get the repository root directory
    repo_root = Path.cwd()

    print("🔍 Checking Terraform Repository Kpler Compliance...")

    check_result = check_region_consistency(repo_root)

    if check_result.success():
        print(f"✅ {check_result.check_name} check passed.")
        return 0
    else:
        print(f"\n⚠️ {check_result.check_name} check failed!")
        print("-" * 60)
        print("\n".join(check_result.errors))
        print("-" * 60)
        print(f"\n💡 Solution: {check_result.solution_hint}")
        return 1


if __name__ == "__main__":
    sys.exit(main())