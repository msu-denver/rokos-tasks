# AGENTS.md: Roko's Tasks

This is the single source of truth for every AI coding agent on this repo:
Claude Code, Gemini CLI, Codex, Copilot, and any other. `CLAUDE.md`,
`GEMINI.md`, and `.github/copilot-instructions.md` all point here. If
anything else disagrees with this file, this file wins.

Read this whole file at the start of every session. Then read the
`.agents/` doc for whatever you are about to do (table at the bottom).

## What we're building

A comedic coding game: an AI Overlord gives timed, incremental feature
requests, the human player writes a Python program for each one, and
the Overlord grades it by playing the program. Flask + Jinja (three layers), PostgreSQL, a sandboxed
`runner` container, Docker Compose. Game design: [docs/game-design.md](docs/game-design.md).
Build plan, stack, and layout: [docs/roadmap.md](docs/roadmap.md). User
stories: [README.md](README.md#user-stories).

**Current phase:** see the open sprint's issues (`gh issue list`).
Use Python 3.13 (`make check PYTHON=.venv/bin/python` if your `python3`
is a different version). If a gate's `make` target doesn't exist yet,
say "not available yet" for that gate. Don't pretend it passed.

## Commands

| Command | Use |
| :--- | :--- |
| `make check` | Lint, all tests (Selenium included), coverage ≥ 90%, campaign validation. **Must pass before any PR.** |
| `make lint` / `make fmt` | Ruff + pycodestyle + header check / auto-format |
| `make test` / `make coverage` | pytest / pytest under coverage → `htmlcov/` |
| `make up` / `make dev` | Full stack in Docker / Flask with auto-reload (for manual testing) |
| `make llm-smoke`, `make generate-campaigns` | **Forbidden for agents.** Live paid API calls. |

## Non-negotiables

Breaking any of these is a **HIGH** review finding and blocks merge.

1. **No LLM API calls. Ever.** We have $100 of Azure credit for the whole
   project. Agents never set `LLM_MODE=live`, never run the live `make`
   targets, never set `CONFIRM_LIVE=yes`, never call the Azure/OpenAI
   endpoint by any route (script, curl, REPL), and never read `.env` or
   keys. Writing code that *will* call the API is fine; testing it uses
   `fake`/`replay` mode or a mocked client. Live runs are done only by a
   human, under supervision. Details: [.agents/llm-policy.md](.agents/llm-policy.md).
2. **Pass every gate before opening a PR**, in this order:
   1. `make check` is green: lint, tests (Selenium included), and
      **≥ 90% coverage**.
   2. **At least one self-review round** using the team rubric, with
      **every finding addressed** (fixed, or for non-HIGH, moved to a
      linked tech-debt issue). HIGHs are always fixed.
   3. **Manual test done**, with one sentence describing it and
      **one screenshot** saved.
   4. The PR uses the standard format, including `## Manual Testing`.

   Run all of it with [.agents/skills/open-pr/SKILL.md](.agents/skills/open-pr/SKILL.md).
3. **Never push to `main` or `dev`.** Branch from `dev`, open the PR into
   `dev`, and open it as a **draft**. A human attaches the screenshot,
   checks it, and marks it ready. Agents never merge, never approve, and
   never mark a PR ready for review.
4. **Every behavior change ships with tests** in the same PR. Never skip,
   delete, or loosen a test, and never lower the coverage threshold, to
   get green.
5. **Three layers:** routes → services → repositories. Routes never touch
   the database. Services never import Flask. Only repositories run queries.
6. **Header comment on every source file** (description + human
   author(s)), plus PEP 8 via Ruff at 79 columns, and docstrings and type
   hints on public functions. See [.agents/coding-standards.md](.agents/coding-standards.md).
7. **Secrets:** never read, print, or commit `.env` or any key. Only
   `.env.example` (names only) is committed.
8. **Hands off:** never hand-edit `htmlcov/`, and never loosen a
   campaign's `check_script` to make a program pass. Never weaken runner limits or isolation. Don't edit
   `AGENTS.md`, `.agents/`, the roadmap, or Scrum notes unless the issue
   says to.

## Workflow at a glance

```
issue → branch from dev → build + tests → make check → self-review → fix
→ manual test + screenshot → draft PR → human adds screenshot, marks ready
→ peer review (HIGH/MED/LOW/NIT) → human merges with a merge commit
→ agent closes the issue (dev isn't the default branch, so GitHub won't)
```

Full steps: [.agents/workflow.md](.agents/workflow.md).

## Reviews in one paragraph

Findings are rated **HIGH / MED / LOW / NIT**. **HIGH always blocks.**
MED and LOW block ("Request changes") only when they will break upcoming
code or must be fixed now. Otherwise the reviewer approves and opens a
`tech-debt` issue, so review doesn't ping-pong. NIT never blocks. Raise
everything in the first review. Later rounds only check the fixes and the
new commits. Full rubric: [.agents/code-review.md](.agents/code-review.md).

## Acceptance criteria in one paragraph

Every acceptance criterion on every ticket is rated **[HIGH]**
(set in stone), **[MED]** (expected; any deviation is explained in the
PR), or **[LOW]** (the implementer's call, human or agent). Read the
ratings before you write code. Details: [.agents/tickets.md](.agents/tickets.md).

## UI in one paragraph

Every screen follows [docs/design.md](docs/design.md). **Read it before
writing any template, CSS, page JS, SVG, or Overlord line.** Colors, fonts,
and sizes come from design tokens, never hard-coded values. Stage prompts
are plain text in the Overlord's feed. No helper text, emoji, or cartoon
styling. Reviewers rate a hard-coded value as MED
([code-review.md](.agents/code-review.md)).

## Architecture map

| Path | Owns |
| :--- | :--- |
| `src/presentation/` | Flask blueprints, forms, Jinja templates, static JS/CSS |
| `src/business/` | Services, grading, scoring, campaign validation, `llm/` (US11) |
| `src/data/` | SQLAlchemy models, repositories, Alembic migrations |
| `src/runner/` | Sandbox service in its own container. **Security-sensitive.** |
| `content/` | Seed campaigns (JSON) and Overlord dialogue (YAML) |
| `tests/` | `unit/`, `integration/`, `runner/`, `e2e/` (Selenium) |

## Where to read more

| Doing this | Read |
| :--- | :--- |
| Any task, start to finish | [.agents/workflow.md](.agents/workflow.md) |
| Writing or reviewing code | [.agents/code-review.md](.agents/code-review.md), [.agents/coding-standards.md](.agents/coding-standards.md) |
| Building or changing any UI: templates, CSS, page JS, SVG, Overlord lines | [docs/design.md](docs/design.md). Read it **before** writing markup. |
| Writing tests | [.agents/testing.md](.agents/testing.md) |
| Opening a PR | [.agents/pull-requests.md](.agents/pull-requests.md) |
| Creating an issue or tech-debt ticket | [.agents/tickets.md](.agents/tickets.md) |
| Anything touching `src/business/llm/` | [.agents/llm-policy.md](.agents/llm-policy.md) |

Skills (step-by-step procedures any agent can follow):
[.agents/skills/team-review](.agents/skills/team-review/SKILL.md) and
[.agents/skills/open-pr](.agents/skills/open-pr/SKILL.md). Some tools find
these automatically. If yours doesn't, open the file and follow it.

Task status lives in GitHub Issues (`gh issue view <n>`), never in
these files.
