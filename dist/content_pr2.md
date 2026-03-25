status: open

# PR-002: Core Authentication Logic

## 1. Objective
Implement password hashing and verification utilities.

## 2. Scope & Implementation Details
- `auth/crypto.py`: Implement `hash_password(plain_text)` and `verify_password(plain_text, hash)` using `passlib` or `bcrypt`.
- `tests/test_crypto.py`: Add unit tests for hashing and verification logic.

## 3. TDD & Acceptance Criteria
- Write `test_password_hashing()` to ensure the plain text password is not returned.
- Write `test_password_verification()` to ensure `verify_password` returns True for correct passwords and False for incorrect ones.
- CI MUST pass with 100% test coverage on `auth/crypto.py`.