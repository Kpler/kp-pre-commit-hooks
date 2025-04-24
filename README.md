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


### Local Debugging of Schema Validation Logic

Prereq:
`poetry install`

An example for testing against a repo:
`poetry run python kp_pre_commit_hooks/gitops-values-validation.py  repos/mt-inbox-gitops`

Send the entire gitops repository path in for it to parse through the gitops repository for validation.
