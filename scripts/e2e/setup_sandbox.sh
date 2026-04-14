#!/bin/bash

# setup_sandbox.sh - Centralized fixture for dependency injection into hermetic sandboxes

init_hermetic_sandbox() {
    local target_dir="$1"
    if [ -z "$target_dir" ]; then
        echo "Error: target_dir is required"
        return 1
    fi

    # Anchor to the project root relative to this script
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

    # Create target directory if it doesn't exist
    mkdir -p "$target_dir"

    # Copy required scripts from the root scripts directory into the target directory
    cp "$PROJECT_ROOT/scripts/orchestrator.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/utils_json.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/git_utils.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/llm_utils.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/agent_driver.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/agent_llm.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/config.py" "$target_dir/" 2>/dev/null || true
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
    cp "$PROJECT_ROOT/scripts/commit_state.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/doctor.py" "$target_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/scripts/update_pr_status.py" "$target_dir/" 2>/dev/null || true

    local parent_dir="$(dirname "$target_dir")"
    mkdir -p "$parent_dir/config"
    cp -r "$PROJECT_ROOT/config/"* "$parent_dir/config/" 2>/dev/null || true

    # Provide a simple check to ensure at least orchestrator.py is there
    if [ ! -f "$target_dir/orchestrator.py" ]; then
        echo "Warning: orchestrator.py not found in $PROJECT_ROOT/scripts/"
    fi
}
