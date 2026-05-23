---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Preflight Trap Host Tool Guardrail for Explicit Repo Python and OpenClaw Independence

## 1. Context & Problem (业务背景与核心痛点)
A prior trap-mode rollout already established the right remediation pattern for interpreter-binding drift in `leio-sdlc`: make the local failure set reproducible, temporarily quarantine the known failures so every SDLC slice still exits green, then burn the quarantine list down to zero as each failure family is repaired.

That earlier rollout exposed and fixed one major defect in the local preflight stack: `scripts/dev_python.sh` reinstalled `pip` and requirements on every invocation, making trap-mode preflight pathologically slow. That regression is now fixed by making repo-venv bootstrap idempotent.

However, a second and more important contract gap remains.

The repository now has two distinct classes of environment-coupling bugs that local baseline preflight may hide but GitHub CI exposes:

1. **Explicit repo-Python drift**
   Some contract-critical tests spawn SDLC scripts through bare `python3` instead of the explicit repo `.venv` execution contract. When those subprocesses land on a host interpreter without the repo dependencies, they fail with import errors such as `ModuleNotFoundError: No module named 'yaml'`.

2. **Host tool / OpenClaw binary drift**
   Some tests and shell flows implicitly assume the host machine has an `openclaw` binary in `PATH`. Those tests pass on developer machines where OpenClaw happens to be installed, but fail on GitHub runners where `openclaw` is absent.

A GitHub CI probe narrowed the latter class down to concrete failures:
- `tests/test_notification_integration.py::test_notify_channel_integration` fails because the test clears `SDLC_TEST_MODE`, then routes into the real notification path where `utils_notification.NotificationRouter` fails fast if `openclaw` is missing.
- `tests/test_pr_004_rollback.py::test_rollback_no_restart_with_mock` fails because `scripts/rollback.sh` only prints the expected mock-environment skip message if `command -v openclaw` succeeds. In CI it does not, so rollback succeeds but the assertion fails.

The key point is that these are not broad product regressions. They are **environment contract violations** in formal preflight paths. The SDLC rule remains: every slice must exit with preflight green. Therefore this remediation must follow the same rollout pattern as the earlier trap-mode PRD:
- introduce a deterministic local failure surface,
- temporarily quarantine the identified failing tests through the existing ignore manifest,
- repair them incrementally,
- remove each entry in the same PR that fixes it,
- and finish only when the manifest is empty and the strengthened trap path is green.

This PRD is intentionally not a general repository cleanup of all historical `python3` strings or every possible host tool reference. It is narrowly focused on **formal preflight/test surfaces whose correctness must no longer depend on the developer host environment.**

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. Preflight trap mode must cover all formal test entry surfaces, including pytest-driven tests, bash tests, mocked E2E harnesses, and any other contract-critical execution branches already managed by preflight.
2. The trap rollout must expose contract-critical subprocess calls that use ambient `python3`, `pytest`, or equivalent host-discovered tools rather than an explicit repository execution contract.
3. The rollout must also expose tests and shell flows that implicitly depend on a host-installed `openclaw` binary.
4. The solution must provide a deterministic test helper / fixture for mocking an `openclaw` binary so tests can verify command behavior without depending on the host machine.
5. The solution must preserve the existing repo `.venv` execution contract through `scripts/dev_python.sh` and any approved explicit repo-python helpers.
6. The solution must reuse the existing `ignore_tests.json` manifest as a temporary, auditable remediation mechanism so each SDLC slice can still exit preflight-green.
7. Manifest entries may only correspond to currently reproduced failures for this rollout; unrelated additions are forbidden.
8. Any PR that repairs one or more quarantined failures must remove the corresponding manifest entries in the same change.
9. Final completion requires strengthened trap-mode preflight green with the existing ignore manifest empty.
10. The remediation must not weaken or regress the already-fixed idempotent `scripts/dev_python.sh` bootstrap behavior.
11. The remediation must not redefine success as “developer machines happen to have OpenClaw installed.” Formal tests must become invariant to that host detail.
12. The rollout must keep the scope limited to the currently reproduced contract-critical failure set and minimal shared helper/framework changes required to fix it.

### 2.2 Non-Functional Requirements
1. The solution must maximize local reproducibility of GitHub CI failure classes.
2. The solution must prefer explicit repository-controlled execution over implicit host PATH behavior.
3. The solution must support incremental burn-down so every slice ends green while still honestly tracking unresolved failures.
4. The solution must not require developers to manually uninstall host tools or mutate system Python to reproduce failures.
5. Test behavior must become independent of whether `openclaw` is installed on the developer machine.
6. The trap mechanism must remain understandable and auditable; avoid hidden environment magic that obscures which layer is being validated.

### 2.3 User / Operator Stories
- As a maintainer, I want local trap-mode preflight to expose host-environment coupling bugs before GitHub CI does, so local green is a trustworthy predictor.
- As an SDLC operator, I need every remediation PR to exit with preflight green, so I can fix failures incrementally without breaking the delivery pipeline contract.
- As a reviewer, I want all temporary quarantine entries to shrink toward zero, so I can tell whether the rollout is converging.
- As a test author, I want a standard helper for faking `openclaw`, so tests do not accidentally depend on my laptop setup.

### 2.4 Explicit Non-Goals
This PRD does not include:
- a repository-wide rewrite of every historical `python3` string
- a general redesign of deploy/runtime provisioning already covered by prior work
- replacing the existing repo `.venv` execution model with uv or another external dependency manager
- permanently muting failures through long-lived ignore entries
- broad cleanup of non-contract-critical developer scripts that never run through formal preflight

## 3. Architecture & Technical Strategy (架构设计与技术路线)
The remediation should follow the same staged burn-down pattern used by the trap-mode rollout PRD, but broaden the concept of “host drift” beyond ambient Python packages to include host-installed binaries.

### 3.1 Strengthened Trap Semantics
Preflight trap mode must remain a hostile environment detector, not the project runtime itself.

The strengthened trap path should validate two independent properties:
1. **Repo Python explicitness** — formal test subprocesses must not rely on ambient `python3` / `pytest` resolution.
2. **Host tool independence** — tests that verify `openclaw`-related behavior must not silently rely on a real host-installed `openclaw` binary.

The current repo-venv bootstrap remains the formal success path. Trap mode is the detector that makes implicit host coupling fail deterministically.

### 3.2 Preflight Changes
Preflight must be modified so the strengthened trap environment applies uniformly to all formal test entry paths, not only bash branches.

Concretely:
- The trap environment must be active for pytest-driven test execution as well as shell-driven tests.
- The trap environment should be established once at preflight entry when trap mode is enabled, rather than selectively per branch.
- The existing hostile trap venv should continue to ensure bare `python3` / `pytest` resolve away from repo dependencies.
- The preflight architecture should remain compatible with `scripts/dev_python.sh` as the explicit repo-python entrypoint.
- Trap mode must prepend a **controlled test bin directory** to `PATH` and use that directory as the authoritative masking layer for host-tool detection during trap execution.
- That controlled test bin directory must contain a **hostile detector stub** `openclaw` executable whose default purpose is to mask any host-installed OpenClaw binary and make host-tool drift reproducible.
- The trap-path detector stub and the test-side fake-OpenClaw fixture are **separate artifacts with separate semantics**: the trap stub exists to expose hidden host dependence, while the test fixture exists to model and assert intentional command behavior.
- The rollout must not require a single multi-mode `openclaw` stub that both detects failures and cooperates with test assertions; keeping those concerns separate is the required design direction.
- The trap mechanism must be deterministic across developer hosts regardless of whether a real `openclaw` binary is globally installed.
- The rollout must not rely on developers uninstalling host tools, mutating system Python, or otherwise changing workstation state to reproduce failures.

### 3.3 Failure Families and Repair Strategy
This rollout should treat the current failures as two repair families.

#### Family A: Explicit repo-Python drift
These are tests that currently spawn SDLC scripts through bare `python3` and thereby bypass the repo `.venv` contract.

Current reproduced set:
- `tests/test_080_orchestrator_dynamic_strings.py`
- `tests/test_cleanup_flag.py`
- `tests/test_commit_state.py`
- `tests/test_pr_002_orchestrator_lock.py`
- `tests/test_resume_logic_overhaul.py`
- `tests/test_resume_split.py`

Repair pattern:
- add / reuse a small explicit repo-python test helper or fixture,
- route all contract-critical subprocess Python launches through that helper,
- for Python-driven tests, the shared helper must resolve and invoke the repository `.venv` Python interpreter directly as a **Python-side adapter of the `scripts/dev_python.sh` contract**, rather than shelling out to ambient `python3`,
- `scripts/dev_python.sh` remains the canonical human/shell entrypoint for the repo-python contract, but Python tests are authorized to use the direct `.venv` interpreter helper so long as that helper is explicitly defined as implementing the same contract,
- `scripts/runtime_python.sh` is not the primary contract surface for this remediation unless a follow-up explicit decision revises that scope,
- remove the corresponding manifest entries when each file family is fixed.

The preferred contract is repository-local and explicit: `scripts/dev_python.sh` or a minimal wrapper/helper that resolves to the repo `.venv` interpreter.

#### Family B: Host `openclaw` binary drift
These are tests that currently pass only because the developer host has `openclaw` installed.

Current reproduced set:
- `tests/test_notification_integration.py::test_notify_channel_integration`
- `tests/test_pr_004_rollback.py::test_rollback_no_restart_with_mock`

Repair pattern:
- introduce a shared fake-OpenClaw helper / fixture for tests,
- make tests inject a fake `openclaw` binary into PATH when validating behavior that depends on the presence of that binary,
- remove any assertions that assume a real host-installed OpenClaw binary exists unless the test explicitly provisions one.
- default the rollout to **test-side fake binary / PATH-controlled dependency modeling**, not product-behavior changes.
- for `test_notify_channel_integration`, the default repair path is to validate the real notification delivery boundary through fake `openclaw` binary injection at PATH, rather than mocking away the whole notification stack at a higher abstraction layer.

Best-practice resolution choice for this family:
- prefer fixing the tests and their fixtures so they explicitly model the `openclaw` dependency,
- do **not** change product/runtime behavior solely to accommodate a host-dependent test unless the product contract itself is wrong,
- for `test_notify_channel_integration`, prefer mocking the real notification boundary or injecting a fake `openclaw` binary over relying on the host machine,
- for `test_rollback_no_restart_with_mock`, prefer a fake `openclaw` binary in the test PATH if the intent is to validate the branch where an `openclaw` command exists; only change rollback script semantics if the product contract is intentionally being redefined.

For `test_notification_integration`, the test should prefer validating the effective delivery boundary by providing a fake `openclaw` binary in PATH and asserting the resulting behavior, rather than mocking away `NotificationRouter.send` or the full provider stack at a layer that would bypass the host-tool contract under test.

For rollback-related behavior, either:
- the script logic must explicitly print the mock-environment skip message whenever `HOME_MOCK` is set, or
- the test must provide a fake `openclaw` binary in PATH and then assert against the resulting behavior.

The preferred default for this PRD is the second path: use test-side fake binary provision unless a product-level contract decision explicitly requires changing script behavior.

### 3.4 Shared Helper Strategy
A small shared helper layer is justified here because the same environment contract mistake has already appeared in multiple places.

Authorized helper additions may include:
- a repository-local Python execution helper for tests that need to spawn SDLC scripts under the repo `.venv`
- a fake-OpenClaw fixture / helper that provisions a temporary executable into PATH and records invocation arguments

The goal is to stop duplicating fragile subprocess setup logic across tests.

Recommended helper direction:
- a repo-python test helper that standardizes `subprocess.run([...])` against the explicit repo interpreter contract
- for Python-driven tests, that helper should directly resolve the repository `.venv` interpreter instead of going back through ambient `python3`; this is the approved Python-side adapter of the `scripts/dev_python.sh` contract
- a fake `openclaw` helper/fixture under `tests/` that creates a temporary executable, injects it into `PATH`, and records invocations for assertions
- tests must not depend on a developer workstation already having `openclaw` installed
- the fake `openclaw` helper should be built to sit inside the controlled test bin directory used by trap mode, so the same masking concept applies consistently between preflight and test fixtures
- the existing repo `mock_bin/openclaw` may inform implementation, but this PRD does not require blindly reusing it; a trap-specific detector stub and a test-specific fake fixture may evolve separately if that keeps semantics clearer and avoids cross-test coupling

Best-practice policy for this rollout:
- test-only helpers belong under `tests/` (for example `tests/*_support.py` or fixtures exposed through `tests/conftest.py`), not under product/runtime `scripts/`
- product/runtime behavior should not be changed merely to satisfy a host-dependent test if a test fixture can model the dependency explicitly
- fake binaries / PATH injection are preferred over relying on developer-host tools already being installed
- repository-Python subprocess helpers should be explicit, minimal, and reused consistently across all Family A files
- for host-OpenClaw drift, prefer a narrowly scoped helper or fixture over prematurely globalizing behavior in `tests/conftest.py` unless multiple repaired files clearly justify the broader scope
- the default repair direction for host-OpenClaw drift is **test-side mocking / fake binary provision**, not product behavior changes, unless the product contract itself is intentionally being redefined

The chosen helper design should be intentionally minimal and reusable across all files in Family A and Family B.


### 3.5 Manifest / Quarantine Strategy
The existing `ignore_tests.json` manifest is mandatory for rollout control because SDLC requires each slice to end green.

The current manifest mechanism is **file-oriented only**. This PRD explicitly accepts that constraint and does not authorize any redesign toward test-case or node-id granularity.

Because of that constraint, the rollout must quarantine by **failure family / file group**, not by individual failing assertion.

That file-level quarantine may temporarily suppress passing tests that happen to live in the same file as currently reproduced failures. This PRD explicitly accepts that tradeoff during staged remediation, provided the quarantined files remain limited to the authorized rollout set and are burned down back to zero.

The manifest-contract tests themselves are explicitly authorized to participate in the staged rollout:
- **during early rollout**, the relevant tests may assert that the manifest is non-empty but constrained to the authorized family/file set for this PRD,
- **during final rollout completion**, those same tests must be tightened back to asserting that the manifest is empty.

Initial Family A quarantine set:
- `tests/test_080_orchestrator_dynamic_strings.py`
- `tests/test_cleanup_flag.py`
- `tests/test_commit_state.py`
- `tests/test_pr_002_orchestrator_lock.py`
- `tests/test_resume_logic_overhaul.py`
- `tests/test_resume_split.py`

Initial Family B quarantine set:
- `tests/test_notification_integration.py`
- `tests/test_pr_004_rollback.py`

Files that were investigated but are **not** to be added to the manifest because they passed in isolated GitHub CI probe runs:
- `tests/test_planner_envelope_debug.py`
- `tests/test_planner_envelope_forward_compatibility.py`
- `tests/test_trap_mode_final_clean_contract.py`

Each fix PR must:
- repair a bounded subset,
- prove local trap-mode or host-tool reproduction before the fix,
- prove green after the fix,
- and remove the corresponding file entries from the manifest in the same change.

The rollout should prefer family-level slices rather than tiny single-test slices, because file-level quarantine is the only supported mechanism.

### 3.6 Authorized Framework Surface
Framework or shared files that this PRD authorizes for modification include:
- `preflight.sh`
- trap-mode helper/bootstrap logic responsible for constructing the hostile environment and controlled PATH masking layer
- `scripts/dev_python.sh` only if follow-up adjustment is strictly required for the explicit repo-python contract
- `scripts/runtime_python.sh` only if a narrowly scoped compatibility adjustment is strictly required by the approved repo-python helper direction; otherwise it is out of primary scope for this remediation
- test helpers / fixtures under `tests/` or `scripts/` as needed for repo-python and fake-OpenClaw support
- the specific failing test files listed above
- `scripts/rollback.sh` only if the chosen fix requires behavior/documentation alignment for mock restart handling

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Pytest trap coverage matches bash trap coverage**
  - **Given** trap mode is enabled
  - **When** preflight runs formal pytest and bash test branches
  - **Then** both branches must execute inside the same hostile trap environment rather than leaving pytest on the ambient host path
  - **And** the trap environment must use a controlled PATH masking layer that hides any real host-installed `openclaw` binary

- **Scenario 2: Bare python contract violations are locally reproducible**
  - **Given** a contract-critical test that spawns SDLC scripts through bare `python3`
  - **When** trap-mode preflight is run before remediation
  - **Then** the test must fail locally in the same class as GitHub CI

- **Scenario 3: Explicit repo-python subprocesses survive trap mode**
  - **Given** a contract-critical test has been updated to use the explicit repo `.venv` helper
  - **When** trap-mode preflight is run
  - **Then** the subprocess path must succeed regardless of ambient host Python package state

- **Scenario 4: Tests do not rely on host-installed OpenClaw**
  - **Given** a machine where no real `openclaw` binary exists in PATH
  - **When** tests that validate OpenClaw-related behavior are run
  - **Then** they must either pass through a fake `openclaw` fixture or fail only if the product logic is actually broken, not because the host tool is absent

- **Scenario 5: Rollback mock behavior is explicit and deterministic**
  - **Given** rollback is executed in a mock environment
  - **When** restart behavior is validated
  - **Then** the expected skip/restart behavior must not depend on whether the developer workstation happens to have `openclaw` installed

- **Scenario 6: Temporary quarantine preserves slice-green requirement**
  - **Given** some currently reproduced failure files remain unresolved
  - **When** a remediation slice completes
  - **Then** preflight must still exit green by means of the temporary manifest quarantine, with only the currently known files listed

- **Scenario 7: Final completion has zero remaining drift debt**
  - **Given** all Family A and Family B failures have been repaired
  - **When** trap-mode preflight runs
  - **Then** it must pass and the manifest must be empty

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core quality risk
The core risk is false confidence: local tests pass only because the host machine has hidden support (ambient Python packages or a locally installed `openclaw` binary) that formal repository execution contracts do not guarantee.

### Test strategy
- Use strengthened trap-mode preflight as the primary detector for repo-Python drift.
- Use explicit fake-OpenClaw fixtures to make host tool expectations deterministic.
- Keep normal baseline preflight green throughout rollout.
- Validate each repaired file family both before and after the fix.
- Prefer isolated file-level reproduction for debugging, but require full preflight green for slice exit.
- Do not treat host PATH state as a legitimate test fixture unless the test itself explicitly provisions that state.

### Mocking guidance
- Mock or fake `openclaw` at the PATH boundary instead of relying on a real installed binary.
- Prefer explicit repo-python helpers over ambient interpreter assumptions.
- Do not rely on developer workstation state for any assertion in formal tests.
- When a shell script branch depends on the presence of a host binary, tests should explicitly provide a fake binary if the branch behavior is what is under test.
- For `test_notify_channel_integration`, prefer fake `openclaw` PATH injection that exercises the real notification delivery boundary over mocking away the entire notification stack at a higher layer.
- Only change product/runtime behavior for testability when the desired product contract itself is being intentionally redefined.
- The default expectation for this rollout is that `test_rollback_no_restart_with_mock`-style failures are solved via test-side fake `openclaw` provisioning unless a separate product-contract decision explicitly approves changing rollback semantics.

### Quality goal
After completion, formal preflight correctness must be invariant to:
- whether the host system Python has project packages installed,
- whether `openclaw` exists in PATH,
- and whether tests are run locally or on GitHub Actions.

## 6. Framework Modifications (框架防篡改声明)
- `preflight.sh`
- `scripts/dev_python.sh` (only if strictly needed to preserve explicit repo-python execution contract)
- `scripts/rollback.sh` (only if behavior/contract alignment requires it)
- `tests/test_080_orchestrator_dynamic_strings.py`
- `tests/test_cleanup_flag.py`
- `tests/test_commit_state.py`
- `tests/test_pr_002_orchestrator_lock.py`
- `tests/test_resume_logic_overhaul.py`
- `tests/test_resume_split.py`
- `tests/test_notification_integration.py`
- `tests/test_pr_004_rollback.py`
- new shared helpers/fixtures under `tests/`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial execution-grade brief derived from trap-mode debugging and CI-only probe workflow findings.
- **v1.1 rationale**: Clarified that the existing manifest remains file-oriented and should not be redesigned here.
- **v1.2 rationale**: Locked the trap mechanism to a controlled PATH masking layer with a stub `openclaw`, clarified that repo-python helpers should layer on top of `scripts/dev_python.sh`, and made staged manifest-contract alignment explicit.
- **v1.3 rationale**: Split hostile trap stub semantics from cooperative test fake semantics, chose the Python-side `.venv` helper direction for Family A, clarified the notification-test boundary to prefer fake `openclaw` PATH injection, and explicitly accepted the file-level quarantine tradeoff.

---

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **For expected rollback skip text (if preserved as canonical behavior)**:
```text
Skipping OpenClaw gateway restart (mock environment detected)...
```

- **For notification fatal message format already relied on in product code**:
```text
[FATAL] Requested remote channel '{channel}' but the required message-delivery tool '{binary}' was not found in PATH.
```
