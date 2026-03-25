status: open

# PR-001: Database Schema and User Model

## 1. Objective
Create the User database schema and ORM model to store user credentials.

## 2. Scope & Implementation Details
- `models/user.py`: Define `User` model with `id`, `username`, `password_hash`.
- `migrations/initial_schema.sql`: SQL to create the users table.

## 3. TDD & Acceptance Criteria
- `tests/test_user_model.py`: Write tests to ensure a `User` can be instantiated and saved to the in-memory database.
- Assert that saving a user with a duplicate username raises an IntegrityError.

---

status: open

# PR-002: Core Authentication Logic

## 1. Objective
Implement password hashing and JWT token generation logic.

## 2. Scope & Implementation Details
- `services/auth_service.py`: Implement `hash_password`, `verify_password`, and `generate_token`.

## 3. TDD & Acceptance Criteria
- `tests/test_auth_service.py`: Write tests to verify that `verify_password` returns True for the correct password and False for incorrect ones.
- Assert that `generate_token` returns a valid JWT string containing the user ID.