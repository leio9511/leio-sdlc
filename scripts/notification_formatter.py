def format_notification(event_type: str, context: dict) -> str:
    prd_id = context.get('prd_id', 'unknown')
    pr_id = context.get('pr_id', 'unknown')
    
    # Optional prefix extracted from PRD filename, assuming format "PRD_123_Name.md"
    prd_match = prd_id
    if prd_id.lower().startswith("prd"):
        parts = prd_id.split('_')
        if len(parts) >= 2:
            prd_match = f"prd-{parts[1]}"
            
    import re
    pr_match = pr_id
    # Extract PR prefix (case-insensitive) followed by underscores and digits/underscores
    match = re.search(r'^(?i:pr_)([\d_]+)', pr_id)
    if match:
        # Align regex comment with PRD-1063 for clarity
        extracted = match.group(1).rstrip('_')
        pr_match = f"pr-{extracted.replace('_', '-')}"

    prd_file = context.get('prd_file', 'unknown')

    # ISSUE-1166 Contract Strings
    if event_type == "sdlc_handshake":
        return f"🤝 [SDLC Engine] Initial Handshake successful. Channel linked."
    elif event_type == "auditor_start":
        cmd = context.get('command')
        if cmd:
            return f"🚀 [Auditor] Starting PRD audit for: {prd_file}\n💻 Command: `{cmd}`"
        else:
            return f"🚀 [Auditor] Starting PRD audit for: {prd_file}"
    elif event_type == "slicing_start":
        return f"🔪 [Planner] Slicing PRD into Micro-PRs..."
    elif event_type == "slicing_end":
        count = context.get('count', 0)
        return f"✅ [Planner] Slicing complete. {count} PRs generated."
    elif event_type == "coder_spawned":
        return f"💻 [Coder] Implementing {pr_match}..."
    elif event_type == "reviewer_spawned":
        return f"🔍 [Reviewer] Auditing changes for {pr_match}..."
    elif event_type == "pr_merged":
        return f"✅ [Merge] {pr_match} merged to master."
    elif event_type == "uat_start":
        return f"🧪 [UAT] Starting final verification..."

    # Legacy strings maintained for backward compatibility tests
    elif event_type == "sdlc_resume":
        cmd = context.get("command", "unknown")
        return f"🚀 1. [{prd_match}] SDLC 恢复执行\n💻 Command: `{cmd}`"
    elif event_type == "sdlc_start":
        cmd = context.get("command", "unknown")
        return f"🚀 1. [{prd_match}] SDLC 启动\n💻 Command: `{cmd}`"
    elif event_type == "pr_switch":
        branch = context.get('branch', 'unknown')
        return f"🔄 [{pr_match}] 切换分支：{branch}"
    elif event_type == "coder_start":
        return f"💻 [Coder] Implementing {pr_match}..."
    elif event_type == "review_start":
        return f"🔍 [Reviewer] Auditing changes for {pr_match}..."
    elif event_type == "review_result":
        result = context.get('result', 'N/A')
        return f"📝 6. [{pr_match}] Review 结果：{result}"
    elif event_type == "all_done":
        return f"🎉 [{prd_match}] SDLC 完成：所有 PR 执行完毕"
    elif event_type == "dead_end":
        return f"🛑 [{pr_match}] PR 需要人工介入"
    elif event_type == "review_rejected":
        summary = context.get('summary', 'No reason provided')
        return f"❌ Reviewer rejected changes. Reason: {summary}. Retrying..."
    elif event_type == "github_sync_start":
        return f"Synchronizing code to GitHub..."
    elif event_type == "github_sync_complete":
        return f"GitHub sync complete."
    elif event_type == "github_sync_failed":
        err = context.get('error', 'unknown error')
        return f"⚠️ GitHub sync failed: {err}"
    elif event_type == "auditor_approved":
        return f"✅ [Auditor] PRD 审查通过 (APPROVED)。"
    elif event_type == "auditor_rejected":
        return f"❌ [Auditor] PRD 审查未通过 (REJECTED)，请根据反馈进行修改并重试。"
    elif event_type == "uat_complete":
        status = context.get('status', 'UNKNOWN')
        if status == "PASS":
            return f"🎉 [{prd_match}] UAT Verification: Passed."
        else:
            return f"⚠️ [{prd_match}] UAT Verification: Missed (Needs Fix)."
    elif event_type == "uat_error":
        return f"❌ [{prd_match}] UAT Verification Error: 测试报告解析失败或发生异常。"
    

    # Pipeline visibility for new event types
    elif event_type == "coder_timeout":
        return f"⏰ [Coder] Coder execution timed out for {pr_match}."
    elif event_type == "coder_failed":
        return f"❌ [Coder] Coder execution failed for {pr_match}."
    elif event_type == "coder_workspace_dirty":
        return f"⚠️ [Coder] Coder left an unexpected workspace state for {pr_match}."
    elif event_type == "coder_no_output":
        return f"⚠️ [Coder] Coder produced no effective output for {pr_match}."
    elif event_type == "reviewer_failed":
        return f"🚨 [Reviewer] Pipeline failure for {pr_match}."
    elif event_type == "reviewer_placeholder_stuck":
        return f"🚨 [Reviewer] Assessment stuck in placeholder for {pr_match}."
    elif event_type == "reviewer_unknown_verdict":
        return f"🚨 [Reviewer] Unknown assessment verdict for {pr_match}."
    elif event_type == "reviewer_invalid_json":
        return f"🚨 [Reviewer] Invalid JSON response for {pr_match}."
    elif event_type == "reviewer_no_output":
        return f"🚨 [Reviewer] No output produced for {pr_match}."
    elif event_type == "planner_split_start":
        return f"🔄 [Planner] PR {pr_match} failed repeatedly. Starting planner split recovery."
    elif event_type == "planner_split_complete":
        return f"✅ [Planner] Successfully split {pr_match} into smaller slices."
    elif event_type == "planner_split_failed":
        return f"❌ [Planner] Split recovery failed for {pr_match}."
    elif event_type == "uat_recovery_plan_start":
        return f"🔄 [UAT] Triggered recovery replanning based on findings for {prd_match}."
    elif event_type == "uat_recovery_exhausted":
        return f"🚨 [UAT] 补救次数已达上限。自动恢复流已熔断，现场已冻结，请人工介入处理。({prd_match})"
    elif event_type == "uat_blocked":
        return f"🚨 [UAT] Findings non-actionable or need human judgment. 自动恢复已阻塞。({prd_match})"
    
    elif event_type == "preflight_failed":
        attempt = context.get('attempt', '?')
        limit = context.get('limit', '?')
        return f"❌ [Preflight] Failed for {pr_match} (attempt {attempt}/{limit}). Retrying Coder..."
    
    return f"🤖 [SDLC Engine] 未知事件: {event_type}"
