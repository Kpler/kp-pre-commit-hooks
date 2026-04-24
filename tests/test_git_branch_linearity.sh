#!/usr/bin/env bash
# End-to-end tests for git-branch-linearity.sh.
#
# These tests exercise the hook in a realistic GitHub Actions PR environment:
# a shallow clone (depth=1) with GITHUB_HEAD_REF set. This reproduces the
# failure mode seen in practice when --shallow-exclude was given a SHA
# instead of a ref name.

set -eu -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../git-branch-linearity.sh"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

pass=0
fail=0

on_exit() {
    rc=$?
    if [ -n "${WORKDIR:-}" ] && [ -d "${WORKDIR:-}" ]; then
        rm -rf "$WORKDIR"
    fi
    if [ "$fail" -gt 0 ]; then
        echo ""
        echo "FAIL: $fail test(s) failed, $pass passed"
        exit 1
    fi
    if [ "$rc" -ne 0 ]; then
        exit "$rc"
    fi
    echo ""
    echo "OK: $pass test(s) passed"
}
trap on_exit EXIT

setup_origin_with_linear_branch() {
    # Build an "origin" bare repo with:
    #   - main at commit M3 (three commits: M1, M2, M3)
    #   - feature branched from M3, with one additional linear commit F1
    # main has multiple commits so shallow-ification (truncation to 1 commit)
    # is observable in tests that inspect origin/main history afterwards.
    WORKDIR=$(mktemp -d)
    ORIGIN="$WORKDIR/origin.git"
    UPSTREAM="$WORKDIR/upstream"

    git init --bare -q -b main "$ORIGIN"
    git init -q -b main "$UPSTREAM"
    (
        cd "$UPSTREAM"
        git config user.email test@example.com
        git config user.name test
        git remote add origin "$ORIGIN"

        echo initial > file.txt
        git add file.txt
        git -c commit.gpgsign=false commit -q -m "M1 initial"
        echo two >> file.txt
        git -c commit.gpgsign=false commit -qam "M2"
        echo three >> file.txt
        git -c commit.gpgsign=false commit -qam "M3"
        git push -q origin main

        git checkout -q -b feature/linear
        echo change >> file.txt
        git -c commit.gpgsign=false commit -qam "F1 feature change"
        git push -q origin feature/linear
    )
}

add_merge_commit_on_feature() {
    # Add a merge commit onto the feature branch to trigger the linearity failure.
    (
        cd "$UPSTREAM"
        git checkout -q -b other main
        echo other > other.txt
        git add other.txt
        git -c commit.gpgsign=false commit -q -m "other branch commit"

        git checkout -q feature/linear
        git -c commit.gpgsign=false merge -q --no-ff other -m "Merge other into feature"
        git push -q origin feature/linear
    )
}

shallow_clone_like_actions_checkout() {
    # Reproduce actions/checkout@v6 default: a real shallow clone (depth=1)
    # with a narrow refspec pointing at the PR branch. file:// is required —
    # local path clones silently ignore --depth.
    CI_REPO="$WORKDIR/ci"
    git clone -q --depth=1 --branch feature/linear "file://$ORIGIN" "$CI_REPO"
}

expect_exit() {
    want=$1; shift
    name=$1; shift
    set +e
    output=$("$@" 2>&1)
    got=$?
    set -e
    if [ "$got" -eq "$want" ]; then
        pass=$((pass + 1))
        echo "PASS  $name"
    else
        fail=$((fail + 1))
        echo "FAIL  $name: want exit $want, got $got"
        echo "----- output -----"
        echo "$output"
        echo "------------------"
    fi
}

expect_not_shallow() {
    name=$1; repo=$2
    if [ -f "$repo/.git/shallow" ]; then
        fail=$((fail + 1))
        echo "FAIL  $name: .git/shallow exists, repo was unexpectedly shallow-ified"
    else
        pass=$((pass + 1))
        echo "PASS  $name"
    fi
}

expect_full_main_history() {
    name=$1; repo=$2; want_count=$3
    got=$(git -C "$repo" rev-list --count origin/main)
    if [ "$got" -eq "$want_count" ]; then
        pass=$((pass + 1))
        echo "PASS  $name"
    else
        fail=$((fail + 1))
        echo "FAIL  $name: origin/main has $got commits, expected $want_count"
    fi
}

# --------------------------------------------------------------------------
# Test 1: linear branch in a shallow CI clone with GITHUB_HEAD_REF should pass
# --------------------------------------------------------------------------
setup_origin_with_linear_branch
shallow_clone_like_actions_checkout

expect_exit 0 "shallow+GITHUB_HEAD_REF, linear branch" \
    env -C "$CI_REPO" GITHUB_HEAD_REF=feature/linear "$HOOK" main

rm -rf "$WORKDIR"

# --------------------------------------------------------------------------
# Test 2: branch with a merge commit in shallow CI clone should fail
# --------------------------------------------------------------------------
setup_origin_with_linear_branch
add_merge_commit_on_feature
shallow_clone_like_actions_checkout

expect_exit 1 "shallow+GITHUB_HEAD_REF, branch has merge commit" \
    env -C "$CI_REPO" GITHUB_HEAD_REF=feature/linear "$HOOK" main

rm -rf "$WORKDIR"

# --------------------------------------------------------------------------
# Test 3: no GITHUB_HEAD_REF (local run), linear branch, should pass
# --------------------------------------------------------------------------
setup_origin_with_linear_branch
LOCAL_REPO="$WORKDIR/local"
git clone -q --branch feature/linear "$ORIGIN" "$LOCAL_REPO"

expect_exit 0 "local (no GITHUB_HEAD_REF), linear branch" \
    env -C "$LOCAL_REPO" -u GITHUB_HEAD_REF "$HOOK" main

rm -rf "$WORKDIR"

# --------------------------------------------------------------------------
# Test 4: no GITHUB_HEAD_REF (local run), branch with merge commit, should fail
# --------------------------------------------------------------------------
setup_origin_with_linear_branch
add_merge_commit_on_feature
LOCAL_REPO="$WORKDIR/local"
git clone -q --branch feature/linear "$ORIGIN" "$LOCAL_REPO"

expect_exit 1 "local (no GITHUB_HEAD_REF), branch has merge commit" \
    env -C "$LOCAL_REPO" -u GITHUB_HEAD_REF "$HOOK" main

rm -rf "$WORKDIR"

# --------------------------------------------------------------------------
# Test 5: local full clone must not be shallow-ified by the hook.
#
# Regression test for the v0.57.0/v0.58.0 bug where the unconditional
# `git fetch --depth=1 origin main` truncated origin/main to a single commit
# on full clones, leaving the developer's local main detached from prior
# history. Reported by @tmaurin in the Slack thread that triggered PR 73.
# --------------------------------------------------------------------------
setup_origin_with_linear_branch
LOCAL_REPO="$WORKDIR/local"
git clone -q --branch feature/linear "$ORIGIN" "$LOCAL_REPO"

env -C "$LOCAL_REPO" -u GITHUB_HEAD_REF "$HOOK" main > /dev/null 2>&1

expect_not_shallow "local full clone stays non-shallow after hook run" "$LOCAL_REPO"
expect_full_main_history "local origin/main keeps full history (3 commits)" "$LOCAL_REPO" 3

rm -rf "$WORKDIR"

unset WORKDIR
