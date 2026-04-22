# SDLC Lifecycle: Human + Agent Collaboration Protocol

## Purpose

This document defines the intended collaboration lifecycle between:
- the human decision-maker
- the primary agent
- `pm-skill`
- Auditor
- `leio-sdlc`

It exists to clarify upstream/downstream contracts without forcing every skill to duplicate the entire lifecycle in its top-level `SKILL.md`.

## Lifecycle Overview

### 1. Co-pilot design
The human and the primary agent discuss:
- product goals
- architecture
- constraints
- risks
- technical details

This is an exploratory and convergent discussion phase.

This phase does not automatically authorize PRD authoring.
A transition into PRD writing should occur only when the human explicitly asks for it.

### 2. PM synthesis
Once the human explicitly requests PRD authoring, `pm-skill` is used to synthesize the discussion into an execution-grade engineering brief.

This artifact is not merely a lightweight PRD.  
It is intended to be concrete enough for downstream audit and execution.

The brief typically combines:
- product intent
- architecture decisions
- implementation boundaries
- acceptance criteria
- testing strategy
- exact hardcoded content when required

### 3. Auditor gate
The execution brief must be reviewed by the Auditor.

The Auditor evaluates whether the brief is:
- technically coherent
- structurally valid
- specific enough for downstream execution
- not over-designed or dangerously underspecified

### 4. Human decision gate
The Auditor does not have final launch authority.

After Auditor output:
- the primary agent summarizes the result to the human
- the human decides whether to:
  - revise
  - approve
  - stop

This gate exists to prevent uncontrolled Auditor-primary-agent YOLO loops and requirement drift.

### 5. SDLC execution
Only after:
- the execution brief exists
- the Auditor has approved it
- the human has authorized execution

should `leio-sdlc` be used to launch the downstream SDLC pipeline.

### 6. Automated downstream loop
After launch, `leio-sdlc` may coordinate:
- planning / slicing
- coding
- review
- merge
- UAT
- recovery / resume / withdraw

This is the automated execution phase.

## Role boundaries

### Human
- final decision-maker
- can approve / reject / redirect execution

### Primary agent
- co-pilot during discussion
- synthesis coordinator during PRD authoring
- summary layer between Auditor and the human
- launch controller for the downstream SDLC pipeline

### pm-skill
- upstream authoring stage
- produces the audit-ready execution brief
- does not auto-launch SDLC

### Auditor
- evaluates readiness and soundness
- does not own final launch decision
- must not silently turn into an autonomous revision loop with the primary agent

### leio-sdlc
- downstream execution orchestrator
- operates only on approved execution briefs
- provides launch / resume / withdraw control of the SDLC workflow

## Anti-YOLO principle

A critical rule of this lifecycle is that Auditor approval or rejection must not collapse into an uncontrolled primary-agent loop.

The intended pattern is:
1. Auditor produces result
2. primary agent summarizes it
3. human decides
4. only then does the next stage proceed

If the Auditor rejects the brief, the primary agent should:
- summarize the rejection
- identify the underlying design concern
- explain the likely correction direction
- stop and wait for human input

The primary agent should not mechanically patch the brief line-by-line in response to Auditor comments without an explicit human decision.

## Design implication for skills

Because this lifecycle spans multiple skills, no single top-level `SKILL.md` should try to become the entire system constitution.

Instead:
- each skill should define its own scope and role
- shared lifecycle semantics should live in this reference
- top-level skills should link here when lifecycle context is needed

## Skill responsibilities in this lifecycle

### `pm-skill`
`pm-skill` is responsible for upstream authoring.
It should be triggered only when the human explicitly asks to create or refine the execution brief.

### `leio-sdlc`
`leio-sdlc` is responsible for downstream SDLC execution control.
It should be used only after the execution brief has passed Auditor review and the human has authorized launch.

## Why this separation matters

This separation protects against three common failure modes:
1. premature PRD authoring before discussion convergence
2. uncontrolled Auditor-primary-agent revision loops
3. downstream execution on unaudited or unapproved briefs

Keeping the lifecycle explicit also reduces role contamination across skills and makes each skill easier to keep within a low-blast-radius design boundary.
