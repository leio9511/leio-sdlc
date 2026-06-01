#!/bin/bash
set -euo pipefail

echo "=== Running Skill Rollback Substrate Integration Tests ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_ROOT="$(mktemp -d /tmp/test_skill_rollback.XXXXXX)"
BASE_PATH="/usr/bin:/bin"

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

fail() {
    echo "❌ Assertion Failed: $1"
    exit 1
}

assert_file_exists() {
    local path="$1"
    [ -e "$path" ] || fail "Expected path to exist: $path"
}

assert_file_not_exists() {
    local path="$1"
    [ ! -e "$path" ] || fail "Expected path to be absent: $path"
}

assert_file_content_equals() {
    local path="$1"
    local expected="$2"
    local actual
    actual="$(cat "$path")"
    [ "$actual" = "$expected" ] || fail "Expected $path to equal '$expected' but got '$actual'"
}

assert_exit_nonzero() {
    local cmd_desc="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        fail "Expected non-zero exit for: $cmd_desc"
    fi
}

assert_exit_nonzero_with_stderr() {
    local cmd_desc="$1"
    shift
    local stderr_out
    stderr_out="$("$@" 2>&1 >/dev/null)" && fail "Expected non-zero exit for: $cmd_desc"
    if [ -z "$stderr_out" ]; then
        fail "Expected stderr output for: $cmd_desc"
    fi
}

# ---------------------------------------------------------------------------
# Mock repo setup helpers
# ---------------------------------------------------------------------------
create_skill_test_repo() {
    local repo_dir="$1"
    local slug="$2"
    local skill_content="${3:-# Test Skill Fixture}"

    mkdir -p "$repo_dir/scripts" "$repo_dir/skills/$slug"

    # Copy the real entrypoints and library into the mock repo
    cp "$REPO_ROOT/scripts/skill_deploy.sh" "$repo_dir/scripts/skill_deploy.sh"
    cp "$REPO_ROOT/scripts/skill_rollback.sh" "$repo_dir/scripts/skill_rollback.sh"
    cp "$REPO_ROOT/scripts/skill_deploy_lib.sh" "$repo_dir/scripts/skill_deploy_lib.sh"

    # Create the test skill with given content
    printf '%s\n' "$skill_content" > "$repo_dir/skills/$slug/SKILL.md"
}

seed_existing_runtime() {
    local home_dir="$1"
    local slug="$2"

    local prod_dir="$home_dir/.openclaw/skills/$slug"
    mkdir -p "$prod_dir"
    echo "v0" > "$prod_dir/version.txt"
    echo "old-content" > "$prod_dir/SKILL.md"
}

# ---------------------------------------------------------------------------
# Test Case 1: generic rollback restores the latest backup
# Deploy v1, then deploy v2 (which backs up v1), then rollback should restore v1.
# ---------------------------------------------------------------------------
test_generic_rollback_restores_latest_backup() {
    echo "--- test_generic_rollback_restores_latest_backup ---"
    local slug="test-rollback-1"
    local case_dir="$TEST_ROOT/tc1"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"

    # Step 1: Create repo with v1 content
    create_skill_test_repo "$repo_dir" "$slug" "# Skill v1"
    # Add a marker file unique to v1
    echo "v1-marker" > "$repo_dir/skills/$slug/v1_marker.txt"

    # Step 2: Deploy v1
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/v1_marker.txt"
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# Skill v1"

    # Step 3: Change source to v2 (different SKILL.md, different marker)
    echo "# Skill v2" > "$repo_dir/skills/$slug/SKILL.md"
    echo "v2-marker" > "$repo_dir/skills/$slug/v2_marker.txt"
    rm -f "$repo_dir/skills/$slug/v1_marker.txt"

    # Step 4: Deploy v2 — this creates a backup of v1
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Verify v2 is now in place
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# Skill v2"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/v2_marker.txt"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/v1_marker.txt"

    # Verify a backup was created
    local releases_dir="$home_mock/.openclaw/.releases/$slug"
    assert_file_exists "$releases_dir"
    local backup_count
    backup_count=$(ls -1 "$releases_dir"/backup_*.tar.gz 2>/dev/null | wc -l)
    if [ "$backup_count" -lt 1 ]; then
        fail "Expected at least 1 backup, found $backup_count"
    fi

    # Step 5: Rollback — should restore v1 from backup
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug" > /dev/null 2>&1

    # Assert v1 content is restored
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# Skill v1"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/v1_marker.txt"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/v2_marker.txt"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 2: rollback rejects empty slug
# ---------------------------------------------------------------------------
test_rollback_rejects_empty_slug() {
    echo "--- test_rollback_rejects_empty_slug ---"
    local slug="test-rollback-2"
    local case_dir="$TEST_ROOT/tc2"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    assert_exit_nonzero_with_stderr "rollback with empty slug" \
        env HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" ""

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 3: rollback rejects slug with slash
# ---------------------------------------------------------------------------
test_rollback_rejects_slug_with_slash() {
    echo "--- test_rollback_rejects_slug_with_slash ---"
    local slug="test-rollback-3"
    local case_dir="$TEST_ROOT/tc3"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    assert_exit_nonzero "rollback with slug containing '/'" \
        env HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "foo/bar"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 4: rollback rejects slug with dotdot
# ---------------------------------------------------------------------------
test_rollback_rejects_slug_with_dotdot() {
    echo "--- test_rollback_rejects_slug_with_dotdot ---"
    local slug="test-rollback-4"
    local case_dir="$TEST_ROOT/tc4"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    assert_exit_nonzero "rollback with slug containing '..'" \
        env HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "../etc"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 5: rollback fails when no releases dir
# ---------------------------------------------------------------------------
test_rollback_fails_when_no_releases_dir() {
    echo "--- test_rollback_fails_when_no_releases_dir ---"
    local slug="test-rollback-5"
    local case_dir="$TEST_ROOT/tc5"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # HOME_MOCK is set but no releases directory exists for this slug
    # (we never deployed, so no .releases/<slug> was created)

    assert_exit_nonzero_with_stderr "rollback when no releases dir" \
        env HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 6: rollback fails when no backups exist
# ---------------------------------------------------------------------------
test_rollback_fails_when_no_backups() {
    echo "--- test_rollback_fails_when_no_backups ---"
    local slug="test-rollback-6"
    local case_dir="$TEST_ROOT/tc6"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Create the releases directory but with NO backup files inside
    local releases_dir="$home_mock/.openclaw/.releases/$slug"
    mkdir -p "$releases_dir"
    # Put a non-backup file to confirm the dir exists but has no backups
    touch "$releases_dir/README.txt"

    assert_exit_nonzero_with_stderr "rollback when no backups" \
        env HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 7: rollback with HOME_MOCK isolation
# ---------------------------------------------------------------------------
test_rollback_with_home_mock_isolation() {
    echo "--- test_rollback_with_home_mock_isolation ---"
    local slug="test-rollback-7"
    local case_dir="$TEST_ROOT/tc7"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug" "# Skill v1"

    # First deploy to create runtime + then deploy v2 to create a backup
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    echo "# Skill v2" > "$repo_dir/skills/$slug/SKILL.md"
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Snapshot the real HOME skills dir state before rollback
    local real_skills_dir="$HOME/.openclaw/skills"
    local real_skills_before=""
    if [ -d "$real_skills_dir" ]; then
        real_skills_before="$(ls -1 "$real_skills_dir" 2>/dev/null || true)"
    fi

    # Run rollback with HOME_MOCK
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug" > /dev/null 2>&1

    # Assert rollback happened inside HOME_MOCK
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# Skill v1"

    # Assert the real HOME skills directory was not modified
    if [ -d "$real_skills_dir/$slug" ]; then
        fail "Real HOME was touched: $real_skills_dir/$slug exists when it should not"
    fi
    # Verify the real skills directory listing is unchanged
    local real_skills_after=""
    if [ -d "$real_skills_dir" ]; then
        real_skills_after="$(ls -1 "$real_skills_dir" 2>/dev/null || true)"
    fi
    if [ "$real_skills_before" != "$real_skills_after" ]; then
        fail "Real HOME skills directory was modified during HOME_MOCK rollback"
    fi

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_generic_rollback_restores_latest_backup
test_rollback_rejects_empty_slug
test_rollback_rejects_slug_with_slash
test_rollback_rejects_slug_with_dotdot
test_rollback_fails_when_no_releases_dir
test_rollback_fails_when_no_backups
test_rollback_with_home_mock_isolation

echo ""
echo "✅ Skill Rollback Substrate Integration Tests PASSED"
