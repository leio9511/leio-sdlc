#!/bin/bash
set -e

# Target directory
TARGET_DIR="tests"

# Defensive check: Ensure we are operating from the project root and the target directory exists
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Target directory '$TARGET_DIR' does not exist."
    exit 1
fi

echo "Cleaning up legacy test sandboxes..."

# Safely remove planner sandboxes
if ls "$TARGET_DIR"/planner_sandbox_* 1> /dev/null 2>&1; then
    echo "Removing planner_sandbox directories..."
    rm -rf "$TARGET_DIR"/planner_sandbox_*
else
    echo "No planner_sandbox directories found."
fi

# Safely remove manager sandboxes
if ls "$TARGET_DIR"/manager_sandbox_* 1> /dev/null 2>&1; then
    echo "Removing manager_sandbox directories..."
    rm -rf "$TARGET_DIR"/manager_sandbox_*
else
    echo "No manager_sandbox directories found."
fi

echo "Cleanup complete."
exit 0
