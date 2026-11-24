**Value** 3 · **Points** 13 · **Priority** 0.23 · **Depends on** US4 · **Type** Required · **Sprint** 2 · **Label** P0

As a player, I want the Overlord to play my program and check it against the stage's rules so that I can find out whether I cleared the stage, however I chose to build it.

## Why
Submit is how a player clears a stage, and US7, US8, US10, and US11 all build on it. Grading by playing the program (instead of comparing one exact output) lets any program that follows the stage's rules pass, however it was built, per #13.

## Scope
**In:** the Submit button, the `runner` sandbox container, the check-script harness that connects a check script to the player's program, `GradingService` and `RunnerClient`, the `check_script` field in the campaign schema, check scripts for the Pong seed campaign, and showing the pass/fail verdict with what went wrong.
**Out:** losing a life, checkpoints, and opening the next stage (US7); the countdown auto-submit (US8); tier-based failure detail and Overlord reactions (US10); LLM-written check scripts and the validation pipeline (US11); Contest the Verdict (US16); running in the browser (US5).

## Acceptance Criteria
1. **[HIGH]** Given that there is code in the editor, when I click Submit, then my program runs in the server sandbox, the stage's check script plays it (sending keys and reading frames, never reading my code), and I receive a pass or fail verdict within about 10 seconds.
2. **[HIGH]** Given that my program breaks a rule of the stage, crashes, or times out, when grading finishes, then the verdict is fail and names what went wrong (the broken rule, the error, or the timeout).
3. **[HIGH]** Given that two programs follow the stage's rules but differ in details the rules don't fix (speed, starting position, a random serve), when each is submitted, then both pass.
4. **[HIGH] (proposed)** Given that a submitted program tries to reach the network, read environment variables, write outside its temp folder, fork-bomb, or use too much memory or output, when it runs, then the sandbox blocks or kills it and the verdict is fail.
5. **[MED] (proposed)** Given that I clicked Submit, when grading is in progress, then the Submit button is disabled and shows "The Overlord is playing your program…" until the verdict appears.
6. **[LOW] (proposed)** The exact layout of the verdict panel and how the last frame is shown.

## Rules & Details
- **The tick contract** ([game-design §2.2](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#22-the-stage-contract-a-program-the-overlord-can-play)): each tick the program reads one input line and prints one frame ending with a line containing only `---`. Same contract as US5.
- **Grading flow** ([game-design §2.4](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#24-submission-evaluation-the-overlord-plays-it-no-llm)): the sandbox starts the program and the check script and connects them. The script writes each tick's input to the program's stdin and reads its frame from stdout. It stops at the **first broken rule** and reports the rule, the tick, the inputs sent so far, and the last frame.
- **Check script API:** a check script defines `check(game)` and uses only the harness helpers (for example `game.tick(line)` returns the next frame). It imports nothing else and never sees the player's code ([game-design §4.4](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#44-automated-quality-checks), [§4.7](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#47-campaign-schema-abridged-example)).
- **Limits** ([game-design §5.2](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#52-sandboxed-execution), [roadmap §3.2](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/roadmap.md#32-why-a-custom-runner-instead-of-judge0)): about 1 s per tick and about 10 s per run, plus CPU, memory, file-size, process-count, and output (64 KB) caps. Python 3.13, run as `python -I main.py`, unprivileged user, fresh temp folder, own process group.
- **Runner container:** internal-only network (no internet), no secrets in its environment, read-only root filesystem, `tmpfs` scratch, all capabilities dropped, `no-new-privileges`.
- **No LLM** is called during grading.
- **Messages (proposed):**
  - Pass: "Stage cleared. The Overlord is… mildly impressed."
  - Fail heading: "Human hallucination detected"
  - Broken rule: the rule text from the check script, for example "Only the left paddle should move when you press q."
  - Error: "Your program crashed." followed by the traceback, with frames from our harness hidden.
  - Timeout: "Your program took more than 1 second to answer and was stopped. Check for an infinite loop."
- Lives, checkpoints, and score are not changed in this story (US7).

## UI
- **Route:** `POST /game/submit` (JSON), called from the game page.
- **Elements:** `game-submit` (button), `game-verdict` (pass/fail panel), `game-verdict-reason` (the broken rule, error, or timeout), `game-verdict-traceback`, `game-verdict-frame` (last frame, monospace).
- **States:** idle, grading (button disabled, AC5), pass, fail.

## Technical Notes
- **Runner:** `src/runner/` (standard-library HTTP service + check-script harness), `Dockerfile.runner`, a `runner` service in `docker-compose.yml` on an internal network. Add `src/runner/AGENTS.md` for sandbox rules.
- **Business:** `GradingService.grade(run, code)` returns a verdict (pass/fail, reason, tick, inputs, last frame, traceback). `RunnerClient` is the only code that talks to the runner.
- **Data:** add `check_script` to stages in the campaign schema and the campaign validator; seed the Pong campaign's check scripts plus a reference and a broken program per stage.
- **Presentation:** submit route in `game_routes.py`, `static/js/submit.js`, verdict panel in `game/play.html`.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | Submit the Pong stage 1 reference program → `game-verdict` shows pass within 10 s | e2e |
| 1 | `GradingService` with a fake check script that records what it received → it gets frames only, never the source | integration |
| 2 | A frame with two `O` characters → fail, `game-verdict-reason` names the rule | e2e |
| 2 | `raise ValueError` → fail with traceback; `while True: pass` → fail with the timeout message | integration |
| 3 | Two stage 3 programs with different speed and starting position → both pass; the random-serve reference passes on 3 runs | integration |
| 4 | Hostile-code suite (network, env vars, file writes, fork bomb, memory bomb, huge output) → each is blocked or killed | integration |
| 5 | Submit button disabled with "The Overlord is playing your program…" until the verdict appears | e2e |

## Tasks
- [ ] T12: US6: Build the sandbox runner container
- [ ] T13: US6: Add the check-script harness and `check_script` to the campaign schema
- [ ] T14: US6: Write the Pong seed campaign's check scripts
- [ ] T15: US6: Add GradingService, RunnerClient, and the Submit route and verdict panel

## Open Questions
- Pass and fail messages: are the proposed wording and the "Human hallucination detected" heading final? (Product Owner)
- Should a stage-3 check script that never sees a wall bounce, a paddle bounce, and a miss before the tick limit count as fail or as a check-script bug? (Product Owner)
