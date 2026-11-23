# Sprint 1 Issues: Draft for Critique

**Sprint 1:** 11/18–11/22 · **Goal:** a player can register, log in, start a run, see a stage, and run sample tests in the browser. · **Release:** `v1` on 11/22.

**How to read this:**
- There are 5 **story** issues (US1–US5), one file each in [issues/](issues/). Each one has the story points.
- There are 11 **task** issues, the actual work. Each is a GitHub sub-issue of its story, and none has points (points live on stories only, so the burndown doesn't count twice).
- Acceptance criteria marked **(proposed)** aren't in the README yet. They're proposals to settle wording or scope. Once agreed, copy the ratings and new criteria back into the README stories.
- Delete this file once the issues are posted. Its useful parts belong in `scrum/sprint_1/planning.md`.

## Contents
- [Stories](#stories) (one file each in [issues/](issues/))
- [Tasks](#tasks): [T1–T3 foundation](#t1-us1-add-docker-compose-web--db) · [T4–T5 accounts](#t4-us1-user-model-and-registration) · [T6–T8 campaigns and runs](#t6-us3-campaign-schema-difficulty-tiers-and-seed-loader) · [T9–T10 game page](#t9-us4-game-page-overlord-feed-lives-and-editor) · [T11 Scrum](#t11-scrum-sprint-0-and-1-notes-board-and-burndown)
- [Suggested split](#suggested-split)
- [Open questions](#open-questions)

---

## Stories

The full story issues are one file each, ready to post with `--body-file`. They follow [.agents/tickets.md](../../.agents/tickets.md).

| Issue | File | Points | Open questions |
| --- | --- | :---: | --- |
| US1: Register | [issues/US1.md](issues/US1.md) | 2 | None |
| US2: Log In and Log Out | [issues/US2.md](issues/US2.md) | 2 | None |
| US3: Choose a Difficulty and Start a Run | [issues/US3.md](issues/US3.md) | 3 | Seed count for `v1`; resume vs. block an active run |
| US4: View the Stage and Write Code | [issues/US4.md](issues/US4.md) | 3 | None |
| US5: Play My Program | [issues/US5.md](issues/US5.md) | 8 | Tick rate |

---

## Tasks

Every task also inherits the team gates: `make check` green, self-review, Manual Testing + screenshot. Those aren't repeated below.

### T1: US1: Add Docker Compose (web + db)
`task` · Sub-issue of US1
- **[HIGH]** `docker compose up --build` starts `web` (Flask via Gunicorn on port 8000) and `db` (PostgreSQL 17), and `/health` returns ok.
- **[HIGH]** `.env.example` lists every variable with safe defaults (`LLM_MODE=fake`). There's no real secret anywhere in the repo.
- **[MED]** The README Run It and Deployment sections work exactly as written on a clean clone.
- **[LOW]** Multi-arch images, layer caching.

### T2: US1: Add the data layer (SQLAlchemy, Alembic, repositories)
`task` · Sub-issue of US1 · Needs T1
- **[HIGH]** `src/data/database.py` provides the engine and session. Alembic is set up, and migrations run automatically when `web` starts.
- **[HIGH]** CI runs repository tests against a PostgreSQL service container (update `ci.yml`), not SQLite.
- **[MED]** Each test runs in a transaction that's rolled back, so tests don't affect each other.
- **[LOW]** Base repository class shape.

### T3: US1: Add design tokens, base layout, and design rules doc
`task` · Sub-issue of US1 (the first screen with UI)
- **[HIGH]** `src/presentation/static/css/tokens.css` defines every color, font, spacing, and radius as CSS variables, seeded from the values in `docs/design.md`. **The values live only in this file.**
- **[HIGH]** `base.html` (the Jinja layout every page extends) loads `tokens.css` and the shared component styles.
- **[HIGH]** `docs/design.md` (drafted 2026-11-18; fonts decided) has its top bar confirmed, and refers to tokens by name only once `tokens.css` exists. AGENTS.md links to it.
- **[MED]** No page or component hard-codes a color or font. Reviews treat a hard-coded value as a MED finding.
- **[LOW]** Exact component styles beyond design 6 on the design canvas.

### T4: US1: User model and registration
`task` · Sub-issue of US1 · Needs T2, T3
- **[HIGH]** `User` model + migration, `UserRepository`, and `AuthService.register()`. Passwords are hashed with Werkzeug, never stored or logged in plain text.
- **[HIGH]** `/register` form uses Flask-WTF with CSRF protection and shows field errors.
- **[HIGH]** Unit tests for the service rules, integration tests for the route, and a Selenium test for US1 AC1 and AC2.
- **[MED]** Username rules from US1 AC3, with case-insensitive uniqueness enforced in the database (not just in Python).

### T5: US2: Login, logout, and protected pages
`task` · Sub-issue of US2 · Needs T4
- **[HIGH]** Flask-Login session. `/login` and `/logout` routes. A `login_required` page redirects to `/login`.
- **[HIGH]** A wrong username and a wrong password show the same message, so the form doesn't reveal which usernames exist.
- **[HIGH]** A Selenium test covers log in → home → log out → protected page redirects.
- **[MED]** A shared home screen template with the logged-in username and a Log Out button.

### T6: US3: Campaign schema, difficulty tiers, and seed loader
`task` · Sub-issue of US3 · Needs T2
- **[HIGH]** `Difficulty` with the six tiers and their rules (stages, minutes, lives, multiplier) exactly as in game-design §3.1.
- **[HIGH]** `Campaign`, `Stage`, and `TestCase` models + migration, plus a JSON schema matching game-design §4.7.
- **[HIGH]** `make seed` loads `content/campaigns/seed/**.json`, and `make validate-campaigns` rejects files that don't match the schema. `make check` runs `validate-campaigns`.
- **[MED]** The loader is idempotent (running it twice doesn't duplicate anything).
- **[LOW]** Whether the JSON schema is hand-written or generated from the models.

### T7: US3: Write the first seed campaigns
`task` · Sub-issue of US3 · Needs T6
- **[HIGH]** At least one Beginner campaign and one Easy campaign, each with a reference solution that passes every hidden test.
- **[HIGH]** Every stage has an exact input/output contract and 1–2 samples. Expected outputs are produced by running the reference solution, never typed by hand.
- **[HIGH]** Each stage's `prompt` is plain text that states the exact input/output format and at least one example, and every `samples` entry appears in the prompt (game-design §1, §2.2). `make validate-campaigns` checks this.
- **[LOW]** Which projects (game-design §3.1 has examples).

### T8: US3: Start screen and start-run flow
`task` · Sub-issue of US3 · Needs T5, T6
- **[HIGH]** `GameRun` model + migration, and `GameService.start_run()` assigns a campaign per US3 AC2.
- **[HIGH]** The start screen shows all six tiers (US3 AC1), with empty tiers marked "Coming soon" (US3 AC3).
- **[HIGH]** A Selenium test covers choose tier → Start → Stage 1 opens.
- **[MED]** Assignment logic is unit-tested for unplayed, all-played, and empty-tier cases.

### T9: US4: Game page: Overlord feed, lives, and editor
`task` · Sub-issue of US4 · Needs T8
- **[HIGH]** The game page shows the Overlord feed with the prompt as its first message, plus lives and the editor (US4 AC1), with Monaco loaded from a pinned CDN version.
- **[HIGH]** JS is split into ES modules under `static/js/` (`editor.js`, `feed.js`, `api.js`, and the `game.js` entry), with no build step (roadmap §3).
- **[HIGH]** In-progress code survives a refresh (US4 AC3), and a Selenium test proves it.
- **[MED]** Layout follows `docs/design.md` (design 6) and uses only design tokens (T3).

### T10: US5: Run Sample in the browser with Pyodide
`task` · Sub-issue of US5 · Needs T9
- **[HIGH]** `pyodide_worker.js` runs the code in a Web Worker against each sample, feeding stdin and capturing stdout/stderr. Results show pass/fail with the expected vs. actual output.
- **[HIGH]** After 5 s, the worker is terminated and restarted, and a friendly timeout message appears (US5 AC2).
- **[HIGH]** Selenium tests cover a passing sample, a failing sample, an error traceback, and the infinite-loop timeout.
- **[MED]** The Pyodide version is pinned and its Python version is recorded in the README (US5 AC3).

### T11: Scrum: Sprint 0 and 1 notes, board, and burndown
`task` · No story (process)
- **[HIGH]** `scrum/sprint_0/` and `scrum/sprint_1/` use the course templates: planning, daily scrums, review, retrospective, board screenshot.
- **[HIGH]** The GitHub Project board has the To Do / In Progress / In Review / Done columns and the Sprint, Story Points, User Value, and Type fields, and every issue above is on it.
- **[MED]** `scrum/burndown.csv` + `make burndown` draw the ideal and actual lines into `pics/burndown.png`.

---

## Suggested split

| Who | Tasks | Notes |
| --- | --- | --- |
| Tyler | T1 → T2 → T4 → T5 → T8 | Your US1–US3 path for today and tomorrow. T1/T2 first, because everything needs the database. |
| Teammate A | T3, then T9 | Design system first, so every screen uses it. |
| Teammate B | T6 → T7 | Schema + content. Writing the seed campaigns is human work, and it's slow. |
| Teammate C | T10, T11 | Pyodide can be built on a static test page before T9 lands. |

## Open questions

1. **Runner sandbox (US6) is 8 points in a Thanksgiving week.** Should the runner owner start the container skeleton in Sprint 1 if they have spare time? (It wouldn't count toward Sprint 1 points.)
2. **Seed content:** is one Beginner + one Easy campaign enough for `v1`, or do you want one per tier (Medium+ shown as "Coming soon" until the LLM fills them in)?
3. ~~**Wireframe:**~~ Resolved: `docs/design.md` and the design canvas replace `wireframes/game.html` as the design reference.
