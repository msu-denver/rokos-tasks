# GitHub Setup

**What this doc is:** the GitHub repo settings that enforce our rules (branch protection, merge method, labels, required checks), what's already applied, and what's left. The rules themselves are in [AGENTS.md](../AGENTS.md) and [.agents/](../.agents/).

## Contents
1. [Done (2026-11-18)](#done-2026-11-18)
2. [Next: Make the Checks Required](#next-make-the-checks-required)
3. [Optional](#optional)
4. [How GitHub Matches Our Review Rules](#how-github-matches-our-review-rules)

---

## Done (2026-11-18)

- `main`: PR required, 1 approval, `only-dev-into-main` status check, no
  force pushes or deletions, admins included, **conversation resolution
  required**.
- `dev`: PR required, 1 approval, no force pushes or deletions, admins
  included, **conversation resolution required**.
- Repo: **merge commits only** (squash and rebase off), and **head
  branches auto-delete** after merge. Protected branches such as `dev`
  are never auto-deleted.
- Labels `story`, `task`, and `tech-debt` exist.
- Workflows written: `.github/workflows/ci.yml` (job `check`: lint,
  header check, every test including Selenium, coverage of at least
  90%) and `.github/workflows/pr-format.yml` (job `pr-format`).
- Actions are free here because the repo is public. Nobody's personal
  minutes are spent.

## Next: Make the Checks Required

Once the PR that adds both workflows is merged into `dev` (GitHub only
offers checks that have already run), add **`check`** and **`pr-format`**
as required status checks on `dev` and `main`.

Watch for this: `pr-format` runs from the base branch's copy of the
workflow, so it won't run on the PR that adds it. That PR's checks are
expected to show only `check`.

## Optional

- `CODEOWNERS`: the Scrum Master owns `AGENTS.md`, `CLAUDE.md`,
  `GEMINI.md`, `.agents/`, and `.github/`, with **Require review from
  Code Owners** turned on. This needs everyone's GitHub usernames.

## How GitHub matches our review rules

A **"Request changes"** review blocks merge until that reviewer
re-reviews or the review is dismissed. So HIGH = Request changes, and
everything else = Approve or Comment. "Conversation resolution required"
means every finding gets a reply or a fix before merge.
