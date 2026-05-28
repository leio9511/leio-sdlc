#!/bin/bash

# setup_sandbox.sh - Centralized fixture for dependency injection into hermetic sandboxes
#
# Canonical public entrypoints for Bash / mocked E2E tests:
#   init_hermetic_sandbox "$sandbox/scripts"
#   init_git_test_sandbox "$sandbox/repo" [--baseline-commit]
#
# init_git_test_sandbox is the shared clean-runner-safe bootstrap for temporary
# git repos that need commit capability. It only initializes git and repo-local
# identity (plus an optional explicit empty baseline commit); it does not run
# doctor.py --fix or create PRDs, jobs, mocked state, or other business files.

_sandbox_project_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

_sandbox_has_git_repo() {
    local target_dir="$1"
    local resolved_target
    local resolved_top

    resolved_target="$(cd "$target_dir" && pwd -P)" || return 1
    resolved_top="$(git -C "$target_dir" rev-parse --show-toplevel 2>/dev/null)" || return 1
    [ "$resolved_target" = "$resolved_top" ]
}

_sandbox_has_commits() {
    local target_dir="$1"
    git -C "$target_dir" rev-parse --verify HEAD >/dev/null 2>&1
}

init_git_test_sandbox() {
    local target_dir="$1"
    shift || true

    local create_baseline_commit=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --baseline-commit)
                create_baseline_commit=1
                ;;
            *)
                echo "Error: unknown init_git_test_sandbox option: $1"
                return 1
                ;;
        esac
        shift
    done

    if [ -z "$target_dir" ]; then
        echo "Error: target_dir is required"
        return 1
    fi

    mkdir -p "$target_dir"

    if ! _sandbox_has_git_repo "$target_dir"; then
        git -C "$target_dir" init -b master >/dev/null 2>&1
    fi

    git -C "$target_dir" config --local user.name "SDLC Test Sandbox"
    git -C "$target_dir" config --local user.email "sdlc-test-sandbox@example.invalid"

    if [ "$create_baseline_commit" -eq 1 ]; then
        if _sandbox_has_commits "$target_dir"; then
            return 0
        fi

        if [ -n "$(git -C "$target_dir" status --porcelain --untracked-files=no)" ]; then
            echo "Error: --baseline-commit requires a clean index in $target_dir"
            return 1
        fi

        git -C "$target_dir" commit --allow-empty -m "init" >/dev/null 2>&1
    fi
}

init_hermetic_sandbox() {
    local target_dir="$1"
    if [ -z "$target_dir" ]; then
        echo "Error: target_dir is required"
        return 1
    fi

    # Anchor to the project root relative to this script
    PROJECT_ROOT="$(_sandbox_project_root)"

    # Create target directory if it doesn't exist
    mkdir -p "$target_dir"

    # Copy required scripts from the root scripts directory into the target directory
    cp "$PROJECT_ROOT/scripts/utils_path.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/orchestrator.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/runtime_git_identity.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/runtime_launch_guard.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/utils_json.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/git_utils.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/llm_utils.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/agent_driver.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/agent_llm.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/config.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/engine_registry.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/utils_notification.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/notification_formatter.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/handoff_prompter.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/setup_logging.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/spawn_planner.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/spawn_coder.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/spawn_reviewer.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/spawn_arbitrator.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/spawn_auditor.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/spawn_verifier.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/merge_code.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/get_next_pr.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/structured_state_parser.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/commit_state.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/doctor.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/update_pr_status.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/utils_api_key.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/resume_state.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/lock_utils.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/planner_envelope.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/envelope_assembler.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/thinking_resolver.py" "$target_dir/" 2>/dev/null || true

    # Expose the repository-controlled Python entrypoint for mocked E2E sandboxes.
    # This wrapper intentionally delegates back to the source repository script so
    # downstream harnesses bind to the repo .venv contract instead of the sandbox
    # directory, ambient python, bare pytest, or manual virtualenv activation.
    cat >"$target_dir/dev_python.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

exec "$PROJECT_ROOT/scripts/dev_python.sh" "\$@"
EOF
    chmod +x "$target_dir/dev_python.sh"

    local parent_dir="$(dirname "$target_dir")"
    mkdir -p "$parent_dir/config"
    cp -r "$PROJECT_ROOT/config/"* "$parent_dir/config/" 2>/dev/null || true

    # Provide a simple check to ensure at least orchestrator.py is there
    if [ ! -f "$target_dir/orchestrator.py" ]; then
        echo "Warning: orchestrator.py not found in $PROJECT_ROOT/scripts/"
    fi
}
