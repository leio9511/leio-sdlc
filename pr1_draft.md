status: open

# PR-001: Database Schema for Users

## 1. Objective
Establish the database schema for the User entity to support the full stack login system.

## 2. Scope & Implementation Details
- `models/user.py`: Define the User model with fields for id, username, email, and password_hash.
- `models/__init__.py`: Export the User model.

## 3. TDD & Acceptance Criteria
- Create `tests/test_user_model.py`.
- Must test successful creation of a User object.
- Must verify that required fields (email, password_hash) raise appropriate errors when missing.