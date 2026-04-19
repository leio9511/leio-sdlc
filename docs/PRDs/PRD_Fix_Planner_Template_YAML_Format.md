---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Fix Planner Template YAML Format (Refactored)

## 1. Context & Problem (业务背景与核心痛点)
The recent architectural upgrade (PRD-Robust) introduced `structured_state_parser.py`. However, the current implementation uses regular expressions to parse YAML frontmatter, which is a **"Lossy Context Flattening"** anti-pattern. Furthermore, the `TEMPLATES/PR_Contract.md.template` remains in the old format, causing the orchestrator to crash when new PRs are generated.

**Current Pain Points:**
1.  **Fragile Parsing**: Regex-based YAML extraction is error-prone and non-standard.
2.  **Orchestrator Crash**: Missing `---` boundaries in the default template cause deterministic runtime failures.
3.  **Governance Debt**: Validation of templates is not integrated into the unified test suite.

## 2. Requirements & User Stories (需求定义)
- **REQ-1 (Standardized Parsing)**: Refactor `structured_state_parser.py` to use a standard library (**PyYAML**) for frontmatter extraction and parsing.
- **REQ-2 (Template Realignment)**: Update all physical templates in `TEMPLATES/` to comply with the structured YAML frontmatter standard.
- **REQ-3 (Unified Validation)**: Implement a new test suite in **pytest** that dynamically validates the structural integrity of all templates in the project.
- **REQ-4 (Safety First)**: Explicitly define a rollback strategy using the newly implemented `--withdraw` flag.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Standardized YAML Parsing
Modify `scripts/structured_state_parser.py`:
- Replace `re.search` logic with a proper YAML loader (e.g., `yaml.safe_load`).
- Ensure the parser identifies the first `---` block and treats it as the authoritative state source.
- Standardize error reporting with absolute file paths.

### 3.2 Template Correction
Wrap the `status: open` field in `/root/projects/leio-sdlc/TEMPLATES/PR_Contract.md.template` with `---` markers. Ensure no trailing whitespace or hidden characters interfere with the standard parser.

### 3.3 Unified Test Integration
Create `tests/test_template_compliance.py`:
- Use `pytest` to discover all files in `TEMPLATES/*.md.template`.
- For each file, invoke `structured_state_parser.get_status()`.
- Assert that the status is successfully parsed and belongs to `VALID_STATES`.
- Integrate this into the mandatory `./preflight.sh` gate.

### 3.4 Rollback Protocol
If the refactoring causes widespread regressions in the state machine:
- Execute `python3 scripts/orchestrator.py --workdir /root/projects/leio-sdlc --prd-file PRD_Fix_Planner_Template_YAML_Format.md --withdraw`.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Standardized Extraction**
  - **Given** a PR contract with complex markdown content after the YAML block.
  - **When** the new parser is invoked.
  - **Then** it must extract the status without being confused by markdown headers or code blocks in the body.

- **Scenario 2: Template CI Gate**
  - **Given** a malformed template is introduced to the `TEMPLATES/` directory.
  - **When** `./preflight.sh` is executed.
  - **Then** `pytest` must catch the violation and block the pipeline.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Zero-Tolerance Parsing**: The parser must fail loudly on any deviation from the YAML standard within the frontmatter block.
- **High-Fidelity Restoration**: The rollback protocol must be verified as the first step of the implementation.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/structured_state_parser.py`: Core logic refactor.
- `TEMPLATES/PR_Contract.md.template`: Format alignment.
- `tests/test_template_compliance.py`: New quality gate.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL - STRING DETERMINISM]**

```markdown
- Parser_Error_No_Boundary: "[FATAL_FORMAT] No valid YAML frontmatter delimiters (---) found in file: {file_path}"
- Parser_Error_Yaml_Syntax: "[FATAL_FORMAT] YAML syntax error in frontmatter: {error_msg} at {file_path}"
```

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.1**: Adopted "Path A" following Auditor rejection. Moved from Regex to PyYAML and收拢 (consolidated) validation logic into pytest to eliminate "Test Logic Fragmentation".
