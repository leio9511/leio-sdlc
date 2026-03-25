status: open

# PR-004: React UI Login Integration

## 1. Objective
Build the frontend login and registration forms and connect them to the Auth API.

## 2. Scope & Implementation Details
- `frontend/src/components/Login.js`: Create login form.
- `frontend/src/components/Register.js`: Create registration form.
- `frontend/src/api/auth.js`: Add axios calls to API endpoints.

## 3. TDD & Acceptance Criteria
- `frontend/src/components/Login.test.js`: Write component tests verifying form rendering, submission payload, and error handling.
- CI passes including Jest tests.