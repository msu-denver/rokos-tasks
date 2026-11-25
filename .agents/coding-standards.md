# Coding Standards

Condensed from [docs/roadmap.md §6](../docs/roadmap.md#6-code-standards). Code
inspection is graded, so these aren't optional.

## Header comment (every source file; course requirement)

Python (the module docstring is the header):

```python
"""
File: score_calculator.py
Description: Calculates stage points, survival bonus, and total campaign
    score for leaderboard entries.
Author(s): Jane Doe, John Smith
"""
```

JavaScript/CSS: the same three fields in `/* ... */`. Jinja: in
`{# ... #}`.

**Author(s) lists the human teammate(s)** responsible for the file, never
the AI tool. If you substantially change a file, add your human's name.
`scripts/check_headers.py` fails lint when a header is missing.

## Style

- **Ruff** formatter + linter at **79 columns**. Rules: `E, W, F, N, D,
  B, I, UP`, with Google-style docstrings.
- **pycodestyle** is the reference PEP 8 check. (`E203` is ignored.)
- **Type hints** on every function signature. **Docstrings** on every
  public class and function.

## Quality

- **Naming:** `snake_case` for functions and variables, `PascalCase` for
  classes, `UPPER_CASE` for constants. No one-letter names outside short
  loops.
- **Functions:** each does one thing, in about 30 lines or fewer, with
  no deep nesting.
- **OOP:** domain logic lives in classes. Pass dependencies in
  (`GradingService(runner_client)`) rather than creating them inside.
- **Errors:** catch specific exceptions. Raise custom domain exceptions
  (`CampaignValidationError`, `RunnerUnavailableError`). Users see
  friendly messages, never stack traces. Log anything unexpected.
- **Comments** explain *why*, not *what*. No commented-out code.

## Layers (a non-negotiable)

| Layer | Path | May import |
| :--- | :--- | :--- |
| Presentation | `src/presentation/` | Business layer only |
| Business | `src/business/` | Data layer. **Never Flask.** |
| Data | `src/data/` | SQLAlchemy. **The only layer that runs queries.** |

## UI

All UI follows [docs/design.md](../docs/design.md): tokens from `tokens.css` (never hex values or font names in templates), the four fonts, the depth rules, and the Overlord feed. Read it before writing any template, CSS, or page JS.

## Consistency across agents

Before adding a new pattern (a helper, base class, error type, or
fixture), search for an existing one and reuse it. When an agent
introduces a second way to do the same thing, that's a MED finding.
