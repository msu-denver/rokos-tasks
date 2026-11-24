---
name: open-pr
description: Run every pre-PR gate for Roko's Tasks (make check, self-review, manual test and screenshot) and open a draft PR in the team format. Use whenever you are about to open a pull request.
---

# Open a PR

Don't skip steps. If a step fails, fix the problem and start that step
again. If a step's `make` target doesn't exist yet, write
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

Always pass `--draft` when the user has yet to attach the manual-testing
screenshot in the current agent chat. This applies to stacked PRs and
handoffs requesting a regular PR. Share the path to the saved image so
the user can attach it.

```bash
git push -u origin HEAD
gh pr create --draft --base dev --title "<type>(US#): <summary>" --body-file .pr/body.md
```

## 7. Request reviewers

Read the new PR's GitHub author login. Request reviews from every
applicable teammate using the
[reviewer roster and author exclusion rule](../../pull-requests.md#reviewers).
If GitHub blocks any requests while the PR is a draft, include the
pending handles in the handoff.

## 8. Hand off

When the screenshot is still pending, tell the user:

> I opened <url> as a draft. It stays in draft until you attach the
> manual-testing screenshot in this chat or add it under **Manual Testing**
> on GitHub. You can use `.pr/screenshot.png`. Once the screenshot is
> visible in the PR and matches the test, mark it **Ready for review**.

Never mark the PR ready or merge it yourself.
