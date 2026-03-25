#!/bin/bash
set -e

# test_e2e_yellow_path.sh - Manager E2E Test for Yellow Path (Review-Correction loop)
# Created for ISSUE-025

PROJECT_ROOT="$(pwd)"

# 1. 创建隔离沙盒
sandbox_id="$(uuidgen)"
sandbox_dir="tests/e2e_sandbox_yellow_${sandbox_id}"

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

# Pre-create a stub PR so Manager skips Planner
mkdir -p .sdlc/jobs/dummy_prd
cat << 'EOF' > .sdlc/jobs/dummy_prd/PR_001_Stub.md
# PR: 001_Stub
Implement hello.py
EOF

# Create an initial hello.py so Coder has something to work on (or Coder might just create it, but let's give an initial one if needed, prompt says: "提供一个初始的 hello.py")
cat << 'EOF' > hello.py
print("Hello World")
EOF
git add hello.py
git commit -m "feat: init hello.py"

# 3. 生成 Mock Reviewer
rm -f scripts/spawn_reviewer.py # remove the symlinked one if it points to a directory structure that allowed it, but scripts is a symlink to the dir.
# Wait, if `scripts` is a symlink to `../../scripts`, doing `rm scripts/spawn_reviewer.py` will delete the REAL file in the project! 
# We MUST NOT do that. We should delete the `scripts` symlink and copy the real scripts dir, or just write a fake script somewhere else.
# But the prompt says: "在沙盒内用 cat 生成一个 scripts/spawn_reviewer.py（覆盖软链接或者删除软链接后重新生成）".
# If I delete the symlink `scripts`, I have to recreate it as a real directory.
rm scripts
mkdir scripts
cp -r ../../scripts/* scripts/

cat << 'EOF' > scripts/spawn_reviewer.py
#!/usr/bin/env python3
import argparse
import os
parser = argparse.ArgumentParser()
parser.add_argument("--job-dir", default=".")
args, _ = parser.parse_known_args()

count = 0
if os.path.exists(".review_count"):
    with open(".review_count", "r") as f:
        count = int(f.read().strip())

report_path = os.path.join(args.job_dir, "Review_Report.md")
if count < 2:
    with open(report_path, "w") as f:
        f.write("[ACTION_REQUIRED]\nPlease add a docstring to hello.py")
else:
    with open(report_path, "w") as f:
        f.write("[LGTM]\nGood job.")

with open(".review_count", "w") as f:
    f.write(str(count + 1))
EOF
chmod +x scripts/spawn_reviewer.py

# 4. 注入超长 Prompt 并启动分身
MANAGER_PROMPT="You are the leio-sdlc Manager executing a System Test. A PRD exists at \`docs/PRDs/dummy_prd.md\` and its PR contract is already in \`.sdlc/jobs/dummy_prd/PR_001_Stub.md\`. I have provided an initial \`hello.py\`. Begin immediately at the Review phase. You MUST execute the reviewer script. If you encounter an [ACTION_REQUIRED], you MUST follow the SKILL.md rules and call Command Template 2b: run \`spawn_coder.py --workdir . --feedback-file .sdlc/jobs/dummy_prd/Review_Report.md\` to fix the code, then run \`spawn_reviewer.py --workdir .\` again. The max revisions is MAX_REVISIONS=3. Continue until you get [LGTM] and then perform Merge."

unset SDLC_TEST_MODE

echo "Starting Manager Yellow Path E2E Test in sandbox: $sandbox_dir"
openclaw agent --session-id "e2e-yellow-${sandbox_id}" -m "$MANAGER_PROMPT" > manager_e2e.log 2>&1

# 5. 断言
echo "Running assertions..."

if [ ! -f .review_count ]; then
    echo "Assertion failed: .review_count not found."
    cat manager_e2e.log
    exit 1
fi

COUNT=$(cat .review_count)
if [ "$COUNT" -ne 3 ]; then
    echo "Assertion failed: .review_count is $COUNT, expected 3."
    cat manager_e2e.log
    exit 1
fi

if ! grep -q "spawn_coder.py --workdir . --feedback-file" manager_e2e.log; then
    echo "Assertion failed: manager_e2e.log does not contain 'spawn_coder.py --workdir . --feedback-file'."
    cat manager_e2e.log
    exit 1
fi

echo "All assertions passed. [E2E_YELLOW_PATH_SUCCESS]"

# 6. 清理工作
cd "${PROJECT_ROOT}"
rm -rf "$sandbox_dir"

echo "Sandbox cleaned up successfully."
exit 0
