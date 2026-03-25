status: open

# PR-002: Core Authentication Logic

## 1. Objective
Implement the core authentication logic for hashing passwords and verifying user credentials.

## 2. Scope & Implementation Details
- `services/auth_service.py`: Implement `hash_password(plain_text)` and `verify_password(plain_text, hashed)`.
- Use `passlib` or `bcrypt` for secure hashing.

## 3. TDD & Acceptance Criteria
- Create `tests/test_auth_service.py`.
- Must test that `hash_password` returns a hashed string different from the plain text.
- Must test that `verify_password` returns True for correct passwords and False for incorrect ones.