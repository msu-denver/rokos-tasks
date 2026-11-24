# Sprint 2 Planning

**Date/Time:** 11/23/26, _time to fill in_
**Participants:** _to fill in_
**Sprint:** 11/23–11/29 (Thanksgiving 11/26 falls inside it)

## Notes

**Sprint goal:** a player can submit code and get a fair verdict from the Overlord, then keep or lose lives and move through the stages.

**Stories pulled:** _the full list and capacity are to fill in_. This section covers **US6** only.

### US6: The Overlord Plays My Program

**Value** 3 · **Points** 13 · **Priority** 0.23 · **P0** · **Depends on** US4 · **Issue** #19 · **Owner** Richard Hall (with Claude Code)

US6 is the core of the game. When the player clicks Submit, the player's program runs in a locked-down sandbox, and the stage's check script plays it (it sends keys and reads frames) to decide pass or fail. US7, US8, US10, and US11 all build on it.

**Tasks and pull requests.** Each task has its own branch and draft PR into `dev`, stacked in order:

| Task | What | Branch | PR |
| --- | --- | --- | --- |
| T12 | Sandbox runner container, limits, hostile-code tests | `feature/US6-overlord-plays` | #18 |
| T13 | Check-script harness, `POST /grade`, `check_script` in the campaign schema and validator | `feature/US6-check-harness` | #20 |
| T14 | ASCII Pong seed campaign (Medium, 3 stages) with check scripts | `feature/US6-pong-checks` | #21 |
| T15 | `GradingService`, `RunnerClient`, Submit button and verdict panel | `feature/US6-submit` | #22 (closes #19) |

The stack sits on #8 (US4), which has to merge first.

**Decisions made while planning and building US6 (11/24):**

| Decision | Why |
| --- | --- |
| The runner keeps the `SETUID` and `SETGID` Linux capabilities and drops all others. The story's rules said to drop all capabilities. | Each run switches to its own user. If every run shared one user, a player's program could read other players' files or fake its own verdict. Player programs end up with no capabilities at all. Needs the Runner Owner's sign-off. |
| `make check` starts the runner container and runs the hostile-code tests against it. | The attacks only mean something inside the real sandbox. |
| `check_script` is added to campaigns alongside the old output-comparison fields. Nothing is removed yet. | The Beginner and Easy campaigns and PR #8 still rely on the old fields. Removing them is tech debt #15. |
| Check scripts run in a sandbox of their own, never inside the runner server. | US11 has an AI write check scripts, so a bad one must not be able to do harm. |
| If the stage-3 check doesn't see a wall bounce, a paddle bounce, and a miss within 400 ticks, the program fails. | Answers one of US6's open questions. The check script steers the paddles itself, so a working program always produces all three. |
| The ball moves exactly 1 row per tick. Its column speed (1 to 4 columns per tick) is the player's choice. | Different speeds can still pass (AC3), and the check script can reliably steer a paddle in front of the ball. |
| A stage with no check script (Beginner and Easy, until #15) answers Submit with "This stage can't be graded yet." | The alternative was a second, temporary grading system that #15 would have to delete. |
| Verdict wording is placeholder text for now: `PASS` or `FAIL` plus a reason. | The proposed wording is still an open question for the Product Owner. All of it lives in one place, ready for US10. |

**Still open (Product Owner):** the final pass and fail wording, including the "Human hallucination detected" heading.

**New tech debt from US6:** #23. `make dev` can't reach the runner, so Submit can only be tried with `make up`.
