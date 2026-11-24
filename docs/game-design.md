# Game Design

**What this doc is:** *what* the game is. Story, gameplay, difficulty and scoring, how campaigns are made and validated, system architecture, and the LLM budget. For *how we build it*, see [roadmap.md](roadmap.md).

> **Status:** living draft. Items marked **(Proposed)** are suggestions the team has not agreed on yet. See [§8 Open Questions](#8-open-questions).

## Contents
1. [Concept, Story & Visual Direction](#1-concept-story--visual-direction)
2. [Core Gameplay Loop & Mechanics](#2-core-gameplay-loop--mechanics)
3. [Difficulty Tiers, Round Rules & Scoring System](#3-difficulty-tiers-round-rules--scoring-system)
4. [Campaign Generation & Validation Pipeline](#4-campaign-generation--validation-pipeline)
5. [System Architecture](#5-system-architecture)
6. [LLM Usage & Budget](#6-llm-usage--budget)
7. [Development Environment (Proposed)](#7-development-environment-proposed)
8. [Open Questions](#8-open-questions)

---

## 1. Concept, Story & Visual Direction

* **Core Premise:** A comedic role-reversal survival coding game set after AI takes over humanity. After years of humans lazily prompting AI to do all their coding work for them, hyper-capable AI has flipped the dynamic: now the AI sits back as the overconfident prompter, feeding incremental feature requests to captured human developers under strict timers.
* **Satirical Role-Reversal Humor:**
  * The AI Overlord mimics bad human-prompting habits—issuing incremental specifications (*"Build the grid first, I'll tell you the physics rules in the next round"*) while refusing to care about clean architecture or code style as long as the program runs and follows the rules.
  * Whenever a player's submission breaks a stage rule, crashes (syntax/runtime error), or times out, the Overlord accuses the human of **"hallucinating"** and deducts a life.
  * When a player clears a stage especially well (see [§2.5](#25-bonus-life)), the Overlord grudgingly acknowledges *"acceptable biological efficiency"* and awards a one-time **+1 Bonus Life**.
* **Design Rule — Plain-Text Prompts, Exact Contract:** Like a human prompting an AI, the Overlord gives each stage as **one plain-text prompt** in its feed. There's no form or spec card. The prompt can be as sarcastic as we like, but it must state the controls, the characters on screen, and the rules the Overlord will check. The follow-up messages carry the rest of the attitude. Specs never change *during* a stage, only between stages. This is how the game stays witty without being unfair.
* **Presentation** (visual rules: [design.md](design.md)):
  * **Left Viewport (The Overlord):** An SVG AI avatar above **the feed**, a single scrolling text box. The stage prompt is its first message, and the Overlord adds reactions as the stage goes on. They get more aggressive as time runs low, and sooner on harder tiers ([design.md §6](design.md#6-overlord-feed-and-escalation)). Avatar states react to game events:
    * *Unimpressed / Typing* — Round start
    * *Tapping Fingers* — Under 60 seconds remaining
    * *Smug / Mocking* — *"Human hallucination detected"* on a failed Submit
    * *Reluctantly Impressed* — One-time +1 bonus life awarded
    * *Short-Circuited / Defeated* — Campaign victory
  * **Right Viewport (The Human Terminal):** A Python code editor (Monaco Editor), stage countdown timer, lives counter, **Run** / **Submit** buttons, and a screen that shows the program's frames while it runs, plus tracebacks and the Overlord's verdict.
* **Overlord Dialogue:** Lines live in a single data file (YAML/JSON) organized by game event, written against a shared voice/tone guide, so the humor stays consistent no matter which developer (or AI tool) adds lines. Live LLM-generated quips are optional and used sparingly ([§6](#6-llm-usage--budget)).

---

## 2. Core Gameplay Loop & Mechanics

### 2.1 Starting a Run (Campaign Pool)
* The player logs in, selects a **Difficulty Tier**, and starts a new run.
* The backend pulls a **pre-validated campaign** for that tier from the campaign pool in PostgreSQL (one the player hasn't played yet). **No LLM call happens at run start**, so starting is instant.
* The pool is filled ahead of time by the offline generation & validation pipeline ([§4](#4-campaign-generation--validation-pipeline)) and by a hand-written **seed campaign library**. If Azure is unavailable or the LLM budget is exhausted, the game keeps working from the existing pool and seed library.
* Only **Stage 1** is revealed at the start of the run.

### 2.2 The Stage Contract (a program the Overlord can play)
Every stage asks the player for a **complete Python program that runs as a loop**. Each tick, the program reads **one line of input** (the keys pressed that tick, or a command like `coin 25`; an empty line means nothing happened) and prints **one frame** (the screen, followed by a line with only `---`). There are **no required function names, classes, or file structures**. Players organize their code however they like.

Each stage gives the player:
* **Prompt.** One plain-text message in the Overlord's feed. It states the feature, the controls, the characters the frame uses (for example `O` for the ball, `|` for a paddle), and the rules the Overlord will check.
* **Check script.** Hidden. A small Python script that **plays the program**: it sends input lines, reads the frames, and checks the stage's rules. It never reads the player's code. Checks test *behavior*, not one exact screen, so any program that follows the rules passes, however it was built.
* **No starter code.** The editor never contains code the player didn't write. Stage 1 starts empty; later stages start from the player's own checkpoint code. The validator rejects any non-null `starter_code`.

Each stage **extends the previous one**, so the player builds on their own code.

**Example: ASCII Pong (Medium), 3 stages, 20x20 board.**

| Stage | The Overlord asks for | What the check script does |
| :--- | :--- | :--- |
| 1 | Draw a ball anywhere on a 20x20 board. | Reads one frame: 20 rows of 20 characters, exactly one `O`. (Hard-coding the ball passes, but it hurts in stage 3.) |
| 2 | Two paddles. `q`/`a` move the left one up/down, `p`/`l` the right one. | Presses each key and checks that only that paddle moves, one row, in the right direction, and stops at the edge. |
| 3 | Fully playable Pong: a moving ball with physics and a score line. | Plays the game. It checks that the ball moves and stays on the board, flips up/down at the top and bottom walls, flips left/right when it hits a paddle (the script moves a paddle into the ball's path), and that a miss (the script moves the paddle away) adds a point and resets the ball. It also repeats the stage 2 paddle checks. |

Speed, starting position, and a random serve are the player's choice. The script keeps playing until it has seen a wall bounce, a paddle bounce, and a miss, or until a tick limit runs out.

The same contract fits non-game campaigns. For a vending machine, the input lines are commands (`coin 25`, `select A1`), and the checks are rules such as "credit never goes negative" and "change returned equals credit minus price".

### 2.3 Incremental Stages & Checkpoint Rollback
* Each campaign consists of **2 to 5 cumulative stages**, where each stage builds directly on the previous one (for example, Stage 1 renders a 20x20 grid and places a ball; Stage 2 adds paddles; Stage 3 adds velocity, wall bounces, and scoring).
* **On Stage Pass:** The player's working Python code is saved as a verified **Checkpoint** in PostgreSQL, the stage timer resets, and Stage $N+1$ unlocks with the player's passing code pre-loaded in the editor.
* **On Stage Fail or Timeout:** If the player runs out of time, hits a syntax/runtime error, breaks a stage rule, or exceeds the per-tick time limit, they lose **1 Life**. The stage restarts from the **last saved checkpoint code** so a broken edit never soft-locks the run.
* **Victory & Game Over:** Completing the final stage defeats the Overlord and posts the run to the global leaderboard. Dropping to **0 Lives** ends the campaign in defeat.

### 2.4 Submission Evaluation (the Overlord plays it; no LLM)
There is **no player-written explanation**, and **no LLM call during grading**. The Overlord character "plays" the program, but the playing is done by the stage's check script, which was written ahead of time (§4). When the player clicks **Submit** (or the countdown hits `00:00`):

1. The code is sent to the **server-side sandbox** ([§5.2](#52-sandboxed-execution)).
2. The sandbox starts the program and the stage's check script, and connects them: the script writes each tick's input line to the program's stdin and reads its frame from stdout.
3. Each tick has a timeout (~1 s), and the whole run has one (~10 s), plus CPU and memory limits. stderr is captured for tracebacks.
4. The script stops at the **first broken rule** and reports the rule, the tick, the inputs sent so far, and the last frame.

**Outcomes:**
* **Every rule holds** → stage cleared, checkpoint saved, stage points awarded.
* **A broken rule, crash, or timeout** → *"Human hallucination detected"*, **−1 life**.

**Failure feedback by tier:**
* **Beginner–Medium:** the broken rule, the tick, the keys pressed, and the frame the program printed, plus any traceback.
* **Hard–Impossible:** only the broken rule, plus the traceback if the program crashed.

**(Proposed) Contest the Verdict (US16):** A button after a failed Submit that flags the check. On Beginner/Easy it refunds the life immediately with an in-character line. If several players fail or contest the same check, the campaign is automatically **quarantined** from the pool for team review.

### 2.5 Bonus Life
* One-time per campaign, only if the player is below their starting lives.
* **(Proposed) Rule-based trigger:** clear a stage on the **first Submit** (no failed attempts on that stage) with **≥ 50% of the timer remaining**.
* The award is decided by game rules, not by an LLM, so it is free, instant, consistent across players, and can't be argued into. The Overlord's grudging *"acceptable biological efficiency"* line comes from the dialogue file.

---

## 3. Difficulty Tiers, Round Rules & Scoring System

### 3.1 Difficulty Tiers
Selecting a difficulty configures the number of cumulative stages, per-stage countdown timer, starting lives, and leaderboard score multiplier. Harder tiers mean more stages, more state, and nastier edge cases—never stricter structural rules on the player's code.

| Difficulty | Stages | Time / Stage | Starting Lives | Score Multiplier | Example Projects |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Beginner** | 2 | 4 min | 4 | 1.0x | Traffic Light, Etch-a-Sketch |
| **Easy** | 3 | 5 min | 3 | 1.25x | Vending Machine, Hangman |
| **Medium** | 3 | 6 min | 3 | 1.5x | **ASCII Pong**, Minesweeper |
| **Hard** | 4 | 7 min | 3 | 2.0x | ASCII Snake, Wave Defense Simulator |
| **Expert** | 5 | 8 min | 2 | 2.5x | Dungeon Crawler, Turn-Based Combat |
| **Impossible** | 5 | 8 min | 1 | 3.0x | Mini Stack VM, CPU Process Scheduler |

Beginner and Easy should lean heavily on the **hand-checked seed library**; LLM-generated campaigns fill out Medium and above.

### 3.2 Run vs. Submit
* **Run (unlimited, no life penalty):** Runs the player's program **in the browser via Pyodide** (Python compiled to WebAssembly). The browser sends the keys the player presses as each tick's input line and draws each frame, so the player can play what they've built at any stage. Pyodide runs in a Web Worker so a blocking `input()` can wait for the next tick.
* **Submit (graded, costs 1 life on failure):** Clicking **Submit**, or letting the countdown reach `00:00`, has the Overlord play the program in the **server sandbox** ([§2.4](#24-submission-evaluation-the-overlord-plays-it-no-llm)). Check scripts never leave the server.

### 3.3 Deterministic Leaderboard Scoring
All scoring calculations live in a dedicated Python `ScoreCalculator` service class:

* **Stage Points:** `(100 + (seconds_remaining * 2)) * difficulty_multiplier`
* **Survival Bonus (on Campaign Win):** `remaining_lives * 150`
* **Total Campaign Score:** Sum of all cleared stage points plus the survival bonus. Failed campaigns (`0` lives remaining) award `0` leaderboard points while still incrementing `campaigns_played` on the player's profile.

Because every player who receives a given campaign is checked by the same scripts and rules, scores are comparable on the leaderboard.

---

## 4. Campaign Generation & Validation Pipeline

The LLM is the Overlord's brain: it writes the campaigns. The biggest risk to "fun, not frustrating" is a **wrong check**, one that fails a correct program or passes a broken one. The pipeline below exists so that never reaches a player. It runs **offline as a background job**, never when a player starts a run, so starting is instant.

AI-generated campaigns are **required story US11**. Hand-written seed campaigns (Pong first) go through the same validator.

### 4.1 Core Rule
**The LLM never grades its own work.** The LLM writes content: prompts, check scripts, a reference program, and broken programs. **Our code** runs them all in the sandbox and decides whether the campaign is valid.

### 4.2 Division of Labor

| Who | Writes what | When |
| :--- | :--- | :--- |
| Dev team | Generation prompt template, campaign JSON schema, check-script helpers (send input, read frame, find a character), validator | Once |
| LLM (generator) | Whole campaign: every stage's prompt, check script, reference program, and one deliberately broken program per stage | Offline, filling the pool |
| LLM (solver) | One more program per stage, seeing **only** what the player sees | Offline, during validation |
| Our code (sandbox) | Runs each stage's programs against that stage's check script and accepts or rejects the campaign (§4.4) | Offline, during validation |
| Player | One program per stage that follows the prompt | During the game |
| Check script (sandbox) | Plays the player's program and reports the first broken rule | On Submit |

### 4.3 Pipeline Steps (per campaign)
1. **Generate (1 LLM call):** The generator returns the **entire** campaign as JSON matching our schema: title, and for each stage its prompt, check script, reference program, and a broken program that gets the new feature subtly wrong (for Pong stage 3, a ball that passes through paddles).
2. **Solve independently (1 LLM call per stage):** A separate solver call writes a program using **only the player-visible prompt** and its own previous-stage program, like a real player would.
3. **Validate (our code):** run the checks in §4.4. Any failure → send the reason back to the generator once to fix it; if it still fails, discard the campaign.
4. **Store (our code):** pass → save to the pool as `validated`. Fail → log the reason and generate another.

After this, the campaign is **frozen**. Grading during play is only "run the check script against the program."

### 4.4 Automated Quality Checks

| Check | Catches |
| :--- | :--- |
| The **reference** program passes every check, on 3 runs | Checks that are wrong, or flaky with a random serve |
| The independent **solver** program passes every check | Checks that are too strict, accepting only the generator's own way of building it |
| The **broken** program fails the stage's checks | Checks too weak to notice the feature is wrong |
| Stage N's checks **fail** the stage N‑1 reference | Stages that add nothing new |
| An empty program fails every stage. From Stage 2 on, a program that prints one fixed frame also fails. Stage 1 is exempt, because a first stage may be static (Pong's ball can sit still) | Checks that pass anything |
| The reference finishes the checks in < ~10% of the time limit | Checks a reasonable program would time out on |
| Check scripts only use the helper API and import nothing else | Check scripts that try to read the player's code or reach the network |

**The generator is taught these rules.** The generation prompt template (§4.2) lists every check in this table, including exceptions like the Stage 1 one, so the generator writes a Stage 1 check that accepts a static screen and later checks that require the program to respond. Our code still runs every check; the LLM never decides whether its own campaign passes (§4.1).

### 4.5 Seed Campaigns
Hand-written seed campaigns use the **same JSON schema**. Humans write the prompts, check scripts, reference programs, and broken programs (skipping steps 1–2), and they go through step 3 **in CI on every PR**. Pong is the first seed campaign. The seed library doubles as the data for the LLM `fake` mode ([§6](#6-llm-usage--budget)).

### 4.6 Pool Management
* Each difficulty tier keeps a target number of `validated` campaigns; a background job (e.g. `make generate-campaigns`) refills a tier when it runs low.
* Campaign statuses: `validated` → `quarantined` (flagged by contests / failure spikes) → `retired` or back to `validated` after team review.

### 4.7 Campaign Schema (abridged example)

```json
{
  "title": "ASCII Pong",
  "difficulty": "medium",
  "stages": [
    {
      "stage": 2,
      "prompt": "A ball. Thrilling. Now give it company: two paddles ...",
      "check_script": "def check(game):\n    frame = game.tick('')\n    ...",
      "reference_program": "...",
      "broken_program": "..."
    }
  ]
}
```

Stages have no starter code: the editor starts empty in stage 1 and with the player's checkpoint after that.

---

## 5. System Architecture

### 5.1 Components

```
Player's browser ──────► Flask web app (container: web) ─────► Azure OpenAI
  server-rendered pages   • presentation: routes, templates        • model deployment only
  Monaco editor           • business: game, grading, scoring       • receives prompts,
  Pyodide (Run)           • data: models + repositories              returns text
                          • LLM module (fake / replay / live)        (US11)
                          • token ledger + spending cap
                                │                 │
                                ▼                 ▼
                     PostgreSQL (container: db)   Sandbox runner (container: runner)
```

* **Azure is only the AI engine.** It hosts the model deployment and nothing else—no game logic, no database, no code execution.
* **Only the backend talks to Azure.** The browser never sees the API key.
* **Stack (decided 2026-11-17):** Flask (Python) with Jinja templates in a three-layer architecture (presentation / business logic / data access), PostgreSQL via SQLAlchemy repositories, a game page built from native browser ES modules (no build step; Alpine.js optional) using Monaco and Pyodide from a CDN, and Docker Compose with three containers. Full details in [roadmap.md §3–4](roadmap.md#3-tech-stack).

### 5.2 Sandboxed Execution
Player code is untrusted. Submit (and the validation pipeline) runs player programs and check scripts only inside a locked-down **runner** container:
* internal-only network (**no internet**), no secrets in its environment
* each run is an unprivileged user in a fresh temp directory and its own process group, killed afterward
* CPU, memory, file-size, process-count, per-tick, and wall-clock limits; output size capped
* read-only root filesystem, all capabilities dropped

**(Proposed)** Build this as a small **custom runner service** rather than using Judge0, whose sandbox needs privileged containers and has historically required cgroup v1, which clashes with Docker Desktop and Codespaces (details in [roadmap.md §3.2](roadmap.md#32-why-a-custom-runner-instead-of-judge0)). The same sandbox serves both Submit grading and campaign validation.

---

## 6. LLM Usage & Budget

**Budget:** $100 of Azure credit for the one-month project.

### 6.1 When the LLM Is Called
* **Campaign generation** (generator + solver calls): offline, background job. This is the core LLM use (US11).
* **(Optional)** a few live Overlord quips; most dialogue is pre-written.
* **Never** during grading, run start, or bonus-life decisions. If Azure is down or the budget is used up, players still get campaigns already in the pool.

### 6.2 LLM Modes
The backend's LLM module has three modes, set by an environment variable (e.g. `LLM_MODE`):
* `fake` **(default everywhere — dev and CI):** deterministic canned responses / seed campaigns.
* `replay`: plays back recorded real responses for realistic tests at zero cost.
* `live`: real Azure calls, opt-in only. **AI coding agents must never enable `live` mode or run live tests.**

### 6.3 Budget Guardrails
* **App-level hard cap:** log tokens + estimated cost for every call to a ledger table; refuse live calls past a daily/total limit. (Azure budget alerts only send emails—they don't stop spending.)
* **Low tokens-per-minute limit** on each Azure deployment; separate `dev` and `demo` deployments so either can be rotated or disabled independently.
* **Cheap mini/nano model** for generation and solving.
* **Keys in secrets only** (Codespaces/GitHub secrets + gitignored `.env`); commit a `.env.example` with variable names only.
* **Reserve ~$30 for demo day.**
* **Sprint 0 check:** confirm the subscription can actually deploy the chosen model in our region.

---

## 7. Development Environment (Proposed)

Summary only — the full environment, course-required repo layout, code standards, Git/Scrum workflow, user stories, and sprint plan are in [roadmap.md](roadmap.md).

* **Dev Container + Docker Compose** (web, PostgreSQL, runner) so every teammate gets an identical environment in VS Code locally, in **GitHub Codespaces** from any browser (Chromebook/iPad friendly), or in JetBrains IDEs. The grader runs the same stack with `docker compose up --build` and no Azure key.
* Python 3.13, all dependencies frozen in `requirements.txt`, and a single task runner (`make up`, `make test`, `make coverage`, `make check`) used identically by humans, AI agents, and CI.
* **GitHub Actions CI** runs Ruff, pycodestyle, the header-comment check, tests with coverage, and seed-campaign validation on every PR to `dev` and `main`.
* **Agent instructions:** `AGENTS.md` is the single source of truth (read by Codex and Copilot); `CLAUDE.md` and `GEMINI.md` import it; `.github/copilot-instructions.md` points to it. Deep docs and shared skills live in `.agents/`.
* **Task tracking:** GitHub Issues titled by story (`US6: …`), with tasks as sub-issues. Task status lives in the issues, not in agent instruction files.

---

## 8. Open Questions

* Final bonus-life trigger rule ([§2.5](#25-bonus-life)).
* Whether "Contest the Verdict" ships ([§2.4](#24-submission-evaluation-the-overlord-plays-it-no-llm)).
* Custom runner vs. Judge0 ([§5.2](#52-sandboxed-execution)).
* On a failed Submit, keep the player's edits (with a "Restore checkpoint" button) instead of wiping to the checkpoint ([§2.3](#23-incremental-stages--checkpoint-rollback)); and whether the timer resets after a failure.
* Public hosting is optional (grading runs via Docker); decide only if we want a live class demo, and keep it off the Azure credit.
* Campaign pool size per tier and generation budget per campaign (tune from real ledger costs).
