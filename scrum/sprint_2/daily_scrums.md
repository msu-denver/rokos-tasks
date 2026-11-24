# 11/24/26-HH:MM

**Participants:** Richard Hall, _others to fill in_

## Notes

**Richard Hall (US6)**
- **Done:**
  - Built all four US6 tasks, each as a draft PR into `dev`:
    - #18: the sandbox runner.
    - #20: the check-script harness.
    - #21: the ASCII Pong campaign.
    - #22: Submit and the verdict panel.
  - `make check` passes on every branch, and the last one has 454 tests at 98% coverage.
  - Self-reviewed each PR with the team rubric, fixed the findings, and opened tech debt #23.
  - Tested by hand on `make up`: the Pong stage-1 reference passes and a two-ball program fails with the broken rule, each in about half a second.
- **Doing:**
  - Attach the manual-testing screenshots and mark the PRs ready for review.
  - Answer review comments.
  - Start US7 (lives and checkpoints) once US6 merges.
- **Blockers:**
  - The PRs are stacked: #8 (US4) ← #18 ← #20 ← #21 ← #22. Each one waits on the one before it, so #8 needs review first.
  - The Runner Owner needs to sign off on keeping two Linux capabilities.
  - The Product Owner still needs to decide the verdict wording.

_Other team members: to fill in._

**Points remaining:** 18. US6 (13) and US7 (5) aren't done until their PRs merge.
