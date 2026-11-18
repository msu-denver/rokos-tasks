**Value** 3 · **Points** 2 · **Priority** 1.50 · **Depends on** US1 · **Type** Required · **Sprint** 1

As a registered player, I want to log in and log out so that I can play and score under my own account.

## Why
Returning players need to get back to their account, and every game page must know who is playing. Login is a graded course requirement: −10 if it's broken.

## Scope
**In:** login and logout, the shared header with the player's name and a Log Out button, and protecting game pages so only logged-in players reach them.
**Out:** registration (US1), password reset (not planned), account lockout and rate limiting (not planned), the start screen's content (US3).

## Acceptance Criteria
1. **[HIGH]** Given that I have an account, when I enter the correct username and password, then I am logged in and see the home screen.
2. **[HIGH]** Given that I enter a wrong username or password, when I submit the form, then I see "Invalid username or password." and remain logged out.
3. **[HIGH]** Given that I am logged in, when I click Log Out, then my session ends and any game page redirects me to the login page.
4. **[MED] (proposed)** Given that I tried to open a protected page while logged out, when I log in, then I am sent back to the page I asked for. This only works for pages on our own site, never an outside URL.
5. **[MED] (proposed)** Given that I am already logged in, when I open the login page, then I am redirected to the home screen.
6. **[LOW] (proposed)** Whether to offer "Remember me."

## Rules & Details
- Username lookup ignores case (`TYLER` logs into `Tyler`). The password is checked with `check_password_hash`.
- A wrong username and a wrong password show the **same** message, "Invalid username or password.", so the form never reveals which usernames exist.
- Protected pages (the start screen and every `/play/...` page) redirect logged-out visitors to `/login?next=<path>` with the flash message "Please log in to continue."
- `next` is followed only if it's a relative path on this site (starts with `/`, not `//`). Anything else goes to `/`, which prevents an open redirect.
- Logout is a **POST** with a CSRF token (a plain link could be triggered by another site), then redirects to `/login` with the flash message "You've been logged out."
- Session cookie: `HttpOnly`, `SameSite=Lax`, signed with `SECRET_KEY`.

## UI
- **Routes:** `GET/POST /login`, `POST /logout`.
- **Login elements:** `login-username`, `login-password`, `login-submit`, `login-error`, `login-register-link` ("New here? Create an account").
- **Header (in `base.html`, every page):** when logged in, `header-username` and the `header-logout` button. When logged out, `header-login` and `header-register` links.
- **Flash messages:** `flash-message`.

## Technical Notes
- **Presentation:** add `login`/`logout` to `auth_routes.py`, `LoginForm` in `forms.py`, `templates/auth/login.html`. Set up `LoginManager` in `app.py` with `login_view = "auth.login"`.
- **Business:** `AuthService.authenticate(username, password) -> User | None`, plus a small `is_safe_redirect(target) -> bool` helper (pure function, easy to unit-test).
- **Data:** `UserRepository.get_by_id(id)` for the Flask-Login `user_loader`.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | `authenticate` with correct credentials returns the user (any case of the username) | unit |
| 1 | `POST /login` valid → 302 to `/`, session set | integration |
| 1, 3 | Log in → header shows username → Log Out → open `/start` → login page | e2e |
| 2 | `authenticate` returns `None` for an unknown user and for a wrong password | unit |
| 2 | Both failures render the identical message | integration |
| 3 | After `POST /logout`, `GET /start` → 302 to `/login` | integration |
| 4 | `is_safe_redirect` accepts `/play/3`, rejects `https://evil.com`, `//evil.com`, `javascript:` | unit |
| 4 | `/login?next=/start` → after login lands on `/start` | integration |
| 5 | Logged-in `GET /login` → 302 to `/` | integration |

## Tasks
- [ ] T5: US2: Login, logout, and protected pages

## Open Questions
- None.
