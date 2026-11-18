# Pull Requests

Every PR uses the same format: [.github/pull_request_template.md](../.github/pull_request_template.md).
Keep it short. Reviewers should get the whole picture in 30 seconds.

## Title

Same style as commits: `feat(US6): add CPU and memory limits to runner`.

## Body

```markdown
Closes #<issue>

## Summary
<1–2 sentences: what this does and why.>

## Changes
- <One bullet per meaningful change. Not a file list.>

## How to Review
1. <Where to start reading, and what to run or click to see it work.>

## Manual Testing
<ONE sentence: what you did and what happened.>

<exactly one screenshot>

## Checklist
- [ ] `make check` passes (lint, tests incl. Selenium, coverage ≥ 90%)
- [ ] Self-review done: <n> findings fixed · deferred: #<issue> or none
- [ ] All [HIGH] acceptance criteria met · [MED] deviations: <none or explanation>
- [ ] No live LLM calls, no secrets
- Author: <human> with <agent/model, or "no agent">
```

## Manual Testing rules (automatic reject if broken)

- The `## Manual Testing` heading is present, spelled exactly like that.
- It has **one sentence or less**, saying **what was done** and **what
  happened**.
- It has **exactly one screenshot** of the thing that was tested.
- A reviewer who finds any of these missing requests changes right away
  without reviewing further. It's a HIGH finding.

| ✅ Good | ❌ Bad |
| :--- | :--- |
| Registered `tester1` with an 8-char password in Chrome and landed on the home screen logged in. | Tested it, works. |
| Submitted a solution with a trailing newline on Stage 2 and got "All tests passed" with lives unchanged. | Ran the tests. All pass. Also checked the UI and it looks good. Fixed a typo too. |
| Ran `make validate-campaigns` on the new Easy campaign and it reported 0 errors. | See screenshot. |

Passing automated tests don't count as manual testing. The point is that
someone actually used the change.

## Screenshot

1. Save the manual-testing screenshot to `.pr/screenshot.png`
   (gitignored). Leave `<!-- SCREENSHOT: drag .pr/screenshot.png here -->`
   under Manual Testing while the image is pending.
2. **If the user has yet to attach the screenshot in the current agent
   chat, always open the PR as a draft.** This applies to stacked PRs
   and handoffs that request a regular PR. The local screenshot is for
   the user to attach.
3. Tell the user that the PR stays in draft until they attach the
   manual-testing screenshot in this chat or add it under Manual
   Testing on GitHub. Before marking the PR **Ready for review**, the
   human adds the screenshot to the PR and checks that it matches the
   manual-testing sentence. Only a human marks the PR ready.

Never commit screenshots to the repo.
