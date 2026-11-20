@AGENTS.md

## Claude Code notes

- The team skills `/team-review` and `/open-pr` are in `.agents/skills/`
  (linked from `.claude/skills/`). Use them. Don't swap in the built-in
  `/code-review` or `/review` for `/team-review`. If you run one as an
  extra pass, convert its findings to HIGH/MED/LOW/NIT.
- `.claude/settings.json` blocks reading `.env` and the live LLM
  commands. Don't try to get around it.
- For the Manual Testing screenshot, use the built-in browser pane or
  Selenium, and save it to `.pr/screenshot.png`.
