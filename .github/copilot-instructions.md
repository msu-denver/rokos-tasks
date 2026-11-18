# Copilot instructions

Read and follow [AGENTS.md](../AGENTS.md) and the `.agents/` docs it
links. They are the team's single source of truth. If anything here
disagrees with AGENTS.md, AGENTS.md wins.

The short version, for code review and chat:

- **Never make live LLM calls.** No `LLM_MODE=live`, no
  `make llm-smoke` or `make generate-campaigns`, no `CONFIRM_LIVE=yes`,
  no reading `.env`. Test with `fake`/`replay` or a mocked client.
- **Before any PR:** `make check` passes (all tests incl. Selenium, coverage
  ≥ 90%), at least one self-review round with every finding
  addressed, and a manual test with one screenshot. PRs go into `dev`
  as drafts.
- **Layers:** routes → services → repositories. Services never import
  Flask. Only repositories query the DB. Every source file has the
  header comment (description + human authors).
- **UI:** follow `docs/design.md`. Use design tokens, never hard-coded
  colors or fonts. Prompts are plain text. No helper text or emoji.

## When reviewing a PR

Rate every finding **HIGH / MED / LOW / NIT**, one per comment:
`**[SEVERITY]** path:line: problem. **Fix:** suggestion.`

- **HIGH** (always blocks): bugs, an unmet [HIGH] acceptance criterion,
  missing or failing tests, coverage < 90%, security problems, breaking
  any AGENTS.md rule, or a PR body missing `## Manual Testing` with one
  sentence and exactly one screenshot.
- **MED/LOW** block only if they will break upcoming code or must be
  fixed now. Otherwise, suggest a `tech-debt` issue.
- **NIT** never blocks.
- In later rounds, only comment on new commits, unless the finding is
  HIGH.

Full rubric: [.agents/code-review.md](../.agents/code-review.md).
