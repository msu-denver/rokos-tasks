**Value** 3 · **Points** 5 · **Priority** 0.60 · **Depends on** US4 · **Type** Required · **Sprint** 1 · **Label** P1

As a player, I want to run my code against the visible samples as often as I like so that I can debug without losing a life.

## Why
Players need a safe, instant way to check their code before risking a life on Submit. Running in the browser (Pyodide) makes it instant and costs the server nothing.

## Scope
**In:** the Run Sample button, running Python in a Web Worker with Pyodide, feeding each sample as stdin, showing output, tracebacks, and pass/fail against the expected output, and the 5-second timeout.
**Out:** hidden tests and Submit (US6), lives changes (US6/US7), the playable finale (US17), Overlord reactions to sample runs (US10).

## Acceptance Criteria
1. **[HIGH]** Given that there is code in the editor, when I click Run Sample, then my code runs in the browser against each sample and I see its output, any error traceback, and a pass/fail comparison with the expected output, and I lose no lives.
2. **[HIGH]** Given that my code loops forever, when it has run for more than 5 seconds, then it is stopped and I see a friendly timeout message.
3. **[HIGH] (proposed)** Given that I click Run Sample, when it runs, then no request is sent to our server (samples run entirely in the browser).
4. **[MED] (proposed)** Given that sample output differs from the expected output only in trailing spaces or trailing blank lines, when compared, then it counts as a pass, using the same normalization the server uses for Submit ([game-design §2.4](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#24-submission-evaluation-tests-only--no-llm)).
5. **[MED] (proposed)** Given that Python is still loading, when the page opens, then the Run Sample button is disabled and shows "Loading Python…" until it's ready.
6. **[LOW] (proposed)** How the expected-vs-actual comparison looks, and the cap on displayed output length.

## Rules & Details
- **Pyodide:** pin one release from a CDN whose Python version is **3.13** (the server's version; roadmap §3.1). Record the version and its Python version in the README.
- **Samples are the prompt's examples.** Each stage stores them as structured input/output pairs (US4 puts them in `#stage-data`), and the validator guarantees they match the prompt text. The console calls them "example 1", "example 2".
- **Run:** for each sample, in order: reset the interpreter state, set `sys.stdin` to the sample input, capture `stdout` and `stderr`, run the whole program. `input()` must work.
- **Normalization (both sides):** CRLF → LF, strip trailing whitespace from every line, drop trailing blank lines. These rules live in one documented place and must match `GradingService`.
- **Timeout:** 5 seconds per Run Sample click. On timeout the worker is terminated and a new one starts, and the console shows: "Your code ran for more than 5 seconds and was stopped. Check for an infinite loop." The button shows "Restarting Python…" until the new worker is ready.
- **Error:** an uncaught exception shows the Python traceback, with frames from our own harness hidden, and the sample is marked failed.
- **Display cap (suggested):** show at most 10,000 characters of output per sample, then "… output truncated."
- Lives, score, and the run in the database are never touched.

## UI
- **Elements:** `game-run-sample` (button), `game-console`, `game-sample-<n>-result` (container), `game-sample-<n>-status` (text is exactly `PASS` or `FAIL`), `game-sample-<n>-expected`, `game-sample-<n>-actual`, `game-sample-<n>-error`, `game-run-timeout`.
- **Status line:** "2 of 2 samples passed" (`game-sample-summary`).

## Technical Notes
- **JS:** `static/js/pyodide_worker.js` (Web Worker: load Pyodide, run code, post results), `static/js/console.js` (render results), and the Run Sample wiring in `game.js`. The timeout is a `setTimeout` in the main thread that calls `worker.terminate()`.
- **Python side of normalization:** put it in `src/business/output_normalizer.py` now so US6's `GradingService` reuses it, and document the identical JS version next to it.
- **No server code** is needed for running samples. `GameService.get_stage_view` (US4) already supplies the samples.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | Correct code → every `game-sample-<n>-status` = `PASS`, lives unchanged | e2e |
| 1 | Wrong output → `FAIL`, with expected and actual shown | e2e |
| 1 | `raise ValueError` → `game-sample-1-error` shows the traceback | e2e |
| 2 | `while True: pass` → `game-run-timeout` appears within ~6 s, and a following run works | e2e |
| 3 | During a run, the browser's performance log shows no request to our server | e2e |
| 4 | `OutputNormalizer` cases: CRLF, trailing spaces, trailing blank lines, internal blank lines kept | unit (the course white-box test grows from this in US6) |
| 5 | Button disabled with "Loading Python…" until the worker reports ready | e2e |

## Tasks
- [ ] T10: US5: Run Sample in the browser with Pyodide

## Open Questions
- Is the 5 s timeout per click (all samples together) or per sample? This draft says per click. (Product Owner)
