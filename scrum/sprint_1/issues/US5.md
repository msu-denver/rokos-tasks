**Value** 3 · **Points** 8 · **Priority** 0.38 · **Depends on** US4 · **Type** Required · **Sprint** 1 · **Label** P1

As a player, I want to run my program in the browser and control it with my keyboard as often as I like so that I can see my game working before the Overlord judges it.

## Why
Players need a safe, instant way to try their program before risking a life on Submit. Running it as a live loop also lets them actually play what they build at every stage. This replaces the old Run Sample design and the Playable Finale (US17), per #13.

## Scope
**In:** the Run and Stop buttons, Pyodide in a Web Worker, the tick loop (one input line in, one frame out), sending the player's key presses, drawing frames, tracebacks, and the per-tick timeout.
**Out:** check scripts and Submit (US6), lives changes (US6/US7), Overlord reactions to runs (US10).

## Acceptance Criteria
1. **[HIGH]** Given that there is code in the editor, when I click Run, then my program runs in the browser, the keys I press are sent to it each tick, I see every frame it prints, and I lose no lives.
2. **[HIGH]** Given that my program crashes, when the error happens, then it stops and I see the traceback.
3. **[HIGH]** Given that my program takes longer than 1 second to answer a single tick, when that happens, then it is stopped and I see a friendly timeout message.
4. **[HIGH] (proposed)** Given that I click Run, when it runs, then no request is sent to our server.
5. **[MED] (proposed)** Given that Python is still loading, when the page opens, then the Run button is disabled and shows "Loading Python…" until it's ready.
6. **[LOW] (proposed)** Tick rate, how the frame is drawn, and the cap on displayed output.

## Rules & Details
- **The tick contract** ([game-design §2.2](../../../docs/game-design.md#22-the-stage-contract-a-program-the-overlord-can-play)): each tick the program reads one line from stdin and prints one frame ending with a line containing only `---`. `input()` must work.
- **Input line:** the keys pressed since the last tick, in order (for example `qp`), or an empty line if none. Suggested tick rate: 10 per second.
- **Pyodide:** pin one release from a CDN whose Python version is **3.13** (the server's version; roadmap §3.1). It runs in a Web Worker; stdin blocks on a `SharedArrayBuffer` until the next tick, so the page needs the cross-origin isolation headers (`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`).
- **Stop:** the Stop button, or the program exiting, ends the run. The program can be run again right away.
- **Timeout:** if one tick takes more than 1 second, the worker is terminated and a new one starts, and the screen shows: "Your program took more than 1 second to answer and was stopped. Check for an infinite loop."
- **Error:** an uncaught exception shows the Python traceback, with frames from our own harness hidden.
- Lives, score, and the run in the database are never touched.

## UI
- **Elements:** `game-run` (button), `game-stop` (button), `game-screen` (the latest frame, monospace), `game-error`, `game-run-timeout`.
- Keys are captured only while `game-screen` has focus, so typing in the editor never sends input.

## Technical Notes
- **JS:** `static/js/pyodide_worker.js` (load Pyodide, run the program, block on stdin, post each frame), `static/js/play.js` (tick timer, key buffer, drawing), wiring in `game.js`.
- **Server:** only the cross-origin isolation headers on the game page. `GameService.get_stage_view` (US4) already supplies the prompt.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | A program that prints the input line as its frame → pressing `q` shows `q` in `game-screen`, lives unchanged | e2e |
| 2 | `raise ValueError` → `game-error` shows the traceback | e2e |
| 3 | `while True: pass` → `game-run-timeout` appears within ~2 s, and a following run works | e2e |
| 4 | During a run, the browser's performance log shows no request to our server | e2e |
| 5 | Button disabled with "Loading Python…" until the worker reports ready | e2e |

## Tasks
- [ ] T10: US5: Run the program as a live loop in the browser with Pyodide

## Open Questions
- Tick rate: fixed 10 per second, or set per campaign? (Product Owner)
