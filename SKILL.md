---
name: leio-sdlc
version: 1.0.0
description: "Use when an audit-approved execution brief in the required project format is ready to be started, resumed, or withdrawn through the `leio-sdlc` orchestrator, a PRD-driven multi-agent SDLC workflow for planning, coding, review, and UAT. This skill is for downstream pipeline control only, not for PRD authoring or coder/reviewer/verifier/planner role behavior."
---

# leio-sdlc Orchestrator Launch Skill

## Scope

This skill is only for controlling the downstream `leio-sdlc` pipeline from the primary-agent side.

Use it to:
- start a new SDLC run
- resume an interrupted SDLC run
- withdraw or quarantine an SDLC run

Do not use this skill as behavior guidance for:
- coder
- reviewer
- verifier
- planner
- other execution-side sub-agents

This skill is a pipeline-control skill, not a universal SDLC constitution.

## What `leio-sdlc` is

`leio-sdlc` is a PRD-driven multi-agent SDLC orchestrator.

It executes an approved PRD / execution brief through a workflow that may include:
- planning / slicing
- coding
- review
- merge
- UAT verification
- recovery / resume / withdrawal when needed

This skill only governs how to launch and control that orchestrator.

## Preconditions

Before using this skill, all of the following should already be true:

1. A PRD / execution brief already exists on disk.
2. The document is in the required project format.
3. The document has passed Auditor review.
4. Explicit human authorization to execute has been given.

If these conditions are not met, do not launch SDLC yet.

## Relationship to the upstream lifecycle

This skill is part of a larger human-agent software delivery protocol.

The expected upstream flow is:

1. co-pilot design discussion
2. PRD / execution-brief synthesis through `pm-skill`
3. Auditor review
4. explicit human approval to execute
5. `leio-sdlc` launch and downstream automation

This skill therefore assumes that the upstream authoring and audit gates have already been satisfied.

It is not a general “run any PRD” tool.  
It is a downstream execution-control skill for approved PRD / execution briefs.

For the full collaboration lifecycle, read:
- `references/sdlc-lifecycle.md`

If the execution brief has not yet passed Auditor review, return to the upstream PM workflow before launching SDLC execution.
This skill must not be used to bypass the audit gate.

## When to use this skill

Use this skill when:
- an approved execution brief is ready to enter SDLC execution
- an interrupted SDLC run must be resumed
- an existing SDLC run must be withdrawn or quarantined

If the user is asking about:
- internal architecture
- state machine behavior
- recovery logic
- governance semantics

read the architecture references before answering.

## Invocation

If you are unsure about the available parameters, inspect the installed entrypoint first:

```bash
python3 "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}"/leio-sdlc/scripts/orchestrator.py --help
```

The pipeline is launched through `scripts/orchestrator.py`.

Note: the shell command examples in this skill describe the orchestrator command shape only.
Actual launch semantics must follow the platform-specific lifecycle rules in `## Execution rule`.

## Intent-to-command mapping

- If the user asks to start SDLC execution, launch `scripts/orchestrator.py` in normal-start mode.
- If the user asks to continue or resume an interrupted run, add `--resume`.
- If the user asks to withdraw, cancel, rollback, or quarantine the current run, add `--withdraw`.
- If the user explicitly specifies an execution engine, append `--engine <value>`.
- If the user explicitly specifies a model, append `--model <value>`.

### Normal start

```bash
python3 "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}"/leio-sdlc/scripts/orchestrator.py \
  --prd-file <path> \
  --workdir <path> \
  --force-replan true
```

### Resume

```bash
python3 "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}"/leio-sdlc/scripts/orchestrator.py \
  --prd-file <path> \
  --workdir <path> \
  --resume \
  --force-replan false
```

### Withdraw

```bash
python3 "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}"/leio-sdlc/scripts/orchestrator.py \
  --prd-file <path> \
  --workdir <path> \
  --withdraw
```

## Execution rule

The `leio-sdlc` orchestrator is a long-running control-plane process.

Launch invariant (platform-agnostic):
- Start it through the host platform's native background-process mechanism.
- Its lifecycle must remain observable and controllable by the host platform.
- It must not inherit a finite default process timeout that can kill the run mid-flight.
- If the host platform applies a default exec/process timeout, that timeout must be explicitly disabled or overridden for this launch.
- Do not replace the host platform lifecycle mechanism with `nohup`, manual `&`, or improvised daemon loops.

OpenClaw mapping:
- When launching through OpenClaw's `exec` tool, use:
  - `background: true`
  - `timeout: 0`

Why this matters:
- `leio-sdlc` runs may legitimately last for hours across planner / coder / reviewer / UAT cycles.
- A host-level default timeout can terminate the orchestrator in the middle of a valid run and leave the workflow in a partial state.
- Therefore, long-running `leio-sdlc` launches must always use a host execution path that preserves lifecycle tracking without imposing a finite default process timeout.

## After launch

When the orchestrator completes, inspect the completion output.

If the output contains:

```text
[ACTION REQUIRED FOR MANAGER]
```

follow that instruction before ending your turn.

Do not silently ignore manager handoff instructions.

## What this skill does NOT define

This skill does not:
- create or refine the execution brief
- replace the Auditor gate
- replace the human approval gate
- define coder sub-agent behavior
- define reviewer sub-agent behavior
- define verifier sub-agent behavior
- define planner internals
- authorize execution on its own

Those concerns belong to:
- upstream PRD authoring skills
- Auditor
- explicit human decisions
- role-specific prompts, playbooks, and references

## References

Read these only when needed:

- `ARCHITECTURE.md`
  - for SDLC state machine / recovery explanations

- `projects/docs/TEMPLATES/organization_governance.md`
  - for governance and human-in-the-loop clarification

- `references/sdlc-lifecycle.md`
  - for the full upstream/downstream human + agent collaboration lifecycle

- `playbooks/`
  - for role-specific downstream implementation behavior inside the project

## Design boundary

This skill should remain:
- small
- low-blast-radius
- orchestrator-control-only
- safe even if loaded in a context where coding/review work is happening

It should not become:
- a universal SDLC constitution
- a global role override
- a substitute for coder/reviewer/verifier playbooks
- a substitute for PM authoring or Auditor approval
