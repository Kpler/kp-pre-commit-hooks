pre-commit-hooks
================

Some out-of-the-box hooks for [pre-commit](https://github.com/pre-commit/pre-commit).

### Using pre-commit-hooks with pre-commit

Add this to your `.pre-commit-config.yaml`

    -   repo: https://github.com/Kpler/kp-pre-commit-hooks.git
        rev: v0.0.3  # Use the ref you want to point at
        hooks:
        -   id: check-branch-linearity
        -   id: check-commit-first-line-length
        -   id: check-branch-name

### Hooks available

#### `check-branch-linearity`
Simply check that your branch doesn't not contain any merge compare to master.
It's a pre-push hook and will always run

#### `check-branch-name`
Check that branch name is less than 70 characters
It's a pre-push hook and will always run

#### `no-ephemeral-links`
Time is fleeting, we change services.
Consequently to keep the code futureproof we don't
want links to ephemeral thrid party stuff (slack, clubhouse, atlassian)
