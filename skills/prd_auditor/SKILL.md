---
name: prd_auditor
description: "Perform a formal architecture quality-gate audit on a PRD. Use after pm-skill produces a PRD and before downstream SDLC execution begins."
---

# PRD Auditor

Use this skill to audit a PRD against the architecture quality-gate standards defined in `references/playbook.md`.

This is a read-only audit. Do not modify any files.

## Input

- PRD file path
- Repository/working directory path (for codebase context per the playbook)

## Execution

1. Read the PRD file provided in context.
2. Inspect the target repository at the provided working directory to understand the current codebase state.
3. Read `references/playbook.md` and follow its audit standards exactly.
4. Output a single JSON verdict:

```json
{
  "reasoning": "<audit reasoning>",
  "status": "APPROVED | REJECTED",
  "comments": "<concise audit opinion for the manager>"
}
```

## Constraints

- Follow `references/playbook.md` exactly. Do not invent new audit rules.
- Output only the JSON verdict. No conversational text before or after.
- Use an isolated sub-agent with high reasoning/thinking level.
