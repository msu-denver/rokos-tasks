---
name: team-review
description: Review code for Roko's Tasks with the team HIGH/MED/LOW/NIT rubric. Use for the mandatory self-review before opening any PR, and when asked to review a teammate's PR.
---

# Team Review

The rubric is in [.agents/code-review.md](../../code-review.md). Read it
first. This file is the procedure.

## 1. Get the target

- **Self-review (your own branch):**
  `git fetch origin dev && git diff origin/dev...HEAD`. Get the issue
  number from the branch name or commits, then run `gh issue view <n>`.
- **Someone else's PR:** `gh pr view <n>`, `gh pr diff <n>`, and the
  issue it links (`gh issue view <m>`).

## 2. Review in this order

1. **PR format** (PR mode only). `## Manual Testing` has one sentence
   and one image. If it doesn't, report one HIGH and stop.
2. **Acceptance criteria.** Go through every [HIGH] AC one at a time and
   say where in the diff it's satisfied. Unmet [HIGH] = HIGH. Unexplained
   [MED] deviation = MED.
3. **Correctness.** Error paths, empty input, boundaries, timeouts,
   concurrency, and DB transactions.
4. **Tests.** New behavior is tested, failure paths are tested,
   user-facing changes have an e2e test, and nothing was skipped or
   loosened.
5. **Non-negotiables** from [AGENTS.md](../../../AGENTS.md). Any
   violation = HIGH.
6. **Standards** from [coding-standards.md](../../coding-standards.md).
7. **Design** (UI changes only) against [docs/design.md](../../../docs/design.md).

Read the surrounding code, not just the diff lines. Report only real
problems. Rate each one honestly using the definitions in the rubric. Don't
inflate NITs into LOWs.

## 3. Report

Use the exact finding format from the rubric. Put the verdict summary
line first, then the findings sorted HIGH → NIT.

## 4. Then

- **Self-review:** fix every finding. For a non-HIGH you truly can't fix
  in scope, open a tech-debt issue
  (`gh issue create --label tech-debt --label P2 --title "Tech debt: …" --body-file
  <file>` using the fields in `.github/ISSUE_TEMPLATE/tech-debt.md`, or
  draft it for your human)
  and note its number. Rerun `make check`. If round 1 had a HIGH, run
  this skill again. Remember the counts for the PR checklist line:
  `Self-review done: <n> findings fixed · deferred: #<issue> or none`.
- **Someone else's PR:** post it with
  `gh pr review <n> --comment --body-file <file>`. Never `--approve`.
  Use `--request-changes` only if your human says to.
