status: open

# PR-001: Database Schema for Users

## 1. Objective
Create the foundational User database model with necessary fields for authentication.

## 2. Scope & Implementation Details
- `models/user.py`: Implement SQLAlchemy `User` model with `id`, `username`, `email`, and `password_hash`.
- `tests/test_user_model.py`: Add fixture for DB session and tests for user creation.

## 3. TDD & Acceptance Criteria
- Write `test_user_creation()` in `tests/test_user_model.py` to assert a user can be instantiated and saved to the in-memory SQLite DB.
- CI MUST pass with 100% test coverage on `models/user.py`.