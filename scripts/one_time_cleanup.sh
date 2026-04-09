#!/bin/bash
set -e

# Change to the project root directory
cd /root/.openclaw/workspace/projects/leio-sdlc

echo "Starting cleanup..."

# Strict Guardrail: Protect core architecture files
PROTECTED_FILES=("README.md" "STATE.md" "SKILL.md" "ARCHITECTURE.md")

safe_rm() {
    for arg in "$@"; do
        for protected in "${PROTECTED_FILES[@]}"; do
            if [[ "$arg" == "$protected" || "$arg" == */"$protected" ]]; then
                echo "[FATAL] Guardrail prevented deletion of protected file: $arg"
                exit 1
            fi
        done
    done
    rm "$@"
}

safe_git_rm() {
    for arg in "$@"; do
        for protected in "${PROTECTED_FILES[@]}"; do
            if [[ "$arg" == "$protected" || "$arg" == */"$protected" ]]; then
                echo "[FATAL] Guardrail prevented deletion of protected file: $arg"
                exit 1
            fi
        done
    done
    git rm "$@"
}

# Tracked Ghost Directories
safe_git_rm -rf AMS/ 2>/dev/null || true
safe_git_rm -rf projects/ 2>/dev/null || true

# Untracked Ghost Directories
safe_rm -rf root/ 2>/dev/null || true

# PR Fragments
safe_rm -f content_pr1.md content_pr2.md final_pr_contracts.md pr_001.md pr001_tmp.md pr_002.md pr002_tmp.md pr1_draft.md pr1_temp.md pr2_draft.md pr2_temp.md pr3_temp.md pr4.md pr4_temp.md tmp_pr1_final.md tmp_pr3.md tmp_pr4.md 2>/dev/null || true

# Legacy Logs/Reports
safe_rm -f Architectural_Audit_Report_v5.md independent_audit_report.md native_audit_report.md polyrepo_audit_report.md polyrepo_v4_audit_report.md polyrepo_v5_audit_report.md polyrepo_v6_audit_report.md polyrepo_v7_audit_report.md arbitration_report.txt audit_prompt.txt audit_verdict.json dummy_chat_context_074.txt polyrepo_plan.md 2>/dev/null || true

# One-off Scripts
safe_rm -f debug_orchestrator.py hello.py patch_guardrails.sh patch_test_branch_isolation.sh rollback.sh run_independent_audit.sh server.py spawn_native_auditor.sh 2>/dev/null || true
safe_git_rm -f debug_orchestrator.py hello.py patch_guardrails.sh patch_test_branch_isolation.sh rollback.sh run_independent_audit.sh server.py spawn_native_auditor.sh 2>/dev/null || true

echo "Cleanup complete."
