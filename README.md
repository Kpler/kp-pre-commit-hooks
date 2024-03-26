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
        # [...] add other specific hook id relevant from your project
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

This hook is specific to Kafka Stream or Kafka Producers application and will check that the repositories contains AVRO schemas files, under the `schemas/` folder, that are consistent with the code.
The presence of such schemas is required by the Kpler GitHub actions [check-kafka-schemas-compatibility] and [upload-kafka-schemas] and is also mandatory for Kafka application deployment in Kubernetes.

[check-kafka-schemas-compatibility]: https://github.com/Kpler/github-actions/blob/main/actions/kafka/check-kafka-schemas-compatibility/README.md
[upload-kafka-schemas]: https://github.com/Kpler/github-actions/blob/main/actions/kafka/upload-kafka-schemas/README.md


### Contributing

#### Debugging / testing
Hooks can be tried locally using `try-repo`
For example if I want to try `check-branch-linearity` from another repo
I can do:
```bash
pre-commit try-repo path_to_this_repo/kp-pre-commit-hooks/ check-branch-linearity --hook-stage push --verbose
```
