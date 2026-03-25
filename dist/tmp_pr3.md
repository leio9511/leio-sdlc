status: open

# PR-003: Auth API Endpoints

## 1. Objective
Create Flask routes for user registration and login.

## 2. Scope & Implementation Details
- `api/auth_routes.py`: Implement `POST /api/register` and `POST /api/login`.
- `app.py`: Register the new auth blueprint.

## 3. TDD & Acceptance Criteria
- `tests/test_api_auth.py`: Write integration tests using Flask test client. Test successful registration, duplicate email rejection, successful login, and invalid credentials.
- CI passes.