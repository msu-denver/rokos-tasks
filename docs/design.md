# Design

**What this doc is:** the visual rules for every screen, for humans and AI agents alike. It covers colors, type, depth, the Overlord feed and how it escalates, motion, components, and what never to do. **Status: draft (2026-11-18).** Built from design round 3 on the [design canvas](https://claude.ai/artifact/DccJ4Gyyjg2D1EkkuaPqs4) (private until shared). Items marked **(proposed)** aren't settled yet.

Token *values* live in `src/presentation/static/css/tokens.css`. That file is the source of truth, and this doc refers to tokens by name only.

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
| `--magenta` | Second accent: hard shadows, pressure state. An anaglyph crimson (red with a trace of pink), the red lens to cyan's blue one. |
| `--red` | Critical state **only**. Warmer than `--magenta` so the two never blur together. |
| `--yellow` | Code strings, rare highlights |
| `--green` | `PASS` **only** |
| `--tier-*` | The difficulty badge **only**: a cool-to-hot ramp (Beginner cyan, Easy blue, Medium violet, Hard crimson, Expert orange). Impossible cycles all five. |

**Decided 2026-11-18:** the second accent moved from pink to an anaglyph crimson, for an old red/cyan 3D-glasses feel without being literal about it. The token keeps the name `--magenta`.

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
**Decided 2026-11-18** (the login and register pass): energy, holographic foil, and the anaglyph split below. Together they push the vintage 3D look toward old red/cyan 3D glasses, kept subtle.

- **Energy:** a floating window's accent shadow glows, and the glow breathes. A hot band runs along the shadow edge now and then, like current through a wire. Fields sit in a recessed well and glow cyan on focus. Primary buttons glow on hover and press halfway onto their shadow.
- **Holographic foil:** a floating window's top edge is a 1 px cyan-to-crimson foil (interpolated in OKLCH, so it passes through violet without adding a third accent token), and a faint white glint drifts across the surface. Both move with the energy loop.
- **Anaglyph split:** headings and the wordmark carry a faint offset of cyan on the left and crimson on the right, like a 3D print seen without glasses. 1–2 px only; it must never make text hard to read.

## 5. Grid and Spacing

- The background is a 64 px grid in `--grid`.
- **"+" marks** sit at structural intersections, such as the header's bottom corners. Use them sparingly, at most 4 per screen.
- All spacing is a multiple of 4. The common values are 8, 16, 24, and 32.
- **Widths (decided 2026-11-18):** content never spans the full screen. Page content caps at `--width-page` (18 grid cells) and centers. Forms and short pages use a narrow panel, `--width-form` (7 grid cells), centered. Inputs never stretch past `--width-form`.
- **Game screen (decided 2026-11-18):** the editor is the point, so the game screen caps at the wider `--width-game` (24 grid cells). On desktop (at least 960 × 560) it's a fixed app shell with no page scroll: the Overlord column keeps a readable measure (5.5–7 grid cells) and the editor takes everything else. Below that, the two windows stack and the page scrolls.

## 6. Overlord Feed and Escalation

**The feed** is one scrolling text box. It's how the Overlord talks.
- **Layout (decided 2026-11-18):** the Overlord window has two parts. The Overlord's stage is on top, with room beside him for his follow-up lines (US10). The prompt is pinned below and is always visible; when space runs short, the stage shrinks first, then the prompt scrolls.
- The **first message is the stage prompt**: plain sentences that state the feature, the controls, the characters on screen, and the rules the Overlord will check. Exact values (`q`, `a`, `O`, `20x20`) are set in mono cyan.
- New messages are added at the bottom. Older ones scroll up and fade out at the top edge.
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

- **Allowed:** the visor scan, the Impossible badge's rim, new messages typing in, the floating-window energy loop (§4), and, in critical only, the timer and Submit pulsing.
- The energy loop is ambient: one slow animation (`--energy-period`) drives the glow, the edge band, the foil, and the glint together, so a window counts as one loop.
- No more than one looping animation per area. Nothing animates the prompt text after it has typed in.
- Everything respects `prefers-reduced-motion`: loops stop and text appears instantly.

## 8. Components

| Component | Rules |
| --- | --- |
| **Top bar** (decided 2026-11-18) | Wordmark with the **difficulty badge** beside it: a neon parallelogram in the tier's `--tier-*` color; Impossible's rim cycles every tier color. Center: the timer (a static `00:00` until US8), with lives beside it as glowing diamonds (dim outline when lost). The **stage bar** runs along the bottom edge, one cell per stage: done is dim cyan, current is bright cyan, upcoming is dark. No `02/04` text; the bar's `aria-label` carries it. The heat bar (US8) drains the current stage's cell. |
| **Feed** | See §6. A floating window with a magenta shadow. |
| **Editor** | A floating window with a cyan shadow. The tab shows only the file name. The current line gets a 2 px cyan left edge. |
| **Console** | Shows each frame the program prints while it runs (US5). Tracebacks in full on a crash. Nothing else. |
| **Buttons** | Run (secondary) and Submit (primary), bottom right. Restore checkpoint is an icon button, bottom left, with `aria-label`. |

## 9. Never

- Explanatory or helper text, or tooltips on obvious controls.
- Emoji.
- Gradient washes behind content. Gradients are only for the heat bar, Submit, metal shading, the floating-window foil and glint, and the header's bottom hairline.
- Cartoon styling: thick black outlines, bubbly rounded cards, comic speech bubbles.
- More than two accent colors on screen in the calm state.
- Hard-coded colors, fonts, or sizes in templates. Use tokens. A reviewer rates a hard-coded value as a MED finding.

## 10. Accessibility

- Text contrast is at least 4.5:1 against its background, including muted text.
- Color is never the only signal: `PASS`/`FAIL` are words, and lives and stage progress have an `aria-label`.
- Every focusable element shows a 2 px cyan focus outline, offset by 2 px.
- Use real `<button>` and `<input>` elements, and give icon-only buttons an `aria-label`.
