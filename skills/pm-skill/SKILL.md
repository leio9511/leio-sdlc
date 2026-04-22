---
name: pm-skill
version: 1.0.0
description: "Use only when the user explicitly asks to create, write, generate, or refine a PRD / execution-grade engineering brief for downstream audit and SDLC execution."
---

# PM Skill: PRD / Engineering Brief Authoring

## Scope

This skill is for writing or refining an upstream execution brief after the user explicitly requests PRD authoring work.

Its purpose is to convert an already-discussed and sufficiently agreed design direction into a structured document that can be:
1. reviewed by the Auditor, and then
2. executed by the downstream `leio-sdlc` pipeline after explicit human approval.

This skill is not for:
- direct code implementation
- code review
- launching the SDLC pipeline
- bypassing audit or human decision gates

## What this skill produces

The output of this skill is not a lightweight PRD in the narrow sense.

In this workflow, the PRD is an execution-grade engineering brief.

It combines:
- product intent
- architecture and design decisions
- implementation boundaries
- acceptance criteria
- testing strategy
- exact hardcoded strings when precision is required

The downstream assumption is that this PRD / execution brief should be concrete enough for:
- Auditor review
- downstream planning / coding / review / UAT execution

## When to use this skill

Use this skill only when the user explicitly asks to:
- create a PRD
- write a PRD
- generate a PRD
- refine an existing PRD
- turn an agreed design into an execution brief

Do not trigger this skill merely because the discussion appears mature enough.
Do not infer permission to begin PRD authoring from conversational convergence alone.

## Workflow

### Step 1: Get the safe PRD path

Run:

```bash
python3 "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}"/pm-skill/scripts/init_prd.py \
  --project <Target_Project_Name> \
  --title "<Short_Title>" \
  --workdir <Project_Root>
```

Always pass `--workdir <Project_Root>` so the PRD is created in the correct project repository.

### Step 2: Read and fill the scaffold

- Read the generated PRD file
- Use the generated template as the required document structure
- Fill the document from the agreed discussion context
- Preserve the template structure exactly unless the template itself explicitly allows variation

## Use the PRD template as the structure

The generated PRD template is the required structure for this workflow.

When using this skill, you must:
- obtain the correct PRD path through `init_prd.py`
- read the generated template before writing
- fill every required section from the agreed discussion context
- preserve the template structure so the document remains auditable and executable

Do not rewrite the template structure or invent a parallel document format.

## Write for downstream execution

The document should be specific enough that downstream agents can execute without ambiguity.
That means the brief must be coherent as a whole, not just locally complete section by section.

## Downstream contract

The normal lifecycle for the artifact produced by this skill is:

1. co-pilot design discussion reaches an agreed direction
2. this skill synthesizes the execution brief
3. Auditor reviews the brief
4. the user decides whether to proceed
5. `leio-sdlc` executes the approved brief

This skill is therefore an upstream authoring stage in a larger human-agent software delivery protocol.

For the full collaboration lifecycle, read:
- `references/sdlc-lifecycle.md`

## Documentation discipline

### Acceptance Criteria
Use Given / When / Then black-box acceptance criteria.

Do not write granular implementation code or low-level unit test steps in the PRD body unless the template explicitly calls for exact hardcoded content.

### Testing Strategy
Define verification at the macro level:
- what is risky
- what should be mocked
- whether sandbox / E2E / live validation is needed
- what downstream quality signal matters

### Framework Modifications
If the brief authorizes changes to protected SDLC framework files, list them explicitly.

## Auditor gate and anti-YOLO rule

Once the PRD / execution brief is written and saved, the PRD-authoring task is complete.

Then:

1. Trigger the Auditor using the current installed Auditor entrypoint:

```bash
python3 "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}"/leio-sdlc/scripts/spawn_auditor.py \
  --prd-file <Absolute_Path_To_PRD> \
  --workdir <Project_Root> \
  --channel <Channel_String>
```

This is the current installed Auditor entrypoint for the workflow today. If Auditor is later consolidated into `pm-skill`, this invocation path may change.

2. If the Auditor returns `APPROVED`, notify the user and stop
3. If the Auditor returns `REJECTED`, do not auto-correct the PRD

On `REJECTED`, the agent must:
- summarize the rejection clearly
- extract the underlying architectural or product concern
- explain the likely correction direction at a principle level
- present that summary to the user
- stop and wait for explicit human input

Do not enter a loop where the PM mechanically edits one line per Auditor complaint.
Do not let the Auditor become the de facto designer.
Do not continue revising without explicit human approval.

The agent should show understanding of the Auditor’s reasoning, but the human remains the decision-maker for the next revision.

## Baseline rule

After the PRD is approved for use, baseline it using:

```bash
python3 ~/.openclaw/skills/leio-sdlc/scripts/commit_state.py --files <Absolute_Path_To_PRD>
```

Do not use manual `git commit`.
Do not launch SDLC automatically after audit approval unless explicit authorization is given.
