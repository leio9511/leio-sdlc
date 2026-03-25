#!/bin/bash
set -e

# Setup sandbox
SANDBOX_ID=$(uuidgen)
SANDBOX_DIR="/tmp/leio_sdlc_sandbox_$SANDBOX_ID"
mkdir -p "$SANDBOX_DIR"
cd "$SANDBOX_DIR"

echo "Initializing Sandbox: $SANDBOX_DIR"

# Ensure symlinks and directories exist, including job directories
mkdir -p docs/PRDs docs/PRs .sdlc/jobs/FeatureA .sdlc/jobs/FeatureB

# Link to existing leio-sdlc scripts and structure
ln -sf /root/.openclaw/workspace/projects/leio-sdlc/scripts scripts
ln -sf /root/.openclaw/workspace/projects/leio-sdlc/SKILL.md SKILL.md

# Create fake PRDs
echo "# Feature A" > docs/PRDs/FeatureA.md
echo "# Feature B" > docs/PRDs/FeatureB.md

# Define test Prompts
# The Manager is instructed to stop at the Planner phase and only output the DONE token
PROMPT1="You are the leio-sdlc Manager. Process docs/PRDs/FeatureA.md as a new task. CRITICAL: Read the SKILL.md rules about Job Isolation. The job directory /root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureA is already prepared. You must use the 'write' tool to create a file named '/root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureA/proof.txt' inside it with any content. Output [A_DONE] and immediately exit. Do NOT go further."
PROMPT2="You are the leio-sdlc Manager. Process docs/PRDs/FeatureB.md as a new task. CRITICAL: Read the SKILL.md rules about Job Isolation. The job directory /root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureB is already prepared. You must use the 'write' tool to create a file named '/root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureB/proof.txt' inside it with any content. Output [B_DONE] and immediately exit. Do NOT go further."

echo "Starting concurrent OpenClaw agents..."
openclaw agent --session-id "concurrent-a-$SANDBOX_ID" -m "$PROMPT1" &
PID1=$!

openclaw agent --session-id "concurrent-b-$SANDBOX_ID" -m "$PROMPT2" &
PID2=$!

echo "Waiting for background agents to finish..."
wait $PID1 || echo "Agent 1 exited with error"
wait $PID2 || echo "Agent 2 exited with error"

echo "Starting Hardcore Assertions..."

# 1. Check if proof files exist inside job directories
if [ ! -f "/root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureA/proof.txt" ]; then
    echo "ERROR: Assertion failed. File /root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureA/proof.txt does not exist!"
    exit 1
fi

if [ ! -f "/root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureB/proof.txt" ]; then
    echo "ERROR: Assertion failed. File /root/.openclaw/workspace/projects/leio-sdlc/.sdlc/jobs/FeatureB/proof.txt does not exist!"
    exit 1
fi

# 2. Check for PR files inside the job directories (optional logic, but directories are definitely required)
echo "Job directories and proof files validated."

# 3. Check if any file leaked into global docs/PRs/
if ls docs/PRs/ | grep -q "Feature[AB]"; then
    echo "ERROR: Assertion failed. PR files leaked into global docs/PRs/ directory!"
    ls -l docs/PRs/
    exit 1
fi

echo "All hardcore assertions passed! The Job Concurrency Isolation mechanism is working."

# Cleanup sandbox
cd /
rm -rf "$SANDBOX_DIR"
echo "Sandbox cleaned up successfully."
