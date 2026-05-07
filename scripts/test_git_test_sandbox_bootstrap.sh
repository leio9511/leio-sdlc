#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
    echo "❌ test_git_test_sandbox_bootstrap.sh FAILED: $1"
    exit 1
}

assert_no_global_identity() {
    local sandbox_dir="$1"
    local home_dir="$2"

    if [ -f "$home_dir/.gitconfig" ]; then
        fail "Global git config should not be created in clean-runner HOME."
    fi

    if git -C "$sandbox_dir" config --global --get user.name >/dev/null 2>&1; then
        fail "Global git user.name unexpectedly exists."
    fi

    if git -C "$sandbox_dir" config --global --get user.email >/dev/null 2>&1; then
        fail "Global git user.email unexpectedly exists."
    fi
}

bootstrap_sets_repo_local_identity_without_global_git_config() {
    local sandbox_dir="$TEST_ROOT/repo_local_identity"
    local home_dir="$TEST_ROOT/home_local_identity"
    mkdir -p "$home_dir"

    (
        export HOME="$home_dir"
        export GIT_CONFIG_GLOBAL=/dev/null
        export GIT_CONFIG_NOSYSTEM=1
        unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

        init_git_test_sandbox "$sandbox_dir"

        if ! git -C "$sandbox_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            fail "Sandbox was not initialized as a git repository."
        fi

        local repo_name
        local repo_email
        repo_name="$(git -C "$sandbox_dir" config --local --get user.name || true)"
        repo_email="$(git -C "$sandbox_dir" config --local --get user.email || true)"

        [ "$repo_name" = "SDLC Test Sandbox" ] || fail "Repo-local user.name was not set by the helper."
        [ "$repo_email" = "sdlc-test-sandbox@example.invalid" ] || fail "Repo-local user.email was not set by the helper."

        assert_no_global_identity "$sandbox_dir" "$home_dir"

        echo "fixture" > "$sandbox_dir/fixture.txt"
        git -C "$sandbox_dir" add fixture.txt
        git -C "$sandbox_dir" commit -m "local identity commit" >/dev/null 2>&1 || fail "Minimal commit failed without host-global git identity."
    )
}

bootstrap_optional_baseline_commit_is_explicit_and_idempotent() {
    local sandbox_dir="$TEST_ROOT/repo_baseline"
    local home_dir="$TEST_ROOT/home_baseline"
    mkdir -p "$home_dir"

    (
        export HOME="$home_dir"
        export GIT_CONFIG_GLOBAL=/dev/null
        export GIT_CONFIG_NOSYSTEM=1
        unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

        init_git_test_sandbox "$sandbox_dir"

        if git -C "$sandbox_dir" rev-parse --verify HEAD >/dev/null 2>&1; then
            fail "Helper created an implicit baseline commit without an explicit request."
        fi

        init_git_test_sandbox "$sandbox_dir" --baseline-commit

        if ! git -C "$sandbox_dir" rev-parse --verify HEAD >/dev/null 2>&1; then
            fail "Explicit baseline commit request did not create a commit."
        fi

        local first_hash
        local second_hash
        local commit_count
        first_hash="$(git -C "$sandbox_dir" rev-parse HEAD)"
        commit_count="$(git -C "$sandbox_dir" rev-list --count HEAD)"
        [ "$commit_count" = "1" ] || fail "Explicit baseline commit should create exactly one commit."

        init_git_test_sandbox "$sandbox_dir" --baseline-commit

        second_hash="$(git -C "$sandbox_dir" rev-parse HEAD)"
        [ "$first_hash" = "$second_hash" ] || fail "Rerunning baseline bootstrap created an extra commit."

        commit_count="$(git -C "$sandbox_dir" rev-list --count HEAD)"
        [ "$commit_count" = "1" ] || fail "Baseline bootstrap is not idempotent."
    )
}

bootstrap_does_not_create_unrequested_business_state() {
    local sandbox_dir="$TEST_ROOT/repo_no_business_state"
    local home_dir="$TEST_ROOT/home_no_business_state"
    mkdir -p "$home_dir"

    (
        export HOME="$home_dir"
        export GIT_CONFIG_GLOBAL=/dev/null
        export GIT_CONFIG_NOSYSTEM=1
        unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

        init_git_test_sandbox "$sandbox_dir"

        local unexpected_paths=(
            "$sandbox_dir/STATE.md"
            "$sandbox_dir/preflight.sh"
            "$sandbox_dir/docs"
            "$sandbox_dir/.sdlc_runs"
            "$sandbox_dir/config"
            "$sandbox_dir/scripts"
            "$sandbox_dir/PRD.md"
            "$sandbox_dir/doctor.py"
        )

        local unexpected
        for unexpected in "${unexpected_paths[@]}"; do
            if [ -e "$unexpected" ]; then
                fail "Helper created unexpected business state: $unexpected"
            fi
        done

        local tracked_entries
        tracked_entries="$(find "$sandbox_dir" -mindepth 1 -maxdepth 1 ! -name .git | sort)"
        if [ -n "$tracked_entries" ]; then
            fail "Helper created unexpected top-level sandbox entries: $tracked_entries"
        fi
    )
}

echo "--- Running git test sandbox bootstrap regression tests ---"
bootstrap_sets_repo_local_identity_without_global_git_config
bootstrap_optional_baseline_commit_is_explicit_and_idempotent
bootstrap_does_not_create_unrequested_business_state

echo "✅ test_git_test_sandbox_bootstrap.sh PASSED"
