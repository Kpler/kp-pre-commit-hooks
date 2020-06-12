pre-commit-hooks
================

Some out-of-the-box hooks for [pre-commit](https://github.com/pre-commit/pre-commit).

### Using pre-commit-hooks with pre-commit

Add this to your `.pre-commit-config.yaml`

    -   repo: https://github.com/Kpler/kp-pre-commit-hooks
        rev: v0.0.0.1  # Use the ref you want to point at
        hooks:
        -   id: check-branch-linearity


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
