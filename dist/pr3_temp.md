status: open

# PR-003: API Endpoints

## 1. Objective
Expose the core authentication logic via RESTful API endpoints.

## 2. Scope (Functional & Implementation Freedom)
- Implement HTTP routes for user registration (POST /register), login (POST /login), and profile retrieval (GET /me).
- Integrate the previously built authentication service layer into the route controllers.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- API responds with 200/201 on successful registration and login, returning a valid token.
- API responds with 401 Unauthorized for invalid login attempts.
- API endpoints are protected where necessary, returning 401 for requests without valid tokens.
- The Coder MUST ensure all API integration tests run GREEN before submitting.