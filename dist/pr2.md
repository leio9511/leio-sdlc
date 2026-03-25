status: open

# PR-002: Core Authentication Logic

## 1. Objective
Implement password hashing and JWT token generation logic.

## 2. Scope & Implementation Details
- `services/auth_service.py`: Implement `hash_password`, `verify_password`, and `generate_token`.

## 3. TDD & Acceptance Criteria
- `tests/test_auth_service.py`: Write tests to verify that `verify_password` returns True for the correct password and False for incorrect ones.
- Assert that `generate_token` returns a valid JWT string containing the user ID.