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

    # Provide a simple check to ensure at least orchestrator.py is there
    if [ ! -f "$target_dir/orchestrator.py" ]; then
        echo "Warning: orchestrator.py not found in $PROJECT_ROOT/scripts/"
    fi
}
