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

Agents can't upload images to GitHub, so:

1. The agent saves the screenshot to `.pr/screenshot.png` (gitignored)
   and opens the PR as a **draft** with this placeholder under Manual
   Testing: `<!-- SCREENSHOT: drag .pr/screenshot.png here -->`.
2. The human drags the image in over the placeholder, checks that the
   sentence matches what the screenshot shows, and clicks **Ready for
   review**.

Never commit screenshots to the repo.
