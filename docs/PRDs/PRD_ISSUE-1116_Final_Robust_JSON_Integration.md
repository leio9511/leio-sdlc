---
Affected_Projects: [leio-sdlc]
---

# PRD: ISSUE-1116 Final Robust JSON Integration

## 1. Context & Problem (业务背景与核心痛点)
In previous PR runs, we created a robust JSON parser (`utils_json.py`) to handle LLM artifacts, avoiding brittle regex. However, due to Orchestrator resets (`git reset --hard`) and branch collisions, the integration of `utils_json.py` into the core scripts (`orchestrator.py` and `merge_code.py`) was lost. The scripts still contain the brittle `r'(\{.*?\})'` non-greedy regex.

## 2. Requirements & User Stories (需求定义)
- Refactor `merge_code.py` to import and use `extract_and_parse_json` from `utils_json` instead of using local regex-based parsing functions.
- Refactor `orchestrator.py` to import and use `extract_and_parse_json` from `utils_json` instead of using local regex-based parsing functions.
- Update `tests/test_merge_code.py` to reflect the new implementation dependency without breaking the CI suite.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- In both scripts, replace `extract_json_from_llm_response` with `extract_and_parse_json` from `utils_json.py`.
- Remove all `re.search` blocks related to extracting JSON strings.
- In `orchestrator.py`, ensure the function `parse_review_verdict` utilizes the robust parser logic gracefully without crashing if no JSON is found.
- In `merge_code.py`, `parse_review_verdict` must wrap `extract_and_parse_json` inside a `try/except Exception:` block to silently return `None` on unparseable data, mirroring previous fail-safe behavior.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- `grep -r "r'(\{.*?\})'" scripts/` must return no matches for JSON-parsing logic in Orchestrator/Merge code.
- `pytest tests/test_merge_code.py` passes successfully.
- `pytest tests/test_orchestrator*.py` passes successfully, validating the retry behavior using `utils_json.py`.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- Unit tests in `test_merge_code.py` verify that `parse_review_verdict` extracts `APPROVED` and `ACTION_REQUIRED` states correctly through the new utility.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/merge_code.py`
- `tests/test_merge_code.py`

## 7. Hardcoded Content (硬编码内容)
- `from utils_json import extract_and_parse_json`
