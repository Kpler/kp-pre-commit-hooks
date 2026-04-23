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

[example of implementation]: https://github.com/Kpler/template-kafka-stream-msk/blob/main/src/ci/scala/schema_generator/VulcanSchemaGenerator.scala
[sbt command]: https://github.com/Kpler/template-kafka-stream-msk/blob/main/build.sbt#L75

#### `zizmor-workflows` / `zizmor-workflows-online`

Audit GitHub Actions workflow and composite-action files with [zizmor] for common security issues
(unpinned actions, dangerous triggers, excessive permissions, template injection, and ~30 others).

Two variants are provided so the same tool can be used locally without credentials and in CI with
the full audit set:

| Hook | Stage | Runs |
|------|-------|------|
| `zizmor-workflows` | `pre-commit` (default) | Offline audits only. No network, no token. |
| `zizmor-workflows-online` | `manual` (opt-in) | All audits, including `impostor-commit`, `known-vulnerable-actions`, `ref-confusion`, `stale-action-refs`. Requires `GH_TOKEN`. |

Both hooks match `.github/workflows/*.y[a]ml` and `.github/actions/*/action.y[a]ml` and default to
`--min-severity=high` (only `error[...]`-level findings block). Override via `args:` in your
`.pre-commit-config.yaml` to surface more:

```yaml
- id: zizmor-workflows
  args: [--min-severity=medium]  # or: low, informational
```

**Local usage** — add to `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/Kpler/kp-pre-commit-hooks.git
    rev: v0.23.0  # Use the latest version
    hooks:
      - id: zizmor-workflows
      # Also declare the online variant so CI can invoke it. Because its stage
      # is `manual`, it will not fire on `git commit` / `git push` locally.
      - id: zizmor-workflows-online
```

**CI usage** — add a step to your GitHub Actions workflow:
```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: '3.11'
- run: pip install pre-commit
- run: pre-commit run --hook-stage manual --all-files zizmor-workflows-online
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

[zizmor]: https://docs.zizmor.sh/

### Contributing

#### Debugging / testing
Hooks can be tried locally using `try-repo`
For example if I want to try `check-branch-linearity` from another repo
I can do:
```bash
pre-commit try-repo path_to_this_repo/kp-pre-commit-hooks/ check-branch-linearity --hook-stage push --verbose
```


### Local Debugging of Schema Validation Logic

Prereq:
`poetry install`

An example for testing against a repo:
`poetry run python kp_pre_commit_hooks/gitops_values_validation.py ~/repos/mt-inbox-gitops`

Send the entire gitops repository path in for it to parse through the gitops repository for validation.
