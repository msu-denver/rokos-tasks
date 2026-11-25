**Value** 3 · **Points** 2 · **Priority** 1.50 · **Depends on** — · **Type** Required · **Sprint** 1 · **Label** P0

As a visitor, I want to create an account with a username and password so that I can save my progress and appear on the leaderboard.

## Why
Every run, checkpoint, and leaderboard score belongs to a player, so nothing else in the game works without accounts. Registration is also a graded course requirement: −10 if it's broken.

## Scope
**In:** the registration page, account creation with a hashed password, automatic login after registering, and the database foundation (Docker Compose, PostgreSQL, SQLAlchemy, Alembic) that every later story uses.
**Out:** login and logout for returning players (US2), password reset and email (not planned), profile page (US14), rate limiting (not planned).

## Acceptance Criteria
1. **[HIGH]** Given that I am on the registration page, when I submit a unique username, a password of at least 8 characters, and a matching confirmation, then my account is created with a hashed password, I am logged in, and I am taken to the home screen.
2. **[HIGH]** Given that the username is already taken or my input is invalid, when I submit the form, then I see a clear error message and no account is created.
3. **[MED] (proposed)** Given that I enter a username that differs from an existing one only by letter case (`Tyler` vs `tyler`), when I submit, then it's treated as taken.
4. **[HIGH] (proposed)** Given that the registration form is submitted without a valid CSRF token, when the server receives it, then it's rejected and no account is created.
5. **[MED] (proposed)** Given that I am already logged in, when I open the registration page, then I am redirected to the home screen.
6. **[LOW] (proposed)** Page layout, field order, and the welcome message after registering.

## Rules & Details
| Field | Rule | Error message (exact) |
| --- | --- | --- |
| Username | Trimmed, then 3–20 characters: letters, digits, `_` | "Username must be 3–20 characters: letters, numbers, or underscores." |
| Username | Unique, ignoring case | "That username is taken." |
| Password | 8–128 characters, any characters, no other complexity rules | "Password must be at least 8 characters." (and "Password must be 128 characters or fewer.") |
| Confirm password | Must equal Password | "Passwords don't match." |

- The username is stored as typed (`Tyler`), and uniqueness is checked case-insensitively.
- Passwords are hashed with Werkzeug `generate_password_hash` (its default, scrypt). Plain-text passwords are never stored, logged, or put back into the form after an error.
- If two people register the same name at the same instant, the database's unique constraint wins and the loser sees "That username is taken." (no 500 error).
- After a successful registration the player is logged in (Flask-Login) and redirected to `/`.
- On error, the form re-renders with the username kept and both password fields cleared.

## UI
- **Route:** `GET /register` shows the form. `POST /register` submits it. The home and login pages link to it.
- **Elements:** `register-username`, `register-password`, `register-confirm`, `register-submit`, `register-error` (one per field error, next to its field), `register-login-link` ("Already have an account? Log in").
- **Home after registering:** shows `home-username` (the logged-in name). The full home screen comes with US2/US3.
- Styled with design tokens only (task T3).

## Technical Notes
- **Presentation:** `src/presentation/auth_routes.py` (blueprint `auth`), `forms.py` (`RegistrationForm`, Flask-WTF), `templates/auth/register.html` extending `base.html`.
- **Business:** `src/business/auth_service.py`: `AuthService.register(username, password, confirm) -> User`. Raises `RegistrationError(field, message)`. Services never import Flask.
- **Data:** `User` model (`id`, `username`, `password_hash`, `created_at`) + Alembic migration with a unique index on `lower(username)`. `UserRepository.get_by_username(name)` (case-insensitive) and `add(user)`.
- **Config:** `SECRET_KEY` and `DATABASE_URL` from the environment (`.env.example` has safe local defaults).

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | `AuthService.register` creates a user with a hashed password (the hash ≠ the password and verifies) | unit |
| 1 | `POST /register` with valid data → 302 to `/`, user in DB, session logged in | integration |
| 1 | Fill in the form → land on home showing the username | e2e |
| 2 | One test per rule in the table above (short, long, bad characters, taken, short password, mismatch) | unit |
| 2 | `POST /register` with a taken name → 200, error shown, user count unchanged | integration |
| 2 | Register a duplicate in the browser → `register-error` visible | e2e |
| 3 | Register `Tyler` after `tyler` → taken | unit + integration |
| 4 | With CSRF enabled, a POST without a token → 400, no user | integration |
| 5 | Logged-in `GET /register` → 302 to `/` | integration |

## Tasks
- [ ] T1: US1: Add Docker Compose (web + db)
- [ ] T2: US1: Add the data layer (SQLAlchemy, Alembic, repositories)
- [ ] T3: US1: Add design tokens, base layout, and design rules doc
- [ ] T4: US1: User model and registration

## Open Questions
- None.
