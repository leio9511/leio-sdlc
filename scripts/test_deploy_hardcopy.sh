#!/bin/bash
set -euo pipefail

echo "=== Running Hard-Copy Deploy & Rollback Integration Test ==="

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TEST_ROOT=$(mktemp -d /tmp/test_deploy_hardcopy.XXXXXX)
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
    actual=$(cat "$path")
    [ "$actual" = "$expected" ] || fail "Expected $path to equal '$expected' but got '$actual'"
}

assert_files_equal() {
    local left="$1"
    local right="$2"
    cmp -s "$left" "$right" || fail "Expected files to match: $left vs $right"
}

assert_tree_equal() {
    local left="$1"
    local right="$2"
    if ! diff -ru "$left" "$right" >/dev/null; then
        diff -ru "$left" "$right"
        fail "Expected directory trees to match: $left vs $right"
    fi
}

assert_no_gateway_restart() {
    local log_path="$1"
    if [ -s "$log_path" ] && grep -q "gateway restart" "$log_path"; then
        cat "$log_path"
        fail "Detected forbidden gateway restart invocation in $log_path"
    fi
}

assert_log_contains() {
    local log_path="$1"
    local needle="$2"
    grep -F -- "$needle" "$log_path" >/dev/null || fail "Expected '$needle' in $log_path"
}

setup_mock_bin() {
    local bin_dir="$1"
    local openclaw_log="$2"
    local gemini_log="$3"
    local with_gemini="$4"

    mkdir -p "$bin_dir"
    : > "$openclaw_log"
    : > "$gemini_log"

    cat > "$bin_dir/openclaw" <<EOF
#!/bin/bash
printf '%s\n' "openclaw \$*" >> "$openclaw_log"
exit 0
EOF
    chmod +x "$bin_dir/openclaw"

    if [ "$with_gemini" = "true" ]; then
        cat > "$bin_dir/gemini" <<EOF
#!/bin/bash
printf '%s\n' "gemini \$*" >> "$gemini_log"
exit 0
EOF
        chmod +x "$bin_dir/gemini"
    else
        rm -f "$bin_dir/gemini"
    fi
}

create_mock_repo() {
    local repo_dir="$1"

    mkdir -p "$repo_dir/scripts" "$repo_dir/skills/pm-skill" "$repo_dir/config" "$repo_dir/.sdlc_hooks"

    cp "$REPO_ROOT/deploy.sh" "$repo_dir/deploy.sh"
    cp "$REPO_ROOT/kit-deploy.sh" "$repo_dir/kit-deploy.sh"
    cp "$REPO_ROOT/scripts/rollback.sh" "$repo_dir/scripts/rollback.sh"
    cp "$REPO_ROOT/scripts/build_release.sh" "$repo_dir/scripts/build_release.sh"
    cp "$REPO_ROOT/scripts/agent_driver.py" "$repo_dir/scripts/agent_driver.py"
    cp "$REPO_ROOT/scripts/utils_notification.py" "$repo_dir/scripts/utils_notification.py"
    cp "$REPO_ROOT/skills/pm-skill/deploy.sh" "$repo_dir/skills/pm-skill/deploy.sh"
    cp "$REPO_ROOT/.gitignore" "$repo_dir/.gitignore"
    cp "$REPO_ROOT/.release_ignore" "$repo_dir/.release_ignore"

    cat > "$repo_dir/version.txt" <<'EOF'
v1
EOF
    cat > "$repo_dir/config/sdlc_config.json" <<'EOF'
{"source":"new-config"}
EOF
    cat > "$repo_dir/.sdlc_hooks/pre-commit" <<'EOF'
#!/bin/bash
echo hook-from-source
EOF
    chmod +x "$repo_dir/deploy.sh" "$repo_dir/kit-deploy.sh" "$repo_dir/scripts/rollback.sh" "$repo_dir/scripts/build_release.sh" "$repo_dir/skills/pm-skill/deploy.sh" "$repo_dir/.sdlc_hooks/pre-commit"

    cat > "$repo_dir/skills/pm-skill/SKILL.md" <<'EOF'
# PM Skill Fixture
EOF
    cat > "$repo_dir/skills/pm-skill/STATE.md" <<'EOF'
state=v1
EOF
    cat > "$repo_dir/skills/pm-skill/package.json" <<'EOF'
{"name":"pm-skill-fixture"}
EOF

    (
        cd "$repo_dir"
        git init -q
        git config user.email "test@example.com"
        git config user.name "Test User"
    )
}

seed_existing_runtime() {
    local home_dir="$1"
    local slug="$2"
    local runtime_root="${3:-$home_dir/.openclaw/skills}"

    mkdir -p "$runtime_root/$slug/config"
    cat > "$runtime_root/$slug/version.txt" <<'EOF'
v0
EOF
    cat > "$runtime_root/$slug/config/sdlc_config.json" <<'EOF'
{"preserved":"hot-config"}
EOF
}

setup_github_sync_fixture() {
    local home_dir="$1"
    local sync_log="$2"

    mkdir -p "$home_dir/.openclaw/skills/leio-github-sync/scripts"
    cat > "$home_dir/.openclaw/skills/leio-github-sync/scripts/sync.py" <<EOF
#!/usr/bin/env python3
from pathlib import Path
import sys
Path(r"$sync_log").write_text(" ".join(sys.argv[1:]) + "\n", encoding="utf-8")
EOF
    chmod +x "$home_dir/.openclaw/skills/leio-github-sync/scripts/sync.py"
}

run_deploy_with_home_mock() {
    local repo_dir="$1"
    local home_mock="$2"
    local path_override="$3"
    local log_path="$4"
    shift 4
    (
        cd "$repo_dir"
        HOME="$home_mock" HOME_MOCK="$home_mock" PATH="$path_override" bash ./deploy.sh "$@" > "$log_path" 2>&1
    )
}

run_deploy_with_isolated_home() {
    local repo_dir="$1"
    local home_dir="$2"
    local path_override="$3"
    local log_path="$4"
    shift 4
    (
        cd "$repo_dir"
        env -u HOME_MOCK HOME="$home_dir" PATH="$path_override" bash ./deploy.sh "$@" > "$log_path" 2>&1
    )
}

run_kit_deploy_with_isolated_home() {
    local repo_dir="$1"
    local home_dir="$2"
    local path_override="$3"
    local log_path="$4"
    (
        cd "$repo_dir"
        env -u HOME_MOCK HOME="$home_dir" PATH="$path_override" bash ./kit-deploy.sh > "$log_path" 2>&1
    )
}

run_pm_deploy_with_isolated_home() {
    local repo_dir="$1"
    local home_dir="$2"
    local path_override="$3"
    local log_path="$4"
    (
        cd "$repo_dir"
        env -u HOME_MOCK HOME="$home_dir" PATH="$path_override" bash ./skills/pm-skill/deploy.sh > "$log_path" 2>&1
    )
}

test_deploy_copies_dotfiles_from_dist_into_runtime() {
    echo "--- test_deploy_copies_dotfiles_from_dist_into_runtime ---"
    local case_dir="$TEST_ROOT/dotfiles"
    local home_mock="$case_dir/home"
    local repo_dir="$case_dir/src/dotfile-skill"
    local log_path="$case_dir/deploy.log"

    mkdir -p "$case_dir"
    create_mock_repo "$repo_dir"

    run_deploy_with_home_mock "$repo_dir" "$home_mock" "$BASE_PATH" "$log_path"

    assert_file_exists "$repo_dir/.dist/.sdlc_hooks/pre-commit"
    assert_file_exists "$home_mock/.openclaw/skills/dotfile-skill/.sdlc_hooks/pre-commit"
    assert_files_equal "$repo_dir/.sdlc_hooks/pre-commit" "$home_mock/.openclaw/skills/dotfile-skill/.sdlc_hooks/pre-commit"
    echo "✅ Passed: dotfiles are copied from .dist into runtime."
}

test_deploy_sh_does_not_invoke_gateway_restart() {
    echo "--- test_deploy_sh_does_not_invoke_gateway_restart ---"
    local case_dir="$TEST_ROOT/deploy_no_restart"
    local home_dir="$case_dir/home"
    local repo_dir="$case_dir/src/root-skill"
    local mock_bin="$case_dir/mock_bin"
    local openclaw_log="$case_dir/openclaw.log"
    local gemini_log="$case_dir/gemini.log"
    local deploy_log="$case_dir/deploy.log"

    mkdir -p "$case_dir"
    create_mock_repo "$repo_dir"
    setup_mock_bin "$mock_bin" "$openclaw_log" "$gemini_log" false

    run_deploy_with_isolated_home "$repo_dir" "$home_dir" "$mock_bin:$BASE_PATH" "$deploy_log"

    assert_no_gateway_restart "$openclaw_log"
    echo "✅ Passed: deploy.sh does not invoke gateway restart."
}

test_kit_deploy_sh_does_not_invoke_gateway_restart() {
    echo "--- test_kit_deploy_sh_does_not_invoke_gateway_restart ---"
    local case_dir="$TEST_ROOT/kit_no_restart"
    local home_dir="$case_dir/home"
    local repo_dir="$case_dir/src/kit-skill"
    local mock_bin="$case_dir/mock_bin"
    local openclaw_log="$case_dir/openclaw.log"
    local gemini_log="$case_dir/gemini.log"
    local deploy_log="$case_dir/kit-deploy.log"

    mkdir -p "$case_dir"
    create_mock_repo "$repo_dir"
    setup_mock_bin "$mock_bin" "$openclaw_log" "$gemini_log" false

    run_kit_deploy_with_isolated_home "$repo_dir" "$home_dir" "$mock_bin:$BASE_PATH" "$deploy_log"

    assert_no_gateway_restart "$openclaw_log"
    assert_file_exists "$home_dir/.openclaw/skills/kit-skill/version.txt"
    assert_file_exists "$home_dir/.openclaw/skills/pm-skill/SKILL.md"
    echo "✅ Passed: kit-deploy.sh does not invoke gateway restart."
}

test_pm_skill_deploy_sh_does_not_invoke_gateway_restart() {
    echo "--- test_pm_skill_deploy_sh_does_not_invoke_gateway_restart ---"
    local case_dir="$TEST_ROOT/pm_no_restart"
    local home_dir="$case_dir/home"
    local repo_dir="$case_dir/src/pm-root"
    local mock_bin="$case_dir/mock_bin"
    local openclaw_log="$case_dir/openclaw.log"
    local gemini_log="$case_dir/gemini.log"
    local deploy_log="$case_dir/pm-deploy.log"

    mkdir -p "$case_dir"
    create_mock_repo "$repo_dir"
    setup_mock_bin "$mock_bin" "$openclaw_log" "$gemini_log" false

    run_pm_deploy_with_isolated_home "$repo_dir" "$home_dir" "$mock_bin:$BASE_PATH" "$deploy_log"

    assert_no_gateway_restart "$openclaw_log"
    assert_file_exists "$home_dir/.openclaw/skills/pm-skill/SKILL.md"
    echo "✅ Passed: skills/pm-skill/deploy.sh does not invoke gateway restart."
}

test_deploy_sh_accepts_no_restart_as_compatibility_no_op() {
    echo "--- test_deploy_sh_accepts_no_restart_as_compatibility_no_op ---"
    local case_dir="$TEST_ROOT/no_restart_noop"
    local default_home="$case_dir/default_home"
    local default_repo="$case_dir/src/default-skill"
    local default_mock_bin="$case_dir/default_mock_bin"
    local default_openclaw_log="$case_dir/default_openclaw.log"
    local default_gemini_log="$case_dir/default_gemini.log"
    local default_log="$case_dir/default.log"

    local compat_home="$case_dir/compat_home"
    local compat_repo="$case_dir/src/compat-skill"
    local compat_mock_bin="$case_dir/compat_mock_bin"
    local compat_openclaw_log="$case_dir/compat_openclaw.log"
    local compat_gemini_log="$case_dir/compat_gemini.log"
    local compat_log="$case_dir/compat.log"

    mkdir -p "$case_dir/src"
    create_mock_repo "$default_repo"
    create_mock_repo "$compat_repo"
    setup_mock_bin "$default_mock_bin" "$default_openclaw_log" "$default_gemini_log" false
    setup_mock_bin "$compat_mock_bin" "$compat_openclaw_log" "$compat_gemini_log" false

    run_deploy_with_isolated_home "$default_repo" "$default_home" "$default_mock_bin:$BASE_PATH" "$default_log"
    run_deploy_with_isolated_home "$compat_repo" "$compat_home" "$compat_mock_bin:$BASE_PATH" "$compat_log" --no-restart

    assert_no_gateway_restart "$default_openclaw_log"
    assert_no_gateway_restart "$compat_openclaw_log"
    assert_tree_equal "$default_home/.openclaw/skills/default-skill" "$compat_home/.openclaw/skills/compat-skill"
    echo "✅ Passed: --no-restart remains an accepted compatibility no-op."
}

test_existing_hard_copy_deploy_guarantees_do_not_regress() {
    echo "--- test_existing_hard_copy_deploy_guarantees_do_not_regress ---"

    local case_dir="$TEST_ROOT/non_regression"
    mkdir -p "$case_dir"

    # Backup creation, atomic swap, hot config preservation, and rollback under HOME_MOCK.
    local main_home="$case_dir/main_home"
    local main_repo="$case_dir/src/nonreg-skill"
    local main_log="$case_dir/main_deploy.log"
    create_mock_repo "$main_repo"
    seed_existing_runtime "$main_home" "nonreg-skill"

    run_deploy_with_home_mock "$main_repo" "$main_home" "$BASE_PATH" "$main_log"

    local releases_dir="$main_home/.openclaw/.releases/nonreg-skill"
    local runtime_dir="$main_home/.openclaw/skills/nonreg-skill"
    assert_file_exists "$releases_dir"
    find "$releases_dir" -maxdepth 1 -name 'backup_*.tar.gz' | grep . >/dev/null || fail "Expected deploy backup tarball to be created"
    assert_file_content_equals "$runtime_dir/version.txt" "v1"
    assert_file_content_equals "$runtime_dir/config/sdlc_config.json" '{"preserved":"hot-config"}'
    assert_file_not_exists "$main_home/.openclaw/skills/.tmp_nonreg-skill"
    assert_file_not_exists "$main_home/.openclaw/skills/.old_nonreg-skill"

    (
        cd "$main_repo"
        HOME="$main_home" HOME_MOCK="$main_home" PATH="$BASE_PATH" bash ./scripts/rollback.sh > "$case_dir/rollback.log" 2>&1
    )
    assert_file_content_equals "$runtime_dir/version.txt" "v0"
    assert_file_content_equals "$runtime_dir/config/sdlc_config.json" '{"preserved":"hot-config"}'

    # Gemini link skip behavior under HOME_MOCK.
    local no_gemini_home="$case_dir/no_gemini_home"
    local no_gemini_repo="$case_dir/src/no-gemini-skill"
    local no_gemini_mock_bin="$case_dir/no_gemini_mock_bin"
    local no_gemini_openclaw_log="$case_dir/no_gemini_openclaw.log"
    local no_gemini_gemini_log="$case_dir/no_gemini_gemini.log"
    local no_gemini_deploy_log="$case_dir/no_gemini_deploy.log"
    create_mock_repo "$no_gemini_repo"
    setup_mock_bin "$no_gemini_mock_bin" "$no_gemini_openclaw_log" "$no_gemini_gemini_log" false
    run_deploy_with_home_mock "$no_gemini_repo" "$no_gemini_home" "$no_gemini_mock_bin:$BASE_PATH" "$no_gemini_deploy_log"
    [ ! -s "$no_gemini_gemini_log" ] || fail "Gemini link should be skipped when gemini is absent"

    # Gemini link execute behavior under HOME_MOCK.
    local gemini_home="$case_dir/gemini_home"
    local gemini_repo="$case_dir/src/gemini-skill"
    local gemini_mock_bin="$case_dir/gemini_mock_bin"
    local gemini_openclaw_log="$case_dir/gemini_openclaw.log"
    local gemini_gemini_log="$case_dir/gemini_gemini.log"
    local gemini_deploy_log="$case_dir/gemini_deploy.log"
    create_mock_repo "$gemini_repo"
    setup_mock_bin "$gemini_mock_bin" "$gemini_openclaw_log" "$gemini_gemini_log" true
    run_deploy_with_home_mock "$gemini_repo" "$gemini_home" "$gemini_mock_bin:$BASE_PATH" "$gemini_deploy_log"
    assert_log_contains "$gemini_gemini_log" "gemini skills link $gemini_home/.openclaw/skills/gemini-skill --consent"

    # SDLC_RUNTIME_DIR handling under HOME_MOCK.
    local custom_home="$case_dir/custom_home"
    local custom_repo="$case_dir/src/custom-runtime-skill"
    local custom_runtime="$case_dir/custom_runtime"
    create_mock_repo "$custom_repo"
    (
        cd "$custom_repo"
        HOME="$custom_home" HOME_MOCK="$custom_home" SDLC_RUNTIME_DIR="$custom_runtime" PATH="$BASE_PATH" bash ./deploy.sh > "$case_dir/custom_runtime.log" 2>&1
    )
    assert_file_exists "$custom_runtime/custom-runtime-skill/version.txt"

    # GitHub sync compatibility under isolated HOME (HOME_MOCK would intentionally skip sync).
    local sync_home="$case_dir/sync_home"
    local sync_repo="$case_dir/src/sync-skill"
    local sync_mock_bin="$case_dir/sync_mock_bin"
    local sync_openclaw_log="$case_dir/sync_openclaw.log"
    local sync_gemini_log="$case_dir/sync_gemini.log"
    local sync_deploy_log="$case_dir/sync_deploy.log"
    local sync_log="$case_dir/github_sync.log"
    create_mock_repo "$sync_repo"
    setup_mock_bin "$sync_mock_bin" "$sync_openclaw_log" "$sync_gemini_log" false
    setup_github_sync_fixture "$sync_home" "$sync_log"
    run_deploy_with_isolated_home "$sync_repo" "$sync_home" "$sync_mock_bin:$BASE_PATH" "$sync_deploy_log"
    assert_no_gateway_restart "$sync_openclaw_log"
    assert_log_contains "$sync_log" "--project-dir $sync_repo"

    echo "✅ Passed: existing hard-copy deploy guarantees do not regress."
}

test_deploy_copies_dotfiles_from_dist_into_runtime
test_deploy_sh_does_not_invoke_gateway_restart
test_kit_deploy_sh_does_not_invoke_gateway_restart
test_pm_skill_deploy_sh_does_not_invoke_gateway_restart
test_deploy_sh_accepts_no_restart_as_compatibility_no_op
test_existing_hard_copy_deploy_guarantees_do_not_regress

echo "✅ Hard-Copy Deploy & Rollback Integration Test PASSED"
