---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Trap-Mode Preflight Guardrail for Explicit Repo Venv Contract

## 1. Context & Problem (业务背景与核心痛点)
Issue #57 attempted to establish a controlled Python execution contract for `leio-sdlc` across local development/testing, deployed runtime, and GitHub CI. That work succeeded partially: the repository now has a controlled repo `.venv`, deploy now provisions a runtime `.venv`, and runtime smoke validation proved the deployed runtime path can bind to the expected interpreter.

However, real validation after deployment and GitHub push showed Issue #57 is not complete. The decisive evidence is:

1. Local baseline `bash preflight.sh --report-all` is green in the normal development environment.
2. Deploy now correctly provisions `~/.openclaw/skills/leio-sdlc/.venv` and runtime smoke passes.
3. GitHub CI still fails in `Run preflight` with repeated errors such as:
   - `ModuleNotFoundError: No module named 'yaml'`
   - `ModuleNotFoundError: No module named 'pytest'`
4. The failing points are contract-critical bash tests and mocked E2E harnesses that invoke Python via ambient `python3` / `pytest` instead of an explicit repo `.venv` entrypoint.

A controlled local experiment in an isolated clone confirmed the root problem:
- baseline preflight in normal local environment: green
- preflight after activating a clean ambient trap venv with only base Python: fails with the same GitHub-style `yaml` / `pytest` import errors
- preflight after adding only `PyYAML` and `pytest` into the trap venv: green again

This proves the primary current failure mode is interpreter-binding drift in contract-critical tests/harnesses, not broad product logic regression. In other words, some test paths still depend on ambient Python package state, and that dependency is masked locally but exposed in GitHub CI.

The problem to solve now is not general Python packaging, not deploy/runtime provisioning, and not a full repository-wide cleanup of every historical `python3` string. The problem is narrower and more actionable:

> formal preflight must be able to expose and then eliminate any contract-critical Python invocation that is not explicitly bound to the correct repo `.venv` execution path.

Because the downstream SDLC process requires every sliced PR to end with preflight green, the rollout must reuse the existing ignore manifest as a temporary, auditable execution aid for known trap-mode failures. That existing ignore list is allowed only as an execution aid during the remediation rollout and must be fully burned down to zero before this issue is complete.

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. The system must introduce a preflight trap mode that creates a clean temporary ambient Python environment with only base Python and no project dependencies such as `PyYAML` or `pytest` preinstalled.
2. In trap mode, preflight must activate that clean temporary environment before running contract-critical bash tests and mocked E2E harnesses so that ambient `python3` / `pytest` dependency leaks are exposed deterministically.
3. Trap mode must not modify the repository’s formal repo `.venv` or the deployed runtime `.venv`.
4. Trap mode must use temporary artifacts only and must delete its temporary environment on normal completion and best-effort cleanup paths.
5. The rollout must reuse the existing ignore manifest so that, after trap mode is introduced, each sliced SDLC PR can still end with preflight green while the known trap failures are incrementally burned down.
6. That existing ignore manifest must be initialized only with the trap-mode failures explicitly identified during rollout and must not become a generic dumping ground for unrelated failures.
7. Each PR that fixes one or more trap-mode failures must remove the corresponding entries from the existing ignore manifest in the same change.
8. The final completion condition for this work must be: trap mode preflight green with the existing ignore manifest empty.
9. The implementation must repair the current GitHub-hit contract-critical test paths that invoke Python through ambient `python3` / `pytest` instead of an explicit repo `.venv` entrypoint.
10. The implementation must preserve deploy/runtime behavior from Issue #57; this follow-up is not allowed to regress the already working deployed runtime `.venv` provisioning and runtime smoke path.
11. The implementation must preserve the existing normal local baseline preflight path; trap mode is an additional guardrail and rollout mechanism, not permission to break the current green path.
12. The implementation must make the trap-mode failure set locally reproducible in an isolated environment so that future regressions can be diagnosed without relying on GitHub CI alone.
13. The implementation must keep the initial fix scope constrained to the currently GitHub-hit contract-critical files and any minimal supporting preflight/shared helper code required to make those files explicit about interpreter binding.
14. The implementation must not redefine success as “source the repo `.venv` and hope ambient `python3` resolves correctly.” Formal contract-critical calls must converge on explicit repo `.venv` entrypoints.

### 2.2 Non-Functional Requirements
1. The solution must prioritize reproducibility and auditability over convenience shell magic.
2. The trap mechanism must be deterministic enough that local reproduction of the GitHub failure class is stable.
3. The solution must avoid polluting the main repository environment or requiring manual system-level package removal.
4. The rollout must remain compatible with the current SDLC rule that every sliced PR ends with preflight green.
5. The rollout mechanism must be transparent about temporary quarantined failures and must not silently convert trap-mode red into an unqualified green state.
6. The scope must remain bounded to contract-critical preflight/test execution paths; it must not expand into a repository-wide historical `python3` string cleanup.
7. The solution must support incremental burn-down so the fix can be delivered through multiple TDD-style slices while preserving honest status.

### 2.3 User / Operator Stories
- As a maintainer, I want preflight to deterministically expose contract-critical Python calls that still depend on ambient Python, so local green no longer hides GitHub CI breakage.
- As an SDLC operator, I need a rollout path where every PR still ends with preflight green, so I can fix the failures incrementally without violating the existing pipeline discipline.
- As a reviewer, I want the existing ignore manifest to shrink to zero over time during the trap rollout, so I can tell whether the remediation is converging or just hiding problems.
- As an environment owner, I want this follow-up to leave deploy/runtime `.venv` provisioning intact, so the already validated runtime execution contract does not regress.

### 2.4 Explicit Non-Goals
This PRD does not include:
- redesigning the deploy/runtime `.venv` model already established by Issue #57
- solving every historical or documentation-only `python3` reference in the repository
- converting all developer workflows to require `source .venv/bin/activate`
- introducing a permanent broad ignore policy for test debt
- weakening the existing SDLC rule that each PR must end with preflight green

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Guiding Principle
This follow-up treats the problem as a contract-enforcement gap in preflight/test harnesses, not as a runtime provisioning problem. The correct target behavior is:
- formal repo-development/test calls must be explicitly bound to the repo `.venv`
- ambient Python must be intentionally hostile in trap mode so accidental reliance is exposed
- temporary quarantine is allowed only as a burn-down mechanism, never as final success

### 3.2 Trap-Mode Guardrail
Preflight gains an explicit trap mode (for example, a CLI flag or an equivalent guarded path) with the following behavior:
1. Create a temporary clean venv used only as the ambient Python trap.
2. Do not install project requirements into that temporary trap venv during the initial trap check.
3. Activate that trap venv so bare `python3`, bare `pytest`, and `#!/usr/bin/env python3`-style paths resolve to a clean interpreter lacking project dependencies.
4. Run the contract-critical bash test and mocked E2E surfaces under that ambient trap.
5. Clean up the temporary trap venv on exit.

The trap venv is a detector, not the formal project environment. Its purpose is to make ambient-python leaks fail early and consistently.

### 3.3 Explicit Repo `.venv` Entry Contract
Any contract-critical path that is supposed to succeed in development/test must not rely on the ambient trap or ambient host Python. Those paths must converge on an explicit repo `.venv` entrypoint, such as:
- the existing `scripts/dev_python.sh`
- or an equivalent explicit helper with the same semantics

Hardcoded absolute paths inside every test file are not required if a repository-local wrapper provides the same explicit binding. The important property is explicit interpreter binding, not the literal textual form.

### 3.4 Rollout via Existing Ignore Manifest
Because current SDLC rules require every PR to finish green, trap mode cannot be introduced and left broadly red. Therefore the rollout reuses the existing ignore manifest with strict semantics:
- its initial contents for this rollout are the set of currently trap-failing contract-critical tests/harnesses identified during rollout bootstrap
- it exists only to keep each sliced PR preflight-green while the failures are incrementally repaired
- each PR that repairs one or more failing paths must remove the corresponding entries from the manifest
- the manifest may shrink during rollout; adding unrelated items is not allowed
- final completion requires the manifest to be empty

This is intentionally more constrained than a generic long-lived debt bucket. For this PRD, the existing ignore manifest is a remediation burn-down mechanism, not a permanent waiver system.

### 3.5 Minimal First-Round Fix Surface
The first round of implementation must focus on the currently GitHub-hit surfaces:

#### A. Core failing bash tests
- `scripts/test_cwd_guardrail.sh`
- `scripts/test_escalation_clean.sh`
- `scripts/test_missing_channel.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`
- `scripts/test_orchestrator_session_strategy.sh`
- `scripts/test_polyrepo_context.sh`
- `scripts/test_pr_003.sh`

#### B. Current GitHub-hit mocked E2E harnesses
- `scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh`
- `scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh`
- `scripts/e2e/mocked/e2e_test_forensic_quarantine.sh`
- `scripts/e2e/mocked/e2e_test_git_boundary.sh`
- `scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh`
- `scripts/e2e/mocked/e2e_test_ignition_guardrail.sh`
- `scripts/e2e/mocked/e2e_test_job_queue_engine.sh`
- `scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh`
- `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- `scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh`
- `scripts/e2e/mocked/e2e_test_uat_orchestrator.sh`

#### C. Minimal supporting framework surface
- `preflight.sh`
- `scripts/e2e/setup_sandbox.sh` only if minimally necessary
- a minimal shared repository-local dev-python wrapper/helper only if required to avoid duplicated binding logic

The first round must avoid unnecessary expansion into deploy/runtime code or non-contract-critical historical references.

### 3.6 Evidence-Based Rollout Logic
The local experiment already established the following sequence:
- baseline preflight: green
- trap-empty ambient Python: GitHub-style `yaml` / `pytest` failures reproduced
- trap ambient Python plus minimal missing deps: preflight green

That evidence supports a focused implementation strategy:
- treat interpreter-binding drift as the first-order problem
- do not assume broad hidden product regressions unless new failures remain after contract fixes
- use trap mode to guard against future regressions in this same failure class

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Trap mode reproduces ambient-python contract violations**
  - **Given** a repository state where contract-critical tests still invoke Python through ambient `python3` / `pytest`
  - **When** preflight runs in trap mode
  - **Then** those calls must fail in a deterministic, locally reproducible way instead of being silently masked by the developer machine environment

- **Scenario 2: Normal baseline preflight remains green during rollout**
  - **Given** the current repository baseline passes preflight in the normal local environment
  - **When** trap mode is introduced
  - **Then** the repository must still support a green normal preflight path while the trap rollout is in progress

- **Scenario 3: Temporary trap quarantine preserves per-PR green requirement**
  - **Given** trap mode has been introduced and an initial set of trap-failing tests has been identified
  - **When** a sliced remediation PR is prepared for completion
  - **Then** preflight must still be green for that PR through the temporary trap quarantine mechanism, consistent with the existing SDLC rule that each PR ends green

- **Scenario 4: Fixed tests are removed from quarantine**
  - **Given** a specific trap-failing test or harness has been updated to use an explicit repo `.venv` entrypoint
  - **When** the remediation PR is validated
  - **Then** that test must pass in trap mode and its entry must be removed from the temporary trap quarantine list in the same PR

- **Scenario 5: Final rollout completion has no remaining trap debt**
  - **Given** all targeted contract-critical test and harness paths have been remediated
  - **When** preflight runs in trap mode
  - **Then** preflight must pass and the temporary trap quarantine list must be empty

- **Scenario 6: Existing deploy/runtime contract does not regress**
  - **Given** Issue #57 already established working deployed runtime `.venv` provisioning and runtime smoke behavior
  - **When** this follow-up is implemented
  - **Then** deploy/runtime validation must remain green and must not be weakened or broken by the trap rollout

- **Scenario 7: Ambient Python no longer changes correctness of formal test paths**
  - **Given** two environments where ambient Python package availability differs
  - **When** formal contract-critical test paths are executed after remediation
  - **Then** they must succeed or fail based on the explicit repo `.venv` contract rather than on ambient package state

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
The core risk is false confidence: local preflight appears green because ambient Python happens to contain project dependencies, while GitHub CI or future clean environments fail because contract-critical paths are not explicitly interpreter-bound.

### 5.2 Testing Strategy
Required test signals:
1. Normal local baseline preflight remains green.
2. Trap-empty mode reproduces GitHub-style `yaml` / `pytest` dependency failures before remediation.
3. Each remediation slice proves that the targeted failing test/harness now passes under trap mode and can be removed from the existing ignore manifest.
4. Final validation proves trap-mode preflight green with empty existing ignore manifest.
5. GitHub CI preflight green after the rollout is complete.

Verification methods:
- bash test coverage for contract-critical failing scripts
- mocked E2E coverage for the currently GitHub-hit harnesses
- direct comparison of failure sets between baseline, trap-empty, and remediated trap runs when needed
- preservation of existing runtime smoke/deploy validation signals from Issue #57

Mocking expectations:
- continue using existing mocked E2E patterns where appropriate
- do not introduce live external API requirements for this remediation
- sandbox and fixture behavior may be updated only as needed to preserve explicit repo `.venv` binding semantics

### 5.3 Quality Goal
A clean environment must no longer reveal interpreter-binding drift in contract-critical preflight paths. After completion, formal test correctness must be invariant to ambient Python package state.

## 6. Framework Modifications (框架防篡改声明)
- `preflight.sh`
- `scripts/test_cwd_guardrail.sh`
- `scripts/test_escalation_clean.sh`
- `scripts/test_missing_channel.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`
- `scripts/test_orchestrator_session_strategy.sh`
- `scripts/test_polyrepo_context.sh`
- `scripts/test_pr_003.sh`
- `scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh`
- `scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh`
- `scripts/e2e/mocked/e2e_test_forensic_quarantine.sh`
- `scripts/e2e/mocked/e2e_test_git_boundary.sh`
- `scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh`
- `scripts/e2e/mocked/e2e_test_ignition_guardrail.sh`
- `scripts/e2e/mocked/e2e_test_job_queue_engine.sh`
- `scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh`
- `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- `scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh`
- `scripts/e2e/mocked/e2e_test_uat_orchestrator.sh`
- `scripts/e2e/setup_sandbox.sh` only if minimally necessary
- a minimal shared repository-local dev-python wrapper/helper only if required to avoid duplicated binding logic

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: Follow-up PRD created after Issue #57 deploy/runtime work proved partially successful but GitHub CI exposed unresolved contract-critical ambient-python leaks in preflight/test harnesses.
- **Evidence used for v1.0**: Local baseline preflight was green; GitHub CI failed with `yaml` / `pytest` missing errors; isolated local trap experiment reproduced the same failure class; adding only `PyYAML` and `pytest` back into the trap environment restored green.
- **v1.0 rollout rationale**: The rollout must respect the SDLC rule that every sliced PR ends with preflight green. Therefore the existing ignore manifest is explicitly reused during remediation, but completion requires that manifest to reach zero entries for this trap-mode rollout.

---

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **Trap quarantine status banner / summary wording**:
```text
TRAP REMEDIATION PENDING
This preflight run is green only under the temporary existing ignore-manifest rollout for trap-mode failures.
Remaining trap failures must be burned down to zero before this issue is complete.
```

- **Trap final-success wording**:
```text
TRAP MODE CLEAN
Trap-mode preflight passed with no remaining trap remediation entries.
```

- **If no exact hardcoded strings beyond the above are required**:
```text
None
```
