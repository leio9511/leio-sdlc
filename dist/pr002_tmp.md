status: open

# PR-002: Core Authentication Logic

## 1. Objective
Implement password hashing, password verification, and JWT token generation for authenticated sessions.

## 2. Scope & Implementation Details
- `services/auth_service.py`: Implement `hash_password`, `verify_password`, and `generate_token`.
- `requirements.txt`: Add `passlib` and `PyJWT` (or equivalent).

## 3. TDD & Acceptance Criteria
- `tests/test_auth.py`: Write tests for password hashing/verification and token encoding/decoding.
- Assertion: `verify_password(plain, hashed)` returns True. `decode_token(token)` returns valid payload.