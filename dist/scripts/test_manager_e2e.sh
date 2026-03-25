#!/bin/bash
set -e

# test_manager_e2e.sh - Manager Full Lifecycle E2E Test
# Created for ISSUE-024

# Go to project root (assuming script is run from project root, or we can force it)
# We will use the current directory as project root as per instructions
PROJECT_ROOT="$(pwd)"

# 1. 创建隔离沙盒
sandbox_id="$(uuidgen)"
sandbox_dir="tests/e2e_sandbox_${sandbox_id}"

mkdir -p "$sandbox_dir"
cd "$sandbox_dir"

# Initialize git
git init
git config user.name "E2E Test"
git config user.email "e2e@example.com"
git commit --allow-empty -m "init"

# 2. 挂载依赖（软链接）
ln -s ../../scripts scripts
ln -s ../../playbooks playbooks
ln -s ../../docs docs
ln -s ../../TEMPLATES TEMPLATES

mkdir -p docs/PRDs
cat << 'EOF' > docs/PRDs/dummy_prd.md
# PRD: Hello World
Implement a hello world script.
EOF

# 3. 注入超长 Prompt 并启动分身
MANAGER_PROMPT="You are the leio-sdlc Manager. A PRD exists at \`docs/PRDs/dummy_prd.md\`. Execute the full pipeline (Plan -> Code -> Review -> Merge). You MUST use the exact python scripts in the scripts/ folder. You must ensure that the Planner creates PR contracts in .sdlc/jobs/dummy_prd/, the Coder writes hello.py and commits it, and the Reviewer writes a Review_Report.md in .sdlc/jobs/dummy_prd/. Do not stop until all these physical artifacts are generated."

unset SDLC_TEST_MODE

echo "Starting Manager E2E Test in sandbox: $sandbox_dir"
openclaw agent --session-id "e2e-manager-${sandbox_id}" -m "$MANAGER_PROMPT" > manager_e2e.log 2>&1

# 4. 终极断言
echo "Running assertions..."

if [ -z "$(ls .sdlc/jobs/dummy_prd/PR_*.md 2>/dev/null)" ]; then echo "Assertion failed: Planner PR contract not found."; exit 1; fi

if [ ! -f hello.py ]; then
    echo "Assertion failed: hello.py not found."
    cat manager_e2e.log
    exit 1
fi

if ! grep -q "print" hello.py; then
    echo "Assertion failed: 'print' not found in hello.py."
    cat manager_e2e.log
    exit 1
fi

if git log -1 --oneline | grep -q "init"; then echo "Assertion failed: Coder did not create a new git commit."; exit 1; fi
if [ ! -f .sdlc/jobs/dummy_prd/Review_Report.md ]; then echo "Assertion failed: Review_Report.md not found."; exit 1; fi
if ! grep -q "APPROVED" .sdlc/jobs/dummy_prd/Review_Report.md; then echo "Assertion failed: Review_Report.md does not contain [LGTM]."; exit 1; fi

echo "All assertions passed. [E2E_MANAGER_SUCCESS]"

# 5. 清理工作
cd "${PROJECT_ROOT}"
rm -rf "$sandbox_dir"

echo "Sandbox cleaned up successfully."
exit 0
