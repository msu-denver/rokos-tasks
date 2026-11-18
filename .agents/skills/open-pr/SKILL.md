---
name: open-pr
description: Run every pre-PR gate for Roko's Tasks (make check, self-review, manual test and screenshot) and open a draft PR in the team format. Use whenever you are about to open a pull request.
---

# Open a PR

Don't skip steps. If a step fails, fix the problem and start that step
again. If a step can't run yet (Sprint 0 has no `make check`), write
"not available yet" in the checklist. Never claim it passed.

## 1. Preflight

- `git branch --show-current` is a feature/fix/chore/docs/debt branch,
  not `main` or `dev`.
- `git fetch origin && git merge origin/dev`. Resolve any conflicts.
- `git status` is clean: everything is committed, and there's no `.env`
  or secrets in the diff.

## 2. Gate 1: checks

`make check`. Everything must pass, including Selenium and coverage of
at least 90%. Paste nothing from it into the PR. Just tick the box.

## 3. Gate 2: self-review

Run [team-review](../team-review/SKILL.md) on your own diff, unless you
already did and haven't changed anything since. Every finding must be
fixed or deferred to a linked tech-debt issue. HIGHs must be fixed.
Rerun `make check` after fixing.

## 4. Gate 3: manual test

- Run the app (`make up` or `make dev`) and use the change for real.
- Save **one** screenshot to `.pr/screenshot.png`.
- Write the one-sentence Manual Testing line (what you did and what
  happened). See the examples in
  [pull-requests.md](../../pull-requests.md).

## 5. Write the body

Write `.pr/body.md` from
[.github/pull_request_template.md](../../../.github/pull_request_template.md).
Fill in every section. Leave the screenshot placeholder exactly as:
`<!-- SCREENSHOT: drag .pr/screenshot.png here -->`.
Fill in the author line, for example `Author: Jane Doe with Claude Opus 5.5`.

## 6. Open as a draft

```bash
git push -u origin HEAD
gh pr create --draft --base dev --title "<type>(US#): <summary>" --body-file .pr/body.md
```

## 7. Hand off

Tell your human, word for word:

> Draft PR opened: <url>. Drag `.pr/screenshot.png` into the Manual
> Testing section, check that the sentence matches, then click
> **Ready for review**.

Never mark the PR ready, request reviewers, or merge it yourself.
