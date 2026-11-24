**Value** 3 · **Points** 3 · **Priority** 1.00 · **Depends on** US3 · **Type** Required · **Sprint** 1 · **Label** P0

As a player, I want to read the Overlord's text prompt and write code in an editor so that I can know exactly what to build.

## Why
This is the screen players spend the whole game on. Like a human prompting an AI, the Overlord gives each stage as one plain-text prompt. It can be as snarky as we like, but it must leave no doubt about the feature, the controls, and the rules the Overlord will check.

## Scope
**In:** the game page layout, the Overlord feed showing the stage prompt as its first message, the lives display, the Monaco editor (empty on Stage 1), and keeping in-progress code across a refresh.
**Out:** follow-up Overlord messages and escalation (US10), Play My Program (US5), Submit and grading (US6), removing sample data from the campaign schema and stage data (US6), checkpoints and preloading the last passing code (US7), the timer and heat bar (US8), avatar states (US10, US12).

## Acceptance Criteria
1. **[HIGH]** Given that a stage is active, when the game page loads, then I see the Overlord's prompt as the first message in its feed (stating the feature, the controls, and the rules the Overlord will check), my lives, and an empty Python editor.
2. **[MED]** Given that I am on Stage 2 or later, when the page loads, then the editor is preloaded with my last passing code. *This can't be fully tested until US7 (checkpoints) lands in Sprint 2.*
3. **[HIGH]** Given that I have typed code in the editor, when I refresh the page, then my in-progress code is restored.
4. **[HIGH] (proposed)** Given that I view the game page, when I inspect the page source or network traffic, then no check script is present. Only the prompt reaches the browser.
5. **[MED] (proposed)** Given that the run isn't mine or doesn't exist, when I open `/play/<run_id>`, then I get a 404.
6. **[LOW] (proposed)** How code is saved (browser storage or server autosave), and the fallback if Monaco can't load.

## Rules & Details
- **The prompt** is the stage's `prompt` text, shown as plain sentences, not a form. Exact values the author marks in backticks (`` `0–9` ``, `` `w` ``) render in mono cyan ([design.md §6](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/design.md#6-overlord-feed-and-escalation)). It's the first message in the feed, and later messages (US10) are added below it.
- **Feed box:** a fixed-height window that scrolls. The newest message is at the bottom, older ones fade at the top edge, and the newest one has a blinking cursor. There are no sender names or timestamps.
- **Lives:** shown as integrity cells in the top bar, with the count in `aria-label` ("2 of 3 lives").
- **Stage readout:** `TIER / 02/04` in the top bar.
- **Editor:** Monaco from a pinned CDN version, language Python, the theme from the design tokens, and tab = 4 spaces.
- **No starter code:** Stage 1 starts empty. Later stages use the last checkpoint (US7). Until US7 lands, they start empty too.
- **Autosave (suggested):** save to `localStorage` under `rokos:run:<run_id>:stage:<n>` at most once per second while typing. On load, a saved draft fills the editor. US7 clears it when the stage is passed.
- **Data to JS:** the server renders the prompt into the HTML, plus one `<script type="application/json" id="stage-data">` with the stage data the page scripts need. It never holds the check script. There's no separate API call to load the stage.
- **A finished run** (`won`, `lost`, or `abandoned`) shows "This run is over." with a link to `/start` instead of the editor.

## UI
- **Route:** `GET /play/<run_id>` (login required, owner only).
- **Layout:** follows [design.md](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/design.md) and design 6 on the design canvas. The Overlord and its feed are on the left. The editor + console are on the right (the console is used by US5).
- **Elements:** `game-feed`, `game-prompt` (the first feed message), `game-stage-readout`, `game-lives`, `game-editor`, `game-run-over`.
- **JS:** `static/js/game.js` (entry) imports `editor.js` (Monaco setup + autosave), `feed.js` (renders and scrolls the feed), and `api.js`. These are ES modules, with no build step.

## Technical Notes
- **Presentation:** `game_routes.py` `play(run_id)`, `templates/game/play.html`, `static/js/game.js`, `editor.js`, `feed.js`.
- **Business:** `GameService.get_stage_view(user, run_id) -> StageView`, a plain object holding only what the page may show (prompt, lives, stage number). It never holds the check script. Raises `RunNotFoundError` for a missing run or someone else's run.
- **Data:** `RunRepository.get(run_id)`, plus its `Stage`.
- **Selenium tip:** typing into Monaco is unreliable. Set code with `monaco.editor.getModels()[0].setValue(...)` through `execute_script`, then reload and read the value back the same way.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | `get_stage_view` returns prompt, lives, and stage number | unit |
| 1 | Start a Beginner run → `game-prompt` shows the seed's prompt text, and `game-lives` and `game-editor` are visible | e2e |
| 2 | With a fake checkpoint, the view's editor code = the checkpoint code | unit (full e2e in US7) |
| 3 | Set editor code → reload → the same code is shown | e2e |
| 4 | `GET /play/<id>` HTML contains no check script | integration |
| 5 | Another user's run → 404; nonexistent → 404; logged out → redirect to login | integration |

## Follow-up requirement

- **[MED]** When a player tries to start a new run while one is in progress,
  ask for confirmation and explain that starting over will abandon the
  current run with a score of zero. Cancel keeps the current run. Confirm
  abandons it and starts the selected run.
- [Cameron’s review on PR #7](https://github.com/msu-denver/rokos-tasks/pull/7#pullrequestreview-5967671409)

## Tasks
- [ ] T9: US4: Game page: Overlord feed, lives, and editor

## Open Questions
- None.
