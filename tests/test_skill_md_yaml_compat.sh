#!/bin/bash
set -e

# test_skill_md_yaml_compat.sh - Verify SKILL.md files have correct YAML frontmatter for dual compatibility

check_file() {
    local file=$1
    echo "Checking $file..."
    
    if [ ! -f "$file" ]; then
        echo "❌ Error: $file not found!"
        exit 1
    fi
    
    # Check if first line is exactly "---"
    local first_line=$(head -n 1 "$file")
    if [ "$first_line" != "---" ]; then
        echo "❌ Error: $file does not start with '---'. Found: '$first_line'"
        exit 1
    fi
    
    # Check if description field exists in the first 20 lines (frontmatter block)
    if ! head -n 20 "$file" | grep -q "^description:"; then
        echo "❌ Error: $file does not contain 'description:' in the frontmatter."
        exit 1
    fi
    
    echo "✅ $file passed checks."
}

REPO_ROOT="/root/.openclaw/workspace/projects/leio-sdlc"

check_file "$REPO_ROOT/SKILL.md"
check_file "$REPO_ROOT/skills/pm-skill/SKILL.md"

echo "🎉 All SKILL.md files are compatible."
