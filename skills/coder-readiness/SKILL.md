---
name: coder-readiness
description: "Run a read-only coder-readiness review before implementation starts. Use when a PRD or execution brief may be ambiguous or execution-critical and you want a cautious coder-style pass over the target repository to produce blocking and non-blocking clarify questions without writing code or modifying files."
---

# Coder Readiness

Use this skill when the user wants a pre-implementation readiness check from a coder perspective.

This is a read-only review pattern.

The goal is to answer one question:
- Is this PRD clear enough that a coder can begin implementation in the target repository without first asking clarification questions?

## What this check does

The check should:
- inspect the target PRD / execution brief
- inspect the target repository structure, scripts, workflows, and likely implementation surfaces when repository context is available
- identify missing decisions, hidden assumptions, or repo/PRD mismatches
- output only clarification questions, split into blocking vs non-blocking

## Hard constraints

The reviewer must be strictly read-only:
- do not modify any files
- do not write code
- do not propose patches
- do not broaden scope
- do not begin implementation

## Recommended execution pattern

Use a dedicated isolated reviewer (for example, a sub-agent) or equivalent focused review context for this check when possible.

Recommended settings when the host supports them:
- reasoning / thinking: high
- permissions: read-only analysis only
- session working directory: outside the target repository, to avoid writing agent workspace/context files into the repository
- repository context: target repository root

## Recommended output format

Return only:
1. Blocking clarify questions
2. Non-blocking clarify questions
3. Explicit statement if there are no blocking questions
4. Concise practical wording

## Reusable prompt template

Use this template for the read-only review:

```text
Perform a strictly read-only coder-readiness review for <PRD_PATH> against the target repository.

Run the review from outside the target repository when possible. Treat the target repository as an explicit path to inspect, not necessarily as the session working directory.

Goal:
Assess whether the PRD is sufficiently clear for a coder to begin implementation.

Hard constraints:
- READ ONLY. Do not modify any files.
- Do not write code.
- Do not propose patches.
- Do not broaden scope.
- Inspect repository files/workflows/scripts as needed when repository context is available.

Output format:
1. Blocking clarify questions (only if truly required before implementation)
2. Non-blocking clarify questions
3. Explicitly state if there are no blocking questions
4. Keep it concise and practical

Review focus:
- Internal consistency of the PRD
- Whether implementation surfaces are inferable enough
- Whether any key decisions are still missing
- Whether the current repo creates ambiguity against the PRD
- Surface hidden assumptions as questions only if needed

You are acting like a cautious coder about to start implementation.
```

## When to use this skill

Use it when:
- a PRD is newly drafted or heavily revised
- the change is infrastructure-heavy or execution-contract-heavy
- the repo is old/complex and likely to diverge from the PRD
- you want to catch coder-facing ambiguity before launching real implementation

## When not to use this skill

Do not use it when:
- the user already wants direct implementation and there is no sign of ambiguity
- an auditor review alone is sufficient
- the task is trivial and no repository/PRD mismatch risk exists

## Notes

This skill is best treated as an independent pre-execution check, not part of auditor core logic.

If blocking questions are found, resolve them before launching coder.

If no blocking questions are found, treat that as an implementation-readiness signal and proceed with the normal flow.
