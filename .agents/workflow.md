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
- **Start the issue** before writing code:
  1. Assign yourself: `gh issue edit <n> --add-assignee @me`.
  2. Create the branch **from the issue** so GitHub links it (it shows
     under the issue's **Development**):
     `gh issue develop <n> --base dev --name <branch> --checkout`, or
     **Create a branch** on the issue page.
  3. Name it `<type>/<issue#>-<short-name>`, where type is `feature`,
     `fix`, `chore`, `docs`, or `debt`. Examples:
     `feature/14-US6-runner-sandbox`, `fix/21-checkpoint-restore`,
     `debt/30-flaky-timer-test`.

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
- Recommended: review with a *different model* than the one that wrote
  the code. Different models miss different things. Any tool works: in
  Copilot Chat, pick another model in the model picker before running
  the review; with other agents, use whichever second model you have.

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

- Follow [skills/open-pr](skills/open-pr/SKILL.md) to open a **draft**
  against `dev` in the standard format. Draft status is mandatory when
  the user has yet to attach the manual-testing screenshot in the
  current agent chat, including for stacked PRs and handoffs that ask
  for a regular PR.
- Tell the user the PR stays in draft until they attach the screenshot
  in chat or add it under **Manual Testing** on GitHub. The human marks
  it ready once the screenshot appears in the PR and matches the test.
- Request reviews from the team roster using the actual PR author to
  determine who to exclude. Include pending requests in the handoff
  if GitHub blocks them while the PR is a draft.
  See [reviewer selection](pull-requests.md#reviewers).

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

## 8. After merge: close the issue

PRs go into `dev`, which isn't the repo's default branch, so GitHub
ignores `Closes #n` and never closes the issue. The author's agent
closes it instead.

1. **When:** at the start of every session, and whenever your human
   says a PR merged.
2. **Find your human's merged PRs** (`@me` is whoever `gh` is logged
   in as):
   `gh pr list --base dev --state merged --author @me --limit 20 --json number,body`
3. **For each `Closes #n` line** in a PR body, check the issue with
   `gh issue view <n> --json state`. If it's still open, close it:
   `gh issue close <n> --reason completed --comment "Done in #<pr>, merged into dev."`
4. **Only close** issues listed as `Closes #n` in a PR that merged and
   that your human authored. Leave issues from someone else's PR, from a
   PR closed without merging, and issues a PR only mentions.

## Agents never

- Push to `main` or `dev`, or force-push a branch someone else uses.
- Merge, approve, or mark a PR ready for review.
- Close an issue before its PR merges, or one from someone else's PR
  (see [§8](#8-after-merge-close-the-issue)).
- Make live LLM calls ([llm-policy.md](llm-policy.md)).
