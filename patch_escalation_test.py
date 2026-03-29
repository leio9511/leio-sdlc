import re

with open("scripts/test_escalation_clean.sh", "r") as f:
    content = f.read()

# Replace the old directory creation and PR placement
old_setup = """mkdir -p docs/PRs/dummy_prd scripts
cp "${PROJECT_ROOT}/scripts/orchestrator.py" scripts/
cp "${PROJECT_ROOT}/scripts/get_next_pr.py" scripts/
cp "${PROJECT_ROOT}/scripts/git_utils.py" scripts/
cp "${PROJECT_ROOT}/scripts/handoff_prompter.py" scripts/
cp "${PROJECT_ROOT}/scripts/notification_formatter.py" scripts/

echo ".sdlc_run.lock" > .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "*.log" >> .gitignore
git add .gitignore scripts docs
git commit -m "setup" > /dev/null 2>&1

cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_001_Test.md
status: open
slice_depth: 0
INNER_EOF"""

new_setup = """export SDLC_GLOBAL_RUN_BASE="$(pwd)/.sdlc_runs"
mkdir -p "$SDLC_GLOBAL_RUN_BASE/dummy_prd" scripts
cp "${PROJECT_ROOT}/scripts/"*.py scripts/

echo ".sdlc_run.lock" > .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "*.log" >> .gitignore
git add .gitignore scripts
git commit -m "setup" > /dev/null 2>&1

cat << 'INNER_EOF' > "$SDLC_GLOBAL_RUN_BASE/dummy_prd/PR_001_Test.md"
status: open
slice_depth: 0
INNER_EOF"""

content = content.replace(old_setup, new_setup)

# Also update the orchestrator call to use the env var
content = content.replace(
    'export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"',
    'export SDLC_GLOBAL_RUN_BASE="$(pwd)/.sdlc_runs"\nexport PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"'
)


with open("scripts/test_escalation_clean.sh", "w") as f:
    f.write(content)

print("Patched test_escalation_clean.sh")
