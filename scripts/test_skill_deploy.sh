#!/bin/bash
set -euo pipefail

echo "=== Running Skill Deploy Substrate Integration Tests ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_ROOT="$(mktemp -d /tmp/test_skill_deploy.XXXXXX)"
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

assert_glob_matches() {
    local dir="$1"
    local pattern="$2"
    find "$dir" -maxdepth 1 -name "$pattern" | grep . >/dev/null || fail "Expected '$pattern' glob match in $dir"
}

# ---------------------------------------------------------------------------
# Mock repo setup
# ---------------------------------------------------------------------------
create_skill_test_repo() {
    local repo_dir="$1"
    local slug="$2"
    local skill_content="${3:-# Test Skill Fixture}"

    mkdir -p "$repo_dir/scripts" "$repo_dir/skills/$slug"

    # Copy the real skill_deploy entrypoint and library into the mock repo
    cp "$REPO_ROOT/scripts/skill_deploy.sh" "$repo_dir/scripts/skill_deploy.sh"
    cp "$REPO_ROOT/scripts/skill_deploy_lib.sh" "$repo_dir/scripts/skill_deploy_lib.sh"

    # Create the test skill
    cat > "$repo_dir/skills/$slug/SKILL.md" <<'INNEREOF'
INNEREOF
    printf '%s\n' "$skill_content" >> "$repo_dir/skills/$slug/SKILL.md"

    # Skill-local deploy wrapper (thin)
    cat > "$repo_dir/skills/$slug/deploy.sh" <<INNEREOF
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="\$(cd "\$SCRIPT_DIR/../.." && pwd)"
bash "\$REPO_ROOT/scripts/skill_deploy.sh" "$slug" "\$@"
INNEREOF
    chmod +x "$repo_dir/skills/$slug/deploy.sh"
}

create_full_mock_repo_for_kit() {
    local repo_dir="$1"
    local slug="$2"

    mkdir -p "$repo_dir/scripts" "$repo_dir/skills/$slug"

    # Copy the real skill_deploy entrypoint and library
    cp "$REPO_ROOT/scripts/skill_deploy.sh" "$repo_dir/scripts/skill_deploy.sh"
    cp "$REPO_ROOT/scripts/skill_deploy_lib.sh" "$repo_dir/scripts/skill_deploy_lib.sh"

    # Stub root deploy.sh (must succeed so kit-deploy.sh continues)
    cat > "$repo_dir/deploy.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$repo_dir/deploy.sh"

    # Copy real kit-deploy.sh
    cp "$REPO_ROOT/kit-deploy.sh" "$repo_dir/kit-deploy.sh"

    # Create the test skill
    cat > "$repo_dir/skills/$slug/SKILL.md" <<EOF
# $slug Test Fixture
EOF

    # Skill-local deploy wrapper (thin)
    cat > "$repo_dir/skills/$slug/deploy.sh" <<INNEREOF
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="\$(cd "\$SCRIPT_DIR/../.." && pwd)"
bash "\$REPO_ROOT/scripts/skill_deploy.sh" "$slug" "\$@"
INNEREOF
    chmod +x "$repo_dir/skills/$slug/deploy.sh"
}

setup_mock_bin() {
    local bin_dir="$1"
    local gemini_log="$2"
    local with_gemini="$3"

    mkdir -p "$bin_dir"

    if [ "$with_gemini" = "true" ]; then
        cat > "$bin_dir/gemini" <<'INNEREOF'
#!/bin/bash
printf '%s\n' "gemini $*" >> "$GEMINI_LOG_PATH"
exit "${GEMINI_MOCK_EXIT:-0}"
INNEREOF
        chmod +x "$bin_dir/gemini"
    else
        rm -f "$bin_dir/gemini"
    fi
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
# Test Case 1: generic deploy installs a skill
# ---------------------------------------------------------------------------
test_generic_deploy_installs_skill() {
    echo "--- test_generic_deploy_installs_skill ---"
    local slug="test-skill-1"
    local case_dir="$TEST_ROOT/tc1"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 2: generic deploy creates backup of existing runtime
# ---------------------------------------------------------------------------
test_generic_deploy_creates_backup_of_existing_runtime() {
    echo "--- test_generic_deploy_creates_backup_of_existing_runtime ---"
    local slug="test-skill-2"
    local case_dir="$TEST_ROOT/tc2"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug" "# Skill v2"
    seed_existing_runtime "$home_mock" "$slug"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Backup created
    assert_glob_matches "$home_mock/.openclaw/.releases/$slug" "backup_*.tar.gz"

    # Runtime replaced with new content
    assert_file_content_equals "$home_mock/.openclaw/skills/$slug/SKILL.md" "# Skill v2"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 3: pm-skill deploy wrapper remains compatible
# ---------------------------------------------------------------------------
test_pm_skill_deploy_wrapper_remains_compatible() {
    echo "--- test_pm_skill_deploy_wrapper_remains_compatible ---"
    local slug="pm-skill"
    local case_dir="$TEST_ROOT/tc3"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    mkdir -p "$repo_dir/scripts" "$repo_dir/skills/$slug"

    # Copy real lib and entrypoint
    cp "$REPO_ROOT/scripts/skill_deploy.sh" "$repo_dir/scripts/skill_deploy.sh"
    cp "$REPO_ROOT/scripts/skill_deploy_lib.sh" "$repo_dir/scripts/skill_deploy_lib.sh"

    # Create pm-skill source with SKILL.md (bare minimum)
    cat > "$repo_dir/skills/$slug/SKILL.md" <<'EOF'
# PM Skill
EOF

    # Use real pm-skill deploy.sh wrapper (already delegates to generic)
    cp "$REPO_ROOT/skills/pm-skill/deploy.sh" "$repo_dir/skills/$slug/deploy.sh"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/skills/$slug/deploy.sh" > /dev/null 2>&1

    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 4: deploy rejects empty slug
# ---------------------------------------------------------------------------
test_deploy_rejects_empty_slug() {
    echo "--- test_deploy_rejects_empty_slug ---"
    local slug="test-skill-4"
    local case_dir="$TEST_ROOT/tc4"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    if HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "" > /dev/null 2>&1; then
        fail "Expected deploy with empty slug to fail"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 5: deploy rejects slug with slash
# ---------------------------------------------------------------------------
test_deploy_rejects_slug_with_slash() {
    echo "--- test_deploy_rejects_slug_with_slash ---"
    local slug="test-skill-5"
    local case_dir="$TEST_ROOT/tc5"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    if HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "foo/bar" > /dev/null 2>&1; then
        fail "Expected deploy with slug containing '/' to fail"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 6: deploy rejects slug with dotdot
# ---------------------------------------------------------------------------
test_deploy_rejects_slug_with_dotdot() {
    echo "--- test_deploy_rejects_slug_with_dotdot ---"
    local slug="test-skill-6"
    local case_dir="$TEST_ROOT/tc6"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    if HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "../etc" > /dev/null 2>&1; then
        fail "Expected deploy with slug containing '..' to fail"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 7: deploy rejects missing skill dir
# ---------------------------------------------------------------------------
test_deploy_rejects_missing_skill_dir() {
    echo "--- test_deploy_rejects_missing_skill_dir ---"
    local slug="test-skill-7"
    local case_dir="$TEST_ROOT/tc7"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    if HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "nonexistent" > /dev/null 2>&1; then
        fail "Expected deploy with missing skill dir to fail"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 8: deploy rejects missing SKILL.md
# ---------------------------------------------------------------------------
test_deploy_rejects_missing_skill_md() {
    echo "--- test_deploy_rejects_missing_skill_md ---"
    local slug="no-skill-md"
    local case_dir="$TEST_ROOT/tc8"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    mkdir -p "$repo_dir/scripts" "$repo_dir/skills/$slug"

    # Copy real lib and entrypoint
    cp "$REPO_ROOT/scripts/skill_deploy.sh" "$repo_dir/scripts/skill_deploy.sh"
    cp "$REPO_ROOT/scripts/skill_deploy_lib.sh" "$repo_dir/scripts/skill_deploy_lib.sh"

    # Create skill dir WITHOUT SKILL.md
    echo "some file" > "$repo_dir/skills/$slug/README.md"

    if HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1; then
        fail "Expected deploy with missing SKILL.md to fail"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 9: deploy respects .release_ignore
# ---------------------------------------------------------------------------
test_deploy_respects_release_ignore() {
    echo "--- test_deploy_respects_release_ignore ---"
    local slug="test-skill-9"
    local case_dir="$TEST_ROOT/tc9"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Create a .log file in the skill source
    echo "should be excluded" > "$repo_dir/skills/$slug/test.log"

    # Create .release_ignore that excludes *.log
    echo "*.log" > "$repo_dir/skills/$slug/.release_ignore"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/test.log"
    # SKILL.md should still be deployed
    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 10: deploy applies common default excludes
# ---------------------------------------------------------------------------
test_deploy_applies_common_default_excludes() {
    echo "--- test_deploy_applies_common_default_excludes ---"
    local slug="test-skill-10"
    local case_dir="$TEST_ROOT/tc10"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Create excluded artifacts in the skill source
    mkdir -p "$repo_dir/skills/$slug/__pycache__"
    echo "pycache" > "$repo_dir/skills/$slug/__pycache__/test.pyc"
    mkdir -p "$repo_dir/skills/$slug/.git"
    echo "git" > "$repo_dir/skills/$slug/.git/HEAD"
    mkdir -p "$repo_dir/skills/$slug/.pytest_cache/v/cache"
    echo "pytest" > "$repo_dir/skills/$slug/.pytest_cache/v/cache/lastfailed"
    mkdir -p "$repo_dir/skills/$slug/.mypy_cache"
    echo "mypy" > "$repo_dir/skills/$slug/.mypy_cache/data.json"
    mkdir -p "$repo_dir/skills/$slug/.ruff_cache/0.0.0"
    echo "ruff" > "$repo_dir/skills/$slug/.ruff_cache/0.0.0/1234"
    mkdir -p "$repo_dir/skills/$slug/dist"
    echo "dist" > "$repo_dir/skills/$slug/dist/output.tar.gz"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/__pycache__"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/.git"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/.pytest_cache"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/.mypy_cache"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/.ruff_cache"
    assert_file_not_exists "$home_mock/.openclaw/skills/$slug/dist"
    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 11: HOME_MOCK isolation — real $HOME is never touched
# ---------------------------------------------------------------------------
test_deploy_with_home_mock_isolation() {
    echo "--- test_deploy_with_home_mock_isolation ---"
    local slug="test-skill-11"
    local case_dir="$TEST_ROOT/tc11"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Assert nothing was created in the real HOME for this slug
    if [ -d "$HOME/.openclaw/skills/$slug" ]; then
        fail "Real HOME was touched: $HOME/.openclaw/skills/$slug exists"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 12: deploy respects SDLC_RUNTIME_DIR (outside HOME_MOCK)
# ---------------------------------------------------------------------------
test_deploy_respects_sdlc_runtime_dir() {
    echo "--- test_deploy_respects_sdlc_runtime_dir ---"
    local slug="test-skill-12"
    local case_dir="$TEST_ROOT/tc12"
    local home_dir="$case_dir/home"
    local custom_runtime="$case_dir/custom_runtime"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Run without HOME_MOCK, with SDLC_RUNTIME_DIR set
    env -u HOME_MOCK HOME="$home_dir" SDLC_RUNTIME_DIR="$custom_runtime" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    assert_file_exists "$custom_runtime/$slug/SKILL.md"
    # Default HOME location should NOT have the skill
    assert_file_not_exists "$home_dir/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 13: HOME_MOCK overrides SDLC_RUNTIME_DIR
# ---------------------------------------------------------------------------
test_home_mock_overrides_sdlc_runtime_dir() {
    echo "--- test_home_mock_overrides_sdlc_runtime_dir ---"
    local slug="test-skill-13"
    local case_dir="$TEST_ROOT/tc13"
    local home_mock="$case_dir/home_mock"
    local custom_runtime="$case_dir/custom_runtime"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Run with BOTH HOME_MOCK and SDLC_RUNTIME_DIR — HOME_MOCK takes precedence
    HOME="$home_mock" HOME_MOCK="$home_mock" SDLC_RUNTIME_DIR="$custom_runtime" PATH="$BASE_PATH" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Deployed under HOME_MOCK
    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    # NOT deployed under SDLC_RUNTIME_DIR
    if [ -d "$custom_runtime/$slug" ]; then
        fail "HOME_MOCK should override SDLC_RUNTIME_DIR, but skill was deployed to $custom_runtime/$slug"
    fi
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 14: Gemini link when available
# ---------------------------------------------------------------------------
test_gemini_link_when_available() {
    echo "--- test_gemini_link_when_available ---"
    local slug="test-skill-14"
    local case_dir="$TEST_ROOT/tc14"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"
    local mock_bin="$case_dir/mock_bin"
    local gemini_log="$case_dir/gemini.log"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Set up mock gemini
    export GEMINI_LOG_PATH="$gemini_log"
    export GEMINI_MOCK_EXIT=0
    setup_mock_bin "$mock_bin" "$gemini_log" true

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$mock_bin:$BASE_PATH" \
        GEMINI_LOG_PATH="$gemini_log" GEMINI_MOCK_EXIT=0 \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Verify gemini was invoked with correct args
    grep -F "gemini skills link $home_mock/.openclaw/skills/$slug --consent" "$gemini_log" > /dev/null \
        || fail "Expected gemini link invocation in log"

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 15: Gemini link skipped when absent
# ---------------------------------------------------------------------------
test_gemini_link_skipped_when_absent() {
    echo "--- test_gemini_link_skipped_when_absent ---"
    local slug="test-skill-15"
    local case_dir="$TEST_ROOT/tc15"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"
    local mock_bin="$case_dir/mock_bin"
    local gemini_log="$case_dir/gemini.log"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    export GEMINI_LOG_PATH="$gemini_log"
    setup_mock_bin "$mock_bin" "$gemini_log" false

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$mock_bin:$BASE_PATH" \
        GEMINI_LOG_PATH="$gemini_log" \
        bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1

    # Deploy should succeed
    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"

    # Gemini should NOT have been invoked
    if [ -s "$gemini_log" ]; then
        fail "Gemini should not be invoked when absent, but log has content: $(cat "$gemini_log")"
    fi

    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 16: kit-deploy invokes skill deploy wrapper
# ---------------------------------------------------------------------------
test_kit_deploy_invokes_skill_deploy_wrapper() {
    echo "--- test_kit_deploy_invokes_skill_deploy_wrapper ---"
    local slug="test-skill-16"
    local case_dir="$TEST_ROOT/tc16"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_full_mock_repo_for_kit "$repo_dir" "$slug"

    HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
        bash "$repo_dir/kit-deploy.sh" --no-restart > /dev/null 2>&1

    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Test Case 17: backup retention keeps only latest 3 backups
# ---------------------------------------------------------------------------
test_backup_retention_keeps_only_latest_three() {
    echo "--- test_backup_retention_keeps_only_latest_three ---"
    local slug="test-skill-17"
    local case_dir="$TEST_ROOT/tc17"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/repo"

    mkdir -p "$case_dir"
    create_skill_test_repo "$repo_dir" "$slug"

    # Perform 5 consecutive deploys to generate 5 backups
    for i in $(seq 1 5); do
        # Update the skill content so each deploy creates a distinct backup
        echo "# Deploy $i" > "$repo_dir/skills/$slug/SKILL.md"
        HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$BASE_PATH" \
            bash "$repo_dir/scripts/skill_deploy.sh" "$slug" > /dev/null 2>&1
    done

    local releases_dir="$home_mock/.openclaw/.releases/$slug"
    local backup_count
    backup_count=$(ls -1 "$releases_dir"/backup_*.tar.gz 2>/dev/null | wc -l)

    if [ "$backup_count" -gt 3 ]; then
        fail "Backup retention failed: expected at most 3 backups, found $backup_count"
    fi
    if [ "$backup_count" -lt 1 ]; then
        fail "Expected at least 1 backup, found $backup_count"
    fi
    assert_file_exists "$home_mock/.openclaw/skills/$slug/SKILL.md"
    echo "✅ Passed"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_generic_deploy_installs_skill
test_generic_deploy_creates_backup_of_existing_runtime
test_pm_skill_deploy_wrapper_remains_compatible
test_deploy_rejects_empty_slug
test_deploy_rejects_slug_with_slash
test_deploy_rejects_slug_with_dotdot
test_deploy_rejects_missing_skill_dir
test_deploy_rejects_missing_skill_md
test_deploy_respects_release_ignore
test_deploy_applies_common_default_excludes
test_deploy_with_home_mock_isolation
test_deploy_respects_sdlc_runtime_dir
test_home_mock_overrides_sdlc_runtime_dir
test_gemini_link_when_available
test_gemini_link_skipped_when_absent
test_kit_deploy_invokes_skill_deploy_wrapper
test_backup_retention_keeps_only_latest_three

echo ""
echo "✅ Skill Deploy Substrate Integration Tests PASSED"
