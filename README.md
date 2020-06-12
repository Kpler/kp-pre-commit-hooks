pre-commit-hooks
================

Some out-of-the-box hooks for [pre-commit](https://github.com/pre-commit/pre-commit).

### Using pre-commit-hooks with pre-commit

Add this to your `.pre-commit-config.yaml`

    -   repo: git@github.com:Kpler/kp-pre-commit-hooks.git
        rev: v0.0.0.1  # Use the ref you want to point at
        hooks:
        -   id: check-branch-linearity


### Running hooks from CircleCI

Cloning a repo using ssh doesn't work out of the box on CircleCI.

Workaround: adding this in .circleci/config.yml solve the issue (cf [link](https://discuss.circleci.com/t/the-authenticity-of-github-host-cant-be-stablished/33133)):
> mkdir ~/.ssh/ && echo -e "Host github.com\n\tStrictHostKeyChecking no\n" > ~/.ssh/config

example: https://github.com/Kpler/ct-pipeline/blob/1.269.12/.circleci/config.yml#L110

### Hooks available

#### `check-branch-linearity`
Simply check that your branch doesn't not contain any merge compare to master.
It's a pre-push hook and will always run

#### `check-branch-name`
Check that branch name is less than 70 characters
It's a pre-push hook and will always run

#### `check-commit-first-line-length`
Check that the first line of commit message is less than 72 characters
It's a pre-push hook and will always run
