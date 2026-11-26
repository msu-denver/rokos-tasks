**Sprint 2** · **8 points** · **Depends on** #5 (US4, done) and **#36 (US6.5): US6.5 must merge into `dev` first**

**Value** 3 · **Priority** 0.38 · **Type** Required · **Label** P1

As a player, I want to run my program in the browser as often as I like, and type to it or play it with my keyboard, so that I can see it working before the Overlord judges it.

## Merge order: US6.5 first
US6.5 (#36, PR #58) changes the stage contract this story is built on, and it adds the console panel Run writes to. **Don't merge US5 until US6.5 is in `dev`.** Then:
1. Merge `dev` into the US5 branch (or rebase onto it).
2. Resolve conflicts by **keeping US6.5's version** of every shared file: `play.html`, `components.css`, `console.js`, `validator.py`, and the seed campaigns. Then add Run on top.
3. Re-run `make check` on the merged branch.

The current US5 PR (#64) implements the old **Run Sample** design: samples with expected output, an output normalizer, and PASS/FAIL against the Café Tab Splitter. US6.5 removes samples and that campaign, so the PR has to be reworked as described below.

## The stage contract (from US6.5, Part 4)
Run must play a program exactly the way Submit does:
- A stage program is a **normal Python script**, run like `python main.py`: top to bottom, and its output is whatever it prints. The player writes their own `main`, and writes a loop only if the program needs one.
- **No `for line in sys.stdin` loop and no `---` separator**, ever. A program that prints and exits is finished, not failed.
- A program reads input **only when the stage's prompt says so**, with plain `input()`.
- A **screen** is everything the program printed since it last asked for input, or before it exited.
- **(proposed, US6.5)** Each stage declares its **input style** in the campaign data:
  - `none`: the program reads no input. Run just shows what it prints.
  - `lines`: each `input()` waits for the player to type a line in the console and press Enter.
  - `keys`: a real-time game. Each `input()` returns the keys pressed since the last call, or an empty line if none, at a fixed turn rate. The game keeps moving when nobody presses anything.

  If US6.5 settles different names or a different turn rate, follow US6.5.

## Scope
**In:** the Run and Stop buttons; Pyodide in a Web Worker; blocking `input()` for the `lines` and `keys` styles; showing output in US6.5's console panel; tracebacks; the time limit; the loading state.
**Out:** check scripts and Submit (US6/US6.5), lives (US7), Overlord reactions (US10).

## Acceptance Criteria
1. **[HIGH]** Given that there is code in the editor, when I click Run, then my program runs in the browser like `python main.py`, everything it prints appears in the console panel, and I lose no lives.
2. **[HIGH]** Given a `lines` stage, when my program calls `input()`, then the console waits for me to type a line and press Enter, and my program continues with that line.
3. **[HIGH]** Given a `keys` stage, when my program calls `input()`, then it gets the keys I pressed since its last call (or an empty line) at the turn rate, and the console shows its latest screen. A Pong program is playable this way.
4. **[HIGH]** Given that my program exits, when it finishes, then the run ends normally (no error), and I can run it again right away. Stop ends a run at any time.
5. **[HIGH]** Given that my program crashes, when the error happens, then it stops and I see the traceback, with frames from our own code hidden.
6. **[HIGH]** Given that my program goes more than 1 second without asking for input or finishing, when that happens, then it's stopped, I see a friendly timeout message, and the next run works.
7. **[HIGH] (proposed)** Given that I click Run, when it runs, then no request is sent to our server.
8. **[MED]** Given the same program and the same input, when I Run it and when the Overlord plays it on Submit, then it gets input the same way (same input style, and the same 64-character cap on a `keys` line), so a program that works in Run behaves the same on Submit.
9. **[MED] (proposed)** Given that Python is still loading, when the page opens, then the Run button is disabled and shows "Loading Python…" until it's ready.
10. **[LOW] (proposed)** The turn rate for `keys` stages (suggested 10 per second) and how the latest screen is drawn.

## Rules & Details
- **Blocking `input()`:** Pyodide runs in a Web Worker. `input()` blocks the worker on a `SharedArrayBuffer` (`Atomics.wait`) until the page hands it a line:
  - `lines`: the line the player typed, sent on Enter.
  - `keys`: the key buffer, flushed every turn (even if empty).
  - `none`: the program shouldn't call `input()`. If it does, handle it the way the runner does on Submit.
- **Cross-origin isolation:** `SharedArrayBuffer` needs `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` on the game page. Check on day one that Monaco still loads from its CDN; if it doesn't, use `credentialless`.
- **Pyodide:** pin one release whose Python version is **3.13** (the server's version), from a CDN.
- **Keys:** captured only while the console has focus, so typing in the editor never sends input. Send only printable keys, and cap a `keys` line at 64 characters (the runner's limit).
- **Time limit:** the 1-second clock restarts each time the program asks for input. If it runs out, terminate the worker and start a fresh one.
- **Output:** goes to US6.5's console panel (`game-console`, resizable and collapsible). Don't add a second results panel.
- Lives, score, and the run in the database are never touched.

## Reworking the current US5 PR (#64)
**Keep and adapt:**
- `pyodide_worker.js`: loading Pyodide, running the code, the timeout, and recovering with a fresh worker. Add the blocking `input()` and the three input styles.
- The Run button wiring in `game.js` and `get_code()`.

**Remove** (it's the old Run Sample design that US6.5 deleted):
- `src/business/output_normalizer.py` and `tests/unit/test_output_normalizer.py`.
- Sample PASS/FAIL, expected vs. actual output, and the "Run Sample" button and label.
- The PR's own `console.js` (sample results) and its `components.css` and `play.html` additions. Use US6.5's console panel instead.
- The `validator.py` change. US6.5 rewrote the validator.
- `tests/e2e/test_run_sample.py`. Its tests are built on samples and the Café campaign; replace them with the Test Plan below.
- The README's Run Sample section. Describe Run under the new contract instead.

## UI
- **Elements:** `game-run` (button), `game-stop` (button), the console panel from US6.5 (`game-console`, `game-console-body`) for output, `game-run-timeout`, `game-error`.
- The `lines` style shows a typing line in the console. The `keys` style shows that the console is listening while it has focus.
- Tokens only, per `docs/design.md`.

## Technical Notes
- **JS:** `static/js/pyodide_worker.js` (Pyodide, run, blocking `input()`, timeout); `static/js/play.js` (Run/Stop, typed lines or the key buffer and turn timer, writing screens to the console); wiring in `game.js`.
- **Server:** only the cross-origin isolation headers on the game page, and passing the stage's input style to the page (in `#stage-data`, next to the stage number US6.5 already puts there). No grading code.
- **Don't build on:** samples or expected output (removed in US6.5), or the runner's `/run` endpoint. Run stays in the browser.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | A `none` program that prints a 20×20 board → the board appears in the console, lives unchanged | e2e |
| 2 | A `lines` program that echoes `input()` → typing `coin 25` and Enter shows it echoed | e2e |
| 3 | A `keys` program that prints the keys it got → pressing `q` shows `q`; no key shows an empty line on the next turn | e2e |
| 4 | A program that prints and exits → the run ends without an error, and Run works again | e2e |
| 5 | `raise ValueError` → `game-error` shows the traceback without our frames | e2e |
| 6 | `while True: pass` → `game-run-timeout` within ~2 s, and the next run works | e2e |
| 7 | During a run, the browser's performance log shows no request to our server | e2e |
| 8 | The same `keys` program and keys give the same screens in Run and on Submit | e2e |
| 9 | Run is disabled with "Loading Python…" until the worker is ready | e2e |

## Tasks
One issue per story: the work is tracked here as a checklist.

- [ ] **Rework the US5 PR onto US6.5** · Depends on: US6.5 (#36) merged into `dev`
  - **What:** merge `dev` (with US6.5) into the US5 branch, keep US6.5's shared files, and remove the Run Sample pieces listed above.
  - **[HIGH]** No samples, expected output, output normalizer, or "Run Sample" remain.
  - **Tests:** `make check` passes on the merged branch.
- [ ] **Run plain scripts with blocking `input()` and the three input styles** · Depends on: the task above
  - **What:** AC 1–10.
  - **Tests:** the Test Plan above.

## Open Questions
- The input-style names and turn rate are proposed in US6.5 (#36). Confirm them there before building AC 2–3. (Product Owner)
