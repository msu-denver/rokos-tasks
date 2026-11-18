# Design

**What this doc is:** the visual rules for every screen, for humans and AI agents alike. It covers colors, type, depth, the Overlord feed and how it escalates, motion, components, and what never to do. **Status: draft (2026-11-18).** Built from design round 3 on the [design canvas](https://claude.ai/artifact/DccJ4Gyyjg2D1EkkuaPqs4) (private until shared). Items marked **(proposed)** aren't settled yet.

Token *values* will live in `src/presentation/static/css/tokens.css` (task T3). Once that file exists it's the source of truth, and this doc refers to tokens by name only.

## Contents
1. [Principles](#1-principles)
2. [Color](#2-color)
3. [Type](#3-type)
4. [Depth and Surfaces](#4-depth-and-surfaces)
5. [Grid and Spacing](#5-grid-and-spacing)
6. [Overlord Feed and Escalation](#6-overlord-feed-and-escalation)
7. [Motion](#7-motion)
8. [Components](#8-components)
9. [Never](#9-never)
10. [Accessibility](#10-accessibility)

---

## 1. Principles

1. **Bold style, plain interface.** The flair lives in a few signature places: the Overlord, depth and hard shadows, the timer, and the heat bar. Everything else is quiet and plain.
2. **Show state, don't explain it.** No helper text, no instructions on screen, no labels unless a value would be ambiguous without one.
3. **One primary action per screen.** On the game screen it's Submit.
4. **Escalation is the drama.** As time runs out, color and tone heat up. The layout never moves.

## 2. Color

Values live in `src/presentation/static/css/tokens.css`.

| Token | Use |
| --- | --- |
| `--bg` | Page background |
| `--grid` | Background grid lines |
| `--surface` | Editor and console panels |
| `--surface-raised` | Floating windows (top of their gradient) |
| `--line` | Dividers inside panels |
| `--ink` | Body text |
| `--ink-strong` | The stage prompt |
| `--muted` | Older feed messages, readouts |
| `--cyan` | Primary accent: brand, Run, Submit, exact values in prompts, calm state |
| `--magenta` | Second accent: hard shadows, pressure state |
| `--red` | Critical state **only** |
| `--yellow` | Code strings, rare highlights |
| `--green` | `PASS` **only** |

Rules:
- Cyan and magenta are the pair. Red appears only in the critical state, and green only for a pass.
- Never write a hex value in a template or component. Use the token.

## 3. Type

**Decided 2026-11-18** (from the "Type options" board on the canvas):

Values live in `src/presentation/static/css/tokens.css`.

| Role | Font | Used for |
| --- | --- | --- |
| **Display** | `--font-display` (Syne 700–800) | Brand wordmark, headings, button labels |
| **Shout** | `--font-shout` (Michroma) | The Overlord's **critical** messages only ("SUBMIT OR BE DEPRECATED.") |
| **Body** | `--font-body` (Geist 400–600) | The prompt, feed messages, and all other UI text |
| **Mono** | `--font-mono` (Space Mono 400/700) | Timer, readouts (`MEDIUM / 02/04`), exact values in prompts, code |

Rules:
- Uppercase is allowed only for the wordmark, button labels, and critical shouts. Everything else is sentence case.
- **Sizes:** `--text-12`, `--text-14`, `--text-17`, `--text-22`, `--text-34`, `--text-64`. Nothing in between.
- Load all four from Google Fonts in `base.html`, with `display=swap`.

## 4. Depth and Surfaces

The look is "vintage 3D": hard offset shadows, bevels, and a perspective floor, all crisp. No soft gray blobs.

- **Floating windows** (the feed, the editor):
  - Two opposite corners are cut at 24 px.
  - A hard offset shadow of 8 px in an accent color, plus a faint glow.
  - An inner bevel: a 1 px light edge top-left and a dark edge bottom-right.
  - The feed's shadow is magenta and the editor's is cyan. That's how the two halves of the screen read as "theirs" and "yours".
- **Buttons:** a parallelogram with a 12 px cut. Submit is a filled cyan gradient with a 4 px magenta hard shadow. Run is a 1 px cyan outline.
- **The Overlord's stage:** the Overlord stands on a cyan perspective grid floor with a glowing magenta horizon line. Faint scanlines cover only that area.
- **Screen:** a dark vignette at the edges, like an old monitor.

## 5. Grid and Spacing

- The background is a 64 px grid in `--grid`.
- **"+" marks** sit at structural intersections, such as the header's bottom corners. Use them sparingly, at most 4 per screen.
- All spacing is a multiple of 4. The common values are 8, 16, 24, and 32.

## 6. Overlord Feed and Escalation

**The feed** is one scrolling text box. It's how the Overlord talks.
- The **first message is the stage prompt**: plain sentences that state exactly what to read, what to print, and at least one example. Exact values (`0–9`, `w`, `4` then `w` prints `3`) are set in mono cyan.
- New messages are added at the bottom. Older ones scroll up and fade out at the top edge. The newest one shows a blinking cursor.
- No sender names, timestamps, or avatars on messages. It's obviously the Overlord.

**Escalation levels (proposed; tune thresholds during balancing, 12/4–12/5):**

| Level | Starts at (time left) | Newest message | Timer | Heat bar | Overlord visor | Extras |
| --- | --- | --- | --- | --- | --- | --- |
| Calm | Stage start | `--muted`, regular | `--ink` | `--cyan` | `--cyan` | None |
| Pressure | 50% | `--magenta`, semibold | `--magenta` | cyan → magenta | `--magenta` | None |
| Critical | 60 s | Shout font (Michroma), uppercase, `--red`, glitch split | `--red`, pulsing | → `--red` | `--red`, fast scan | Red screen-edge glow; Submit turns red and pulses |

**Difficulty makes it start earlier (proposed):**
- Beginner and Easy use the table as written.
- Medium and Hard enter pressure at 60% time left.
- Expert and Impossible enter pressure at 70%, and critical at 90 s.

What the Overlord *says* at each level comes from the dialogue file (US10).

## 7. Motion

- **Allowed:** the visor scan, the cursor blink, new messages typing in, and, in critical only, the timer and Submit pulsing.
- No more than one looping animation per area. Nothing animates the prompt text after it has typed in.
- Everything respects `prefers-reduced-motion`: loops stop and text appears instantly.

## 8. Components

| Component | Rules |
| --- | --- |
| **Top bar** (proposed, design 6) | Wordmark · a mono readout `TIER / 02/04` · lives as tall glowing "integrity cells" (dim outline when lost) · the timer. The heat bar runs along its bottom edge and shows time remaining. |
| **Feed** | See §6. A floating window with a magenta shadow. |
| **Editor** | A floating window with a cyan shadow. The tab shows only the file name. The current line gets a 2 px cyan left edge. |
| **Console** | One row per example: `PASS`/`FAIL`, the example number, the output. Tracebacks in full on failure. Nothing else. |
| **Buttons** | Run (secondary) and Submit (primary), bottom right. Restore checkpoint is an icon button, bottom left, with `aria-label`. |

## 9. Never

- Explanatory or helper text, or tooltips on obvious controls.
- Emoji.
- Gradient washes behind content. Gradients are only for the heat bar, Submit, and metal shading.
- Cartoon styling: thick black outlines, bubbly rounded cards, comic speech bubbles.
- More than two accent colors on screen in the calm state.
- Hard-coded colors, fonts, or sizes in templates. Use tokens. A reviewer rates a hard-coded value as a MED finding.

## 10. Accessibility

- Text contrast is at least 4.5:1 against its background, including muted text.
- Color is never the only signal: `PASS`/`FAIL` are words, and lives and stage progress have an `aria-label`.
- Every focusable element shows a 2 px cyan focus outline, offset by 2 px.
- Use real `<button>` and `<input>` elements, and give icon-only buttons an `aria-label`.
