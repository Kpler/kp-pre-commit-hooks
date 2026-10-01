pre-commit-hooks
================

Some out-of-the-box hooks for [pre-commit](https://github.com/pre-commit/pre-commit), and
a github action to easily run all kind of hooks from github CI.

### Using pre-commit-hooks with pre-commit

Add this to your `.pre-commit-config.yaml`

```yaml
    -   repo: https://github.com/Kpler/kp-pre-commit-hooks.git
        rev: v0.0.7  # Use the ref you want to point at
        hooks:
        -   id: check-branch-linearity
        -   id: check-branch-name
        -   id: no-ephemeral-links
            exclude: '\.md$'
```

### Hooks available

#### `check-branch-linearity`
Simply check that your branch doesn't not contain any merge compare to a target branch, `main` by default.
It's a pre-push hook and will always run

To configure the target branch:
```yaml
    hooks:
    -   id: check-branch-linearity
        args: [targetbranch]
```

#### `check-branch-name`
Check that branch name is less than 70 characters
It's a pre-push hook and will always run

#### `no-ephemeral-links`
Time is fleeting, we change services.
Consequently to keep the code futureproof we don't
want links to ephemeral thrid party stuff (slack, clubhouse, atlassian)

#### `fastapi-generate-openapi-specification`
Generate the Open API spec from a Fast API. If it has changed, write the new one and fails. If not, succeeds.

#### `kafka-check-schemas`

Check that the Kafka schemas present in the `schemas/` folder are consistent with the code.

This hook currently only supports the `scala` language for now and relies on the presence of the `sbt generateKafkaSchemas` command to re-generate and compare the schemas.

The implementation of the `generateKafkaSchemas` is up to each project, but you can find an [example of implementation] in the `template-kafka-stream-msk` project with the corresponding [sbt command] defined in the `build.sbt` file

Add these lines in your `.pre-commit-config.yaml` file to enable this pre-commit hook:
```yaml
repos:
  # [...]
  - repo: https://github.com/Kpler/kp-pre-commit-hooks.git
    rev: v0.22.0
    hooks:
      # [...]
      - id: kafka-check-schemas
```

#### `terraform-repo-compliance`

Check that the Terraform repository follows Kpler's compliance rules:
- Region consistency: If any config file contains a region (e.g., `dev-main.ireland.tfvars`), then ALL main config files must specify a region. Files without region (e.g., `dev-main.tfvars`) are only allowed if NO files have regions.

This hook runs on pre-commit and checks `.tfvars` files.

Add these lines in your `.pre-commit-config.yaml` file to enable this pre-commit hook:
```yaml
repos:
  # [...]
  - repo: https://github.com/Kpler/kp-pre-commit-hooks.git
    rev: v0.22.0  # Use the latest version
    hooks:
      # [...]
      - id: terraform-repo-compliance
```

#### `gitops-values-validation`

Validate the values files of a gitops repository (`gitops/<application>/<service>/`) against the JSON schema
of the `platform-managed-chart` version declared in `Chart.yaml` / `Chart-<env>.yaml`, plus Kpler specific rules:
- service names are unique across applications and match their folder
- topic names follow the naming convention and `maxLocalTopicBytes` stays within the allowed limits
- the `$schema` header of each values file matches the chart version (it is fixed automatically when wrong)

The JSON schemas are downloaded from S3 and cached in `~/.cache/pre-commit/kp-pre-commit-hooks/schemas`, so the
[Twingate VPN](https://kpler.atlassian.net/wiki/spaces/KSD/pages/243562083/Install+and+configure+the+Twingate+VPN+client)
must be up when a schema is not cached yet. The hook requires Python 3.10 or later.

On commit, only the service instances depending on the changed files (`Chart.yaml`, `Chart-<env>.yaml`,
`values.yaml`, `values-<env>.yaml`, `values-<env>-<instance>.yaml`) are validated. As pre-commit never passes
deleted files to hooks, the staged deleted files are added by the script itself. Repository-level constraints
(unique service names) are always checked. Run it with `--all-files` (e.g. in CI) to validate every instance:
```bash
pre-commit run gitops-values-validation --all-files
```

Add these lines in your `.pre-commit-config.yaml` file to enable this pre-commit hook:
```yaml
repos:
  # [...]
  - repo: https://github.com/Kpler/kp-pre-commit-hooks.git
    rev: v0.63.0  # Use the latest version (v0.63.0+ to only validate the changed files)
    hooks:
      # [...]
      - id: gitops-values-validation
```

[example of implementation]: https://github.com/Kpler/template-kafka-stream-msk/blob/main/src/ci/scala/schema_generator/VulcanSchemaGenerator.scala
[sbt command]: https://github.com/Kpler/template-kafka-stream-msk/blob/main/build.sbt#L75

### Contributing

#### Debugging / testing
Hooks can be tried locally using `try-repo`
For example if I want to try `check-branch-linearity` from another repo
I can do:
```bash
pre-commit try-repo path_to_this_repo/kp-pre-commit-hooks/ check-branch-linearity --hook-stage push --verbose
```


#### Development environment

Use `nix-shell` (or [direnv](https://direnv.net/) with the provided `.envrc`) to get Python, Poetry and
pre-commit, or install Python 3.10+ and Poetry yourself. Then:
```bash
poetry install
poetry run pytest tests
```

The tests use a minimal schema (`tests/test_data/schema-platform-managed-chart-strict.json`) holding only the parts of
the real schema that carry the Kpler specific rules (`additionalChecks`), so they run without the VPN, e.g. in CI.
To run them against the real schemas, with the Twingate VPN up:
```bash
poetry run pytest tests --real-schema
```

#### Local Debugging of Schema Validation Logic

An example for testing against a repo:
`poetry run python kp_pre_commit_hooks/gitops_values_validation.py ~/repos/mt-inbox-gitops`

Send the entire gitops repository path in for it to parse through the gitops repository for validation.
To only validate the instances affected by some files, as the hook does, run it from the gitops repository root
with `--changed-files`:
`poetry -P path_to_this_repo/kp-pre-commit-hooks run python -m kp_pre_commit_hooks.gitops_values_validation --changed-files gitops/app/service/values-dev.yaml`
