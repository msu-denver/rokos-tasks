# Testing

## The bar

- `make check` must pass before any PR: lint, all tests, coverage, and
  campaign validation.
- **Coverage is at least 90%, line + branch, across `src/`**, from any
  mix of tests. It's enforced with `fail_under = 90` in `pyproject.toml`.
- **Selenium is required as well.** Every user-facing story gets e2e
  tests (rules below), whatever the coverage number says.

## Layout

| Folder | What | Notes |
| :--- | :--- | :--- |
| `tests/unit/` | Services, calculators, validators | Fast. No network. |
| `tests/integration/` | Flask test client, repositories against the Compose Postgres | A full stage pass/fail flow lives here |
| `tests/runner/` | Hostile-code suite for the sandbox | Never weaken it |
| `tests/e2e/` | **Selenium** browser tests (`@pytest.mark.e2e`) | Headless Chromium |

## Selenium (e2e) rules

- Every user-facing story gets at least one e2e test for each **[HIGH]**
  AC's main path.
- Use the shared `live_server` and `browser` fixtures in
  `tests/conftest.py`. Don't start your own server.
- Select elements by `data-testid` attributes, never by CSS layout or
  text that might change.
- Wait with `WebDriverWait` and expected conditions. Never use
  `time.sleep`.
- When a test fails, save a screenshot to `.pr/e2e-failures/`
  (gitignored).
- Monaco and Pyodide load from a CDN, so e2e tests need network access
  to the CDN. They never need it for anything else.

## Required labeled tests (course requirement; neither may test auth)

- **White-box:** `GradingService` verdict logic (pass, broken rule,
  crash, timeouts, first-failure stop), `@pytest.mark.whitebox`.
- **Black-box:** `ScoreCalculator` against the scoring rules in
  `docs/game-design.md` §3.3,
  `@pytest.mark.blackbox`.
- Each one gets a docstring stating its **purpose**, the
  **functionality tested**, and the **expected outcome**.

## LLM code

- Tests run in `fake` or `replay` mode, or with a **mocked** `openai`
  client. That's how `src/business/llm/` reaches 90%.
- Tests must pass with **no Azure environment variables set**.
- Recording new `replay` fixtures needs a live call, so only a human does
  that ([llm-policy.md](llm-policy.md)).

## Never

- Skip, `xfail`, delete, or loosen an assertion to get green.
- Lower `fail_under`.
- Add `# pragma: no cover` except on truly unreachable defensive
  branches or `if __name__ == "__main__":`, each with a comment saying
  why.
- Commit `htmlcov/` in feature PRs. It's regenerated and committed only
  in the release PR at the end of each sprint, which avoids merge
  conflicts. It's gitignored, so the release PR uses
  `git add -f htmlcov`. CI also uploads it as a run artifact on every
  PR.
