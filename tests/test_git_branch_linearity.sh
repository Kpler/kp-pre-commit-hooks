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
    #   - main at commit M1
    #   - feature branched from M1, with one additional linear commit F1
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

unset WORKDIR
