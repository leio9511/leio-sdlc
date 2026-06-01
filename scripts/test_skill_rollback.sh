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
# Test Case 8: rollback respects SDLC_RUNTIME_DIR when HOME_MOCK is unset
# When SDLC_RUNTIME_DIR is set and HOME_MOCK is NOT set, rollback must restore
# to $SDLC_RUNTIME_DIR/<slug> while reading backups from $HOME/.openclaw/.releases/<slug>.
# ---------------------------------------------------------------------------
test_rollback_respects_sdlc_runtime_dir() {
    echo "--- test_rollback_respects_sdlc_runtime_dir ---"
    local slug="test-rollback-8"
    local case_dir="$TEST_ROOT/tc8"
    local home_dir="$case_dir/home"
    local runtime_dir="$case_dir/runtime"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir" "$home_dir/.openclaw" "$runtime_dir"

    create_skill_test_repo "$repo_dir" "$slug"

    # Create backup tarball manually with known marker content
    # (backup always lives under $HOME/.openclaw/.releases/ regardless of SDLC_RUNTIME_DIR)
    local releases_dir="$home_dir/.openclaw/.releases/$slug"
    mkdir -p "$releases_dir"
    local staging="$case_dir/staging/$slug"
    mkdir -p "$staging"
    echo "backed-up-content" > "$staging/marker.txt"
    echo "# Skill SDLC_RUNTIME_DIR test" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20240101_000000.tar.gz" -C "$case_dir/staging" "$slug"

    # Set SDLC_RUNTIME_DIR, do NOT set HOME_MOCK
    HOME="$home_dir" SDLC_RUNTIME_DIR="$runtime_dir" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug" > /dev/null 2>&1

    # Assert restored at SDLC_RUNTIME_DIR/<slug>
    assert_file_exists "$runtime_dir/$slug/marker.txt"
    assert_file_content_equals "$runtime_dir/$slug/marker.txt" "backed-up-content"
    assert_file_exists "$runtime_dir/$slug/SKILL.md"

    # Assert NOT restored at $HOME/.openclaw/skills/<slug>
    assert_file_not_exists "$home_dir/.openclaw/skills/$slug"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 9: rollback handles symlink prod directory
# When PROD_DIR is a symlink (even dangling), rollback must remove it cleanly
# and restore a real directory from backup.
# ---------------------------------------------------------------------------
test_rollback_handles_symlink_prod_dir() {
    echo "--- test_rollback_handles_symlink_prod_dir ---"
    local slug="test-rollback-9"
    local case_dir="$TEST_ROOT/tc9"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"

    create_skill_test_repo "$repo_dir" "$slug"

    # Create backup tarball with known content
    local releases_dir="$home_mock/.openclaw/.releases/$slug"
    mkdir -p "$releases_dir"
    local staging="$case_dir/staging/$slug"
    mkdir -p "$staging"
    echo "symlink-backup-content" > "$staging/marker.txt"
    echo "# Skill symlink-test" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20240101_000000.tar.gz" -C "$case_dir/staging" "$slug"

    # Create PROD_DIR as a dangling symlink
    local prod_dir="$home_mock/.openclaw/skills/$slug"
    mkdir -p "$(dirname "$prod_dir")"
    ln -s "/tmp/nonexistent-target-$slug" "$prod_dir"

    # Pre-condition: verify it is a symlink
    [ -L "$prod_dir" ] || fail "Pre-condition failed: PROD_DIR is not a symlink"

    # Run rollback with HOME_MOCK
    if ! HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug" > /dev/null 2>&1; then
        fail "Rollback exited with non-zero status"
    fi

    # Assert PROD_DIR is now a real directory (not a symlink)
    if [ -L "$prod_dir" ]; then
        fail "PROD_DIR is still a symlink after rollback"
    fi
    [ -d "$prod_dir" ] || fail "PROD_DIR is not a directory after rollback"

    # Assert content matches backup
    assert_file_content_equals "$prod_dir/marker.txt" "symlink-backup-content"
    assert_file_exists "$prod_dir/SKILL.md"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 10: rollback retains only 3 most recent backups
# Create 4 backups with sequential timestamps, run rollback, assert only 3
# remain and the oldest is pruned.
# ---------------------------------------------------------------------------
test_rollback_retains_only_three_recent_backups() {
    echo "--- test_rollback_retains_only_three_recent_backups ---"
    local slug="test-rollback-retain"
    local case_dir="$TEST_ROOT/tc-retain"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"

    # Create a minimal repo so rollback can resolve REPO_ROOT
    create_skill_test_repo "$repo_dir" "$slug" "# Skill v1"

    # Create 4 backup tarballs manually with sequential timestamps
    local releases_dir="$home_mock/.openclaw/.releases/$slug"
    mkdir -p "$releases_dir"

    local staging="$case_dir/staging/$slug"

    # backup_20260101 — oldest, should be pruned
    rm -rf "$staging"
    mkdir -p "$staging"
    echo "backup-01-content" > "$staging/marker.txt"
    echo "# Skill backup-01" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20260101_000001.tar.gz" -C "$case_dir/staging" "$slug"

    # backup_20260102
    rm -rf "$staging"
    mkdir -p "$staging"
    echo "backup-02-content" > "$staging/marker.txt"
    echo "# Skill backup-02" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20260102_000002.tar.gz" -C "$case_dir/staging" "$slug"

    # backup_20260103
    rm -rf "$staging"
    mkdir -p "$staging"
    echo "backup-03-content" > "$staging/marker.txt"
    echo "# Skill backup-03" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20260103_000003.tar.gz" -C "$case_dir/staging" "$slug"

    # backup_20260104 — latest, should be restored and kept
    rm -rf "$staging"
    mkdir -p "$staging"
    echo "backup-04-content" > "$staging/marker.txt"
    echo "# Skill backup-04" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20260104_000004.tar.gz" -C "$case_dir/staging" "$slug"

    # Set up current prod directory with distinct content
    local prod_dir="$home_mock/.openclaw/skills/$slug"
    mkdir -p "$prod_dir"
    echo "current-prod-content" > "$prod_dir/marker.txt"
    echo "# Skill current" > "$prod_dir/SKILL.md"

    # Verify we have exactly 4 backups before rollback
    local backup_count_before
    backup_count_before=$(ls -1 "$releases_dir"/backup_*.tar.gz 2>/dev/null | wc -l)
    if [ "$backup_count_before" -ne 4 ]; then
        fail "Expected 4 backups before rollback, found $backup_count_before"
    fi

    # Invoke rollback
    if ! HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug" > /dev/null 2>&1; then
        fail "Rollback exited with non-zero status"
    fi

    # Assert exactly 3 backup tarballs remain
    local backup_count_after
    backup_count_after=$(ls -1 "$releases_dir"/backup_*.tar.gz 2>/dev/null | wc -l)
    if [ "$backup_count_after" -ne 3 ]; then
        fail "Expected 3 backups after rollback, found $backup_count_after"
    fi

    # Assert oldest backup is removed
    assert_file_not_exists "$releases_dir/backup_20260101_000001.tar.gz"

    # Assert latest backup still exists
    assert_file_exists "$releases_dir/backup_20260104_000004.tar.gz"

    # Assert rollback restored content from latest backup
    assert_file_content_equals "$prod_dir/marker.txt" "backup-04-content"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 11: pm-skill rollback wrapper delegation-only verification (PR-002_2_3_1)
# Static analysis of the real repository skills/pm-skill/rollback.sh.
# No runtime execution or HOME_MOCK isolation needed.
# Satisfies PRD Scenario 6 (skill-local wrappers do not duplicate deploy logic).
# ---------------------------------------------------------------------------
test_pm_skill_rollback_wrapper_delegation_only() {
    echo "--- test_pm_skill_rollback_wrapper_delegation_only ---"

    local wrapper_path="$REPO_ROOT/skills/pm-skill/rollback.sh"

    # Pre-condition: the real wrapper must exist
    assert_file_exists "$wrapper_path"

    # Assertion 1: Delegation reference — wrapper must reference skill_rollback.sh or skill_deploy_lib.sh
    if ! grep -qE "skill_rollback.sh|skill_deploy_lib.sh" "$wrapper_path"; then
        fail "pm-skill rollback wrapper must reference skill_rollback.sh or skill_deploy_lib.sh (delegation target)"
    fi

    # Assertion 2: No inline tar operations — wrapper must NOT contain tar -xzf or tar -czf
    if grep -qE "tar -[cx]zf" "$wrapper_path"; then
        fail "pm-skill rollback wrapper must not contain inline tar extraction or creation"
    fi

    # Assertion 3: No inline rm -rf restoration — wrapper must NOT contain rm -rf targeting production or skills directories
    if grep -qE "rm -rf.*(PROD_DIR|OLD_DIR|skills)" "$wrapper_path"; then
        fail "pm-skill rollback wrapper must not contain inline rm -rf restoration"
    fi

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 12: pm-skill rollback wrapper functional correctness (PR-002_2_3_1)
# Deploy v1, then deploy v2 (backs up v1), then invoke skills/pm-skill/rollback.sh
# with HOME_MOCK. Assert v1 is restored with its marker file.
# Covers PRD Scenario 5 (pm-skill rollback wrapper remains compatible).
# ---------------------------------------------------------------------------
test_pm_skill_rollback_wrapper_functional_correctness() {
    echo "--- test_pm_skill_rollback_wrapper_functional_correctness ---"
    local slug="pm-skill"
    local case_dir="$TEST_ROOT/tc_pm_func"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"

    # Step 1: Create repo with pm-skill v1 content
    create_skill_test_repo "$repo_dir" "$slug" "# pm-skill v1"
    # Add v1 marker file
    echo "v1-pm-marker" > "$repo_dir/skills/$slug/v1_pm_marker.txt"

    # Step 2: Create the pm-skill rollback wrapper
    cat > "$repo_dir/skills/$slug/rollback.sh" << 'WRAPPER_EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$REPO_ROOT/scripts/skill_rollback.sh" pm-skill "$@"
WRAPPER_EOF
    chmod +x "$repo_dir/skills/$slug/rollback.sh"

    # Step 3: Deploy v1
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/v1_pm_marker.txt"
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# pm-skill v1"

    # Step 4: Change source to v2
    echo "# pm-skill v2" > "$repo_dir/skills/$slug/SKILL.md"
    echo "v2-pm-marker" > "$repo_dir/skills/$slug/v2_pm_marker.txt"
    rm -f "$repo_dir/skills/$slug/v1_pm_marker.txt"

    # Step 5: Deploy v2 — creates backup of v1
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Verify v2 is in place
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# pm-skill v2"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/v2_pm_marker.txt"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/v1_pm_marker.txt"

    # Verify a backup was created
    local releases_dir="$home_mock/.openclaw/.releases/$slug"
    assert_file_exists "$releases_dir"
    local backup_count
    backup_count=$(ls -1 "$releases_dir"/backup_*.tar.gz 2>/dev/null | wc -l)
    if [ "$backup_count" -lt 1 ]; then
        fail "Expected at least 1 backup, found $backup_count"
    fi

    # Step 6: Invoke pm-skill rollback wrapper with HOME_MOCK
    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/skills/$slug/rollback.sh" > /dev/null 2>&1

    # Assert v1 content restored
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# pm-skill v1"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/v1_pm_marker.txt"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/v2_pm_marker.txt"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 11: rollback must never invoke openclaw gateway restart (PR-002_2_4)
# Regression guard: mock openclaw binary on PATH, no HOME_MOCK, no --no-restart.
# Assert the substrate never calls 'openclaw gateway restart'.
# ---------------------------------------------------------------------------
test_rollback_does_not_restart_gateway() {
    echo "--- test_rollback_does_not_restart_gateway ---"
    local slug="test-no-restart-gw"
    local case_dir="$TEST_ROOT/tc_no_gw_restart"
    local home_dir="$case_dir/home"
    local repo_dir="$case_dir/repo"
    local mock_bin_dir="$case_dir/mock_bin"
    local mock_log_file="$case_dir/mock_openclaw.log"

    mkdir -p "$case_dir" "$home_dir/.openclaw" "$mock_bin_dir"

    create_skill_test_repo "$repo_dir" "$slug"

    # Create mock openclaw binary that logs all invocations
    cat > "$mock_bin_dir/openclaw" << 'MOCK_EOF'
#!/bin/bash
echo "$@" >> "$MOCK_LOG_FILE"
exit 0
MOCK_EOF
    chmod +x "$mock_bin_dir/openclaw"

    # Create backup tarball manually under the temp HOME
    local releases_dir="$home_dir/.openclaw/.releases/$slug"
    mkdir -p "$releases_dir"
    local staging="$case_dir/staging/$slug"
    mkdir -p "$staging"
    echo "no-restart-marker" > "$staging/marker.txt"
    echo "# No Gateway Restart Test" > "$staging/SKILL.md"
    tar -czf "$releases_dir/backup_20240101_000000.tar.gz" -C "$case_dir/staging" "$slug"

    # Invoke rollback: HOME = temp dir (simulates real-home, no HOME_MOCK)
    # --no-restart is NOT passed
    # Mock openclaw is first on PATH
    if ! MOCK_LOG_FILE="$mock_log_file" HOME="$home_dir" PATH="$mock_bin_dir:$BASE_PATH" \
        bash "$repo_dir/scripts/skill_rollback.sh" "$slug" > /dev/null 2>&1; then
        fail "Rollback exited with non-zero status"
    fi

    # Assert no gateway restart was invoked
    if [ -f "$mock_log_file" ]; then
        if grep -q "gateway restart" "$mock_log_file"; then
            fail "Mock openclaw log contains 'gateway restart' — skill rollback must not restart gateway"
        fi
    fi

    # Assert backup content was restored
    assert_file_exists "$home_dir/.openclaw/skills/$slug/SKILL.md"
    assert_file_exists "$home_dir/.openclaw/skills/$slug/marker.txt"
    assert_file_content_equals "$home_dir/.openclaw/skills/$slug/marker.txt" "no-restart-marker"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_pm_skill_rollback_wrapper_functional_correctness
test_pm_skill_rollback_wrapper_delegation_only
test_generic_rollback_restores_latest_backup
test_rollback_rejects_empty_slug
test_rollback_rejects_slug_with_slash
test_rollback_rejects_slug_with_dotdot
test_rollback_fails_when_no_releases_dir
test_rollback_fails_when_no_backups
test_rollback_with_home_mock_isolation
test_rollback_respects_sdlc_runtime_dir
test_rollback_handles_symlink_prod_dir
test_rollback_retains_only_three_recent_backups
test_rollback_does_not_restart_gateway
echo ""
echo "✅ Skill Rollback Substrate Integration Tests PASSED"
