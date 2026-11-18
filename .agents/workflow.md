# Workflow: Issue to Merged PR

Every agent follows these steps, whichever tool you are and whoever
you're working for.

## 1. Start from an issue

- Every change starts from a GitHub issue: `gh issue view <n>`. If there
  is no issue, stop and ask your human. You can draft one for them using
  [tickets.md](tickets.md).
- Read every acceptance criterion **and its rating** before writing code:
  - **[HIGH]** must be met exactly.
  - **[MED]** should be met. If you deviate, explain why in the PR.
  - **[LOW]** is your call. Pick the simplest reasonable option.
- If an AC is ambiguous or has no rating, ask your human. Don't guess at
  a HIGH.
- Branch from the latest `dev`, named for the story:
  `feature/US6-runner-sandbox`, `fix/US7-checkpoint-restore`,
  `chore/sprint0-devcontainer`, `docs/...`, `debt/<issue#>-short-name`.

## 2. Build

- Keep PRs small: aim for under ~400 changed lines, excluding generated
  files. Split bigger work into several issues and PRs.
- Write tests in the same change as the code ([testing.md](testing.md)).
- Commit early and often:
  `feat(US6): add CPU and memory limits to runner (#14)`.
  Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`.

## 3. Gate 1: checks are green

- Run `make check`. Lint, every test (Selenium included), coverage of
  at least 90%, and campaign validation must all pass.
- Never get to green by skipping, deleting, or loosening tests, or by
  adding `# noqa` / `# pragma: no cover` without a comment saying why.

## 4. Gate 2: self-review (at least one round)

- Follow [skills/team-review](skills/team-review/SKILL.md) on your own
  diff (`git diff origin/dev...HEAD`) with the rubric in
  [code-review.md](code-review.md).
- **Address every finding** before the PR:
  - **HIGH:** fix it. No exceptions.
  - **MED / LOW / NIT:** fix it. If the fix is truly out of scope, open
    a `tech-debt` issue and link it in the PR.
- Rerun `make check` after your fixes.
- If round 1 found any HIGH, do a round 2 to confirm the fixes.
- Recommended: have a *different* tool or model do the review than the
  one that wrote the code (for example, Claude writes and Codex reviews).
  Different models miss different things.

## 5. Gate 3: manual test + one screenshot

- Run the app (`make up` or `make dev`) and use the change the way a
  player or developer would.
- Save **one** screenshot of the result to `.pr/screenshot.png`
  (gitignored). Take it with Selenium (`driver.save_screenshot`), your
  tool's browser, or a screen capture. For backend-only changes,
  screenshot the terminal showing the command and its output. For
  docs-only changes, screenshot the rendered page.
- Write the **one-sentence** Manual Testing line. Rules and examples are
  in [pull-requests.md](pull-requests.md).

## 6. Open the PR as a draft

- Follow [skills/open-pr](skills/open-pr/SKILL.md): base `dev`, the
  standard format, opened as a **draft**.
- Agents can't upload images to GitHub. Tell your human: "Drag
  `.pr/screenshot.png` into the Manual Testing section, check it, then
  mark the PR ready for review."
- Move the board card to **In Review** once the PR is ready.

## 7. After review

- Reply to every review comment.
  - **HIGH:** fix, push, and reply with the commit.
  - **MED/LOW the reviewer deferred:** make sure the `tech-debt` issue
    exists and is linked. Then resolve the thread.
  - **NIT:** fix it or reply "won't fix" with a reason. Either is fine.
- Before asking for another review, rerun `make check` and self-review
  the new commits.
- A human merges with a **merge commit** (never squash, because the
  course grades commit history).

## Agents never

- Push to `main` or `dev`, or force-push a branch someone else uses.
- Merge, approve, or mark a PR ready for review.
- Close issues by hand (use `Closes #n` in the PR body).
- Make live LLM calls ([llm-policy.md](llm-policy.md)).
