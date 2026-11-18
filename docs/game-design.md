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
  * The AI Overlord mimics bad human-prompting habits—issuing incremental specifications (*"Build the grid first, I'll tell you the physics rules in the next round"*) while refusing to care about clean architecture or code style as long as the program runs and passes tests.
  * Whenever a player's submission fails a hidden test, crashes (syntax/runtime error), or times out, the Overlord accuses the human of **"hallucinating"** and deducts a life.
  * When a player clears a stage especially well (see [§2.5](#25-bonus-life)), the Overlord grudgingly acknowledges *"acceptable biological efficiency"* and awards a one-time **+1 Bonus Life**.
* **Design Rule — Plain-Text Prompts, Exact Contract:** Like a human prompting an AI, the Overlord gives each stage as **one plain-text prompt** in its feed. There's no form or spec card. The prompt can be as sarcastic as we like, but it must state exactly what the program reads, what it prints, and at least one example. The follow-up messages carry the rest of the attitude. Specs never change *during* a stage, only between stages. This is how the game stays witty without being unfair.
* **Presentation** (visual rules: [design.md](design.md)):
  * **Left Viewport (The Overlord):** An SVG AI avatar above **the feed**, a single scrolling text box. The stage prompt is its first message, and the Overlord adds reactions as the stage goes on. They get more aggressive as time runs low, and sooner on harder tiers ([design.md §6](design.md#6-overlord-feed-and-escalation)). Avatar states react to game events:
    * *Unimpressed / Typing* — Round start
    * *Tapping Fingers* — Under 60 seconds remaining
    * *Smug / Mocking* — *"Human hallucination detected"* on a failed Submit
    * *Reluctantly Impressed* — One-time +1 bonus life awarded
    * *Short-Circuited / Defeated* — Campaign victory
  * **Right Viewport (The Human Terminal):** A Python code editor (Monaco Editor), stage countdown timer, lives counter, **Run Sample** / **Submit** buttons, and a console showing stdout, stderr/tracebacks, and expected-vs-actual diffs.
* **Overlord Dialogue:** Lines live in a single data file (YAML/JSON) organized by game event, written against a shared voice/tone guide, so the humor stays consistent no matter which developer (or AI tool) adds lines. Live LLM-generated quips are optional and used sparingly ([§6](#6-llm-usage--budget)).

---

## 2. Core Gameplay Loop & Mechanics

### 2.1 Starting a Run (Campaign Pool)
* The player logs in, selects a **Difficulty Tier**, and starts a new run.
* The backend pulls a **pre-validated campaign** for that tier from the campaign pool in PostgreSQL (one the player hasn't played yet). **No LLM call happens at run start**, so starting is instant.
* The pool is filled ahead of time by the offline generation & validation pipeline ([§4](#4-campaign-generation--validation-pipeline)) and by a hand-written **seed campaign library**. If Azure is unavailable or the LLM budget is exhausted, the game keeps working from the existing pool and seed library.
* Only **Stage 1** is revealed at the start of the run.

### 2.2 The Stage Contract (stdin → stdout)
Every stage is graded as a **complete Python program** that reads text from `stdin` and prints text to `stdout`. Tests never call player functions, so **there are no required function names, classes, or file structures**—players may organize their code however they like.

Each stage gives the player:
* **Prompt** — one plain-text message in the Overlord's feed. It states the feature, exactly what arrives on stdin (with constraints), exactly what to print, and 1–2 examples.
* **Samples** — the same 1–2 examples, also stored as structured input/output pairs so **Run Sample** can test against them. The campaign validator rejects a stage if a sample's input or output doesn't appear in its prompt.
* **Starter Code** — Stage 1 starter includes the line(s) that read the input; later stages start from the player's own checkpoint code.

Each stage **extends the previous stage's contract** (more input fields, richer output), so the player builds on their own previous code.

**Example — Minesweeper (Medium), Stage 2 of 3:**

> **Overlord:** Your "board" is a sad grid of dots. Now every safe cell shows how many mines touch it, diagonals included, or `.` if none do. The input hasn't changed: the first line is `R C M` (1 ≤ R, C ≤ 20), then `M` lines of `r c`, the 0-indexed mine positions. Print `R` lines of `C` characters, with `*` for a mine. Example: `3 4 2`, `0 0`, `1 2` prints `*211`, `12*1`, `.111`. And no, I won't be changing the input. I'm not a monster. Yet.

| Stage | Feature added | Contract change |
| :--- | :--- | :--- |
| 1 | Place mines on a board | Input `R C M` + mine coords → board of `*` and `.` |
| 2 | Adjacent-mine counts | Same input → digits in safe cells |
| 3 | Click & flood-fill reveal | Input adds a final `click r c` line → unrevealed cells shown as `#`, or `BOOM` |

**(Proposed) Playable Finale:** For game-like projects (Pong, Snake), design the final stage as a "tick program" (input = state + key press, output = new state + frame) so the frontend can loop the player's program in the browser and let them actually play what they built on the victory screen.

### 2.3 Incremental Stages & Checkpoint Rollback
* Each campaign consists of **2 to 5 cumulative stages**, where each stage builds directly on the previous one (for example, Stage 1 renders a 20x20 grid and places a ball; Stage 2 adds paddles; Stage 3 adds velocity, wall bounces, and scoring).
* **On Stage Pass:** The player's working Python code is saved as a verified **Checkpoint** in PostgreSQL, the stage timer resets, and Stage $N+1$ unlocks with the player's passing code pre-loaded in the editor.
* **On Stage Fail or Timeout:** If the player runs out of time, hits a syntax/runtime error, fails a hidden test case, or exceeds the per-test time limit, they lose **1 Life**. The stage restarts from the **last saved checkpoint code** so a broken edit never soft-locks the run.
* **Victory & Game Over:** Completing the final stage defeats the Overlord and posts the run to the global leaderboard. Dropping to **0 Lives** ends the campaign in defeat.

### 2.4 Submission Evaluation (Tests Only — No LLM)
There is **no player-written explanation** and **no LLM involved in grading**. When the player clicks **Submit** (or the countdown hits `00:00`):

1. The code is sent to the **server-side sandbox** ([§5.2](#52-sandboxed-execution)).
2. For each hidden test, in order, the sandbox runs `python main.py` with the test input piped to `stdin`, a per-test timeout (~2 s), and CPU/memory limits. `stdout` and `stderr` are captured separately.
3. Output is **normalized** (trailing whitespace stripped from each line, trailing blank lines ignored) and compared to the stored expected output.
4. Evaluation **stops at the first failing test**.

**Outcomes:**
* **All tests pass** → stage cleared, checkpoint saved, stage points awarded.
* **Any failure** (wrong output, syntax/runtime error, timeout) → *"Human hallucination detected"*, **−1 life**, rollback to last checkpoint.

**(Proposed) Failure Feedback by Tier** — not knowing *why* you lost a life is the biggest source of frustration:
* **Beginner–Medium:** show the failing hidden input, expected output, actual output (as a diff), and any traceback.
* **Hard–Impossible:** show only *"Hidden test N failed"* plus the traceback if the program crashed.

**(Proposed) Contest the Verdict:** A button after a failed Submit that flags the test. On Beginner/Easy it refunds the life immediately with an in-character line (*"…Reviewing logs. That test may have been a hallucination. This conversation never happened."*). If several players fail or contest the same hidden test, the campaign is automatically **quarantined** from the pool for team review.

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
| **Beginner** | 2 | 4 min | 4 | 1.0x | Password Strength Checker, Café Tab Splitter |
| **Easy** | 3 | 5 min | 3 | 1.25x | Vending Machine State Tracker, Hangman, RPN Calculator |
| **Medium** | 3 | 6 min | 3 | 1.5x | **ASCII Pong**, Minesweeper Grid Generator |
| **Hard** | 4 | 7 min | 3 | 2.0x | ASCII Snake, Wave Defense Simulator |
| **Expert** | 5 | 8 min | 2 | 2.5x | Dungeon Maze Pathfinder, Turn-Based Combat Engine |
| **Impossible** | 5 | 8 min | 1 | 3.0x | Mini Stack VM, CPU Process Scheduler |

Beginner and Easy should lean heavily on the **hand-checked seed library**; LLM-generated campaigns fill out Medium and above.

### 3.2 Sample Runs vs. Official Submissions
* **Run Sample (Unlimited, No Life Penalty):** Runs the player's code **in the browser via Pyodide** (Python compiled to WebAssembly) against the 1–2 visible sample cases. Instant, no server load, and shows stdout, tracebacks, and a diff against the expected sample output.
* **Submit Stage (Graded, Costs 1 Life on Failure):** Clicking **Submit**—or letting the countdown timer reach `00:00`—runs the hidden tests in the **server sandbox** ([§2.4](#24-submission-evaluation-tests-only--no-llm)). Hidden inputs and expected outputs never leave the server.

### 3.3 Deterministic Leaderboard Scoring
All scoring calculations live in a dedicated Python `ScoreCalculator` service class:

* **Stage Points:** `(100 + (seconds_remaining * 2)) * difficulty_multiplier`
* **Survival Bonus (on Campaign Win):** `remaining_lives * 150`
* **Total Campaign Score:** Sum of all cleared stage points plus the survival bonus. Failed campaigns (`0` lives remaining) award `0` leaderboard points while still incrementing `campaigns_played` on the player's profile.

Because every player who receives a given campaign gets identical hidden tests and expected outputs, scores are comparable on the leaderboard.

---

## 4. Campaign Generation & Validation Pipeline

The biggest risk to "fun, not frustrating" is a **wrong hidden test**. The pipeline below exists to make sure that never reaches a player. It runs **offline as a background job**, never when a player starts a run.

AI-generated campaigns are **optional story US11** in the course backlog ([roadmap.md §11](roadmap.md#11-user-stories)); the game is complete on hand-written seed campaigns without it. The validator and consensus checks (§4.4) are built first for the seed library either way.

### 4.1 Core Rule
**The LLM never writes expected outputs, and never grades its own work.** The LLM generates *content* (specs, starter code, test **inputs**, candidate solutions). **Our code** computes expected outputs by running solutions in the sandbox, and **our code** decides whether a campaign is valid.

### 4.2 Division of Labor

| Who | Writes what | When |
| :--- | :--- | :--- |
| Dev team | Generation prompt template, campaign JSON schema, test harness, validator | Once (Sprint 1) |
| LLM (generator) | Whole campaign: every stage's prompt, I/O format, starter code, sample inputs, hidden test **inputs**, input validator | Offline, filling the pool |
| LLM (×3 solvers) | Independent solutions per stage, seeing **only** what the player sees | Offline, during validation |
| Our code (sandbox) | **Expected outputs** = output all solvers agree on | Offline, during validation |
| Player | One program per stage that follows the I/O contract | During the game |
| Our code (harness) | Runs the program on hidden inputs, compares stdout | On Submit |

### 4.3 Pipeline Steps (per campaign)
1. **Generate (1 LLM call):** The generator returns the **entire** campaign as JSON matching our schema—title, all stages, each with the Overlord's plain-text prompt (stating the exact input/output format and examples), starter code, 1–2 sample inputs, 6–12 hidden test inputs (covering edge cases: min/max sizes, corners, empty cases), and a small `validate_input.py` that asserts an input matches the stated format and constraints. Stage 3 exists before anyone plays Stage 1.
2. **Solve independently (~3 LLM calls per stage):** Three separate solver calls each write a solution using **only the player-visible spec, samples, and their own previous-stage solution**—mimicking a real player. Use two different models if available to reduce correlated mistakes.
3. **Compute expected outputs by consensus (our code):** Run every solver's solution on every input in the sandbox.
   * All solvers agree → that output becomes the expected output.
   * Solvers disagree → the spec is ambiguous for that input. Send the disagreement back to the generator once to clarify the spec; if they still disagree, drop that input or the whole campaign.
4. **Automated quality checks (our code):** reject the campaign if any check fails (see §4.4).
5. **Store (our code):** Pass → save to the pool with status `validated`. Fail → discard and generate another.

After this, the campaign is **frozen**. Grading during gameplay is purely "run program, compare stdout."

### 4.4 Automated Quality Checks

| Check | Catches |
| :--- | :--- |
| Every hidden input passes `validate_input.py` | Tests that violate the stated constraints |
| Reference solution produces identical output on 2 runs | Randomness / time dependence |
| Reference runs in < ~10% of the CPU time limit | Tests where a reasonable naive solution would time out |
| Stage N tests **fail** the Stage N‑1 reference solution | Stages that add nothing new |
| Tests fail an empty program and a program that just prints the sample outputs | Hidden tests that don't test beyond the samples |
| Reference diff from Stage N‑1 → N is within per-difficulty line-count bounds | Stages that secretly require a rewrite / are too big for the timer |
| Spec bans floats or states exact formatting (e.g. "2 decimal places") | Formatting traps |

### 4.5 Seed Campaigns
Hand-written seed campaigns use the **same JSON schema**. Humans write the specs, inputs, and reference solutions (skipping steps 1–2), and they go through steps 3–5 **in CI on every PR**, so hand-written campaigns are machine-checked too. The seed library doubles as the data for the LLM `fake` mode ([§6](#6-llm-usage--budget)).

### 4.6 Pool Management
* Each difficulty tier keeps a target number of `validated` campaigns; a background job (e.g. `make generate-campaigns`) refills a tier when it runs low.
* Campaign statuses: `validated` → `quarantined` (flagged by contests / failure spikes) → `retired` or back to `validated` after team review.

### 4.7 Campaign Schema (abridged example)

```json
{
  "title": "Minesweeper",
  "difficulty": "medium",
  "stages": [
    {
      "stage": 2,
      "prompt": "Your \"board\" is a sad grid of dots. Now every safe cell shows ... Example: `3 4 2`, `0 0`, `1 2` prints `*211`, `12*1`, `.111`. ...",
      "starter_code": null,
      "samples": [{ "input": "3 4 2\n0 0\n1 2", "expected_output": "*211\n12*1\n.111" }],
      "hidden_tests": [
        { "input": "1 1 0", "expected_output": "." },
        { "input": "3 3 1\n2 2", "expected_output": "...\n.11\n.1*" }
      ],
      "reference_solution": "..."
    }
  ]
}
```

`expected_output` fields are filled in by the validation pipeline, never by the generator. `starter_code` is `null` for stages after Stage 1 (the player's checkpoint is used instead).

---

## 5. System Architecture

### 5.1 Components

```
Player's browser ──────► Flask web app (container: web) ─────► Azure OpenAI
  server-rendered pages   • presentation: routes, templates        • model deployment only
  Monaco editor           • business: game, grading, scoring       • receives prompts,
  Pyodide (samples)       • data: models + repositories              returns text
                          • LLM module (fake / replay / live)        (optional US11)
                          • token ledger + spending cap
                                │                 │
                                ▼                 ▼
                     PostgreSQL (container: db)   Sandbox runner (container: runner)
```

* **Azure is only the AI engine.** It hosts the model deployment and nothing else—no game logic, no database, no code execution.
* **Only the backend talks to Azure.** The browser never sees the API key.
* **Stack (decided 2026-11-17):** Flask (Python) with Jinja templates in a three-layer architecture (presentation / business logic / data access), PostgreSQL via SQLAlchemy repositories, a game page built from native browser ES modules (no build step; Alpine.js optional) using Monaco and Pyodide from a CDN, and Docker Compose with three containers. Full details in [roadmap.md §3–4](roadmap.md#3-tech-stack).

### 5.2 Sandboxed Execution
Player code is untrusted. Submit (and the validation pipeline) runs code only inside a locked-down **runner** container:
* internal-only network (**no internet**), no secrets in its environment
* each test runs as an unprivileged user in a fresh temp directory and its own process group, killed afterward
* CPU, memory, file-size, process-count, and wall-clock limits per test; output size capped
* read-only root filesystem, all capabilities dropped

**(Proposed)** Build this as a small **custom runner service** rather than using Judge0, whose sandbox needs privileged containers and has historically required cgroup v1, which clashes with Docker Desktop and Codespaces (details in [roadmap.md §3.2](roadmap.md#32-why-a-custom-runner-instead-of-judge0)). The same sandbox serves both Submit grading and campaign validation.

---

## 6. LLM Usage & Budget

**Budget:** $100 of Azure credit for the one-month project.

### 6.1 When the LLM Is Called
* **Campaign generation** (generator + solver calls) — offline, background job.
* **(Optional)** a few live Overlord quips; most dialogue is pre-written.
* **Never** during grading, run start, or bonus-life decisions. The game is fully playable with no LLM access.

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
* **Scrum board:** GitHub Projects with To Do / In Progress / In Review / Done; issues titled by story (`US6: …`). Task status lives on the board, not in agent instruction files.

---

## 8. Open Questions

* Final bonus-life trigger rule ([§2.5](#25-bonus-life)).
* Failure-feedback detail on Hard+ tiers, and whether "Contest the Verdict" ships ([§2.4](#24-submission-evaluation-tests-only--no-llm)).
* Custom runner vs. Judge0 ([§5.2](#52-sandboxed-execution)).
* On a failed Submit, keep the player's edits (with a "Restore checkpoint" button) instead of wiping to the checkpoint ([§2.3](#23-incremental-stages--checkpoint-rollback)); and whether the timer resets after a failure.
* Public hosting is optional (grading runs via Docker); decide only if we want a live class demo, and keep it off the Azure credit.
* Campaign pool size per tier and generation budget per campaign (tune from real ledger costs).
* Playable finale for game-like projects ([§2.2](#22-the-stage-contract-stdin--stdout)).
