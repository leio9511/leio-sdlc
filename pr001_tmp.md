status: open

# PR-001: Database Schema for Users

## 1. Objective
Implement the database schema for the User model using SQLAlchemy to support the login system.

## 2. Scope & Implementation Details
- `models/user.py`: Define User class with `id`, `username`, `email`, and `password_hash`.
- `migrations/env.py`: Ensure models are loaded for Alembic.

## 3. TDD & Acceptance Criteria
- `tests/test_models.py`: Write a test that instantiates a User, saves it to an in-memory DB, and retrieves it.
- Assertion: `user.id` is not None after database commit.