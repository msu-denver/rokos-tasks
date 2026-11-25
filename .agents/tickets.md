# Writing Tickets

Every GitHub issue follows one of three shapes: **story**, **task**, or
**tech debt**. Copy the skeleton, fill in every section, and delete
nothing. If a section doesn't apply, write "None."

Templates: [.github/ISSUE_TEMPLATE/](../.github/ISSUE_TEMPLATE/).
Finished examples: the Sprint 1 story drafts in
[scrum/sprint_1/issues/](../scrum/sprint_1/issues/).

## Contents
1. [Labels](#labels)
2. [Acceptance criteria ratings](#acceptance-criteria-ratings)
3. [Story](#story)
4. [Task](#task)
5. [Tech debt](#tech-debt)
6. [Writing rules](#writing-rules)
7. [Ready and done](#ready-and-done)
8. [Posting](#posting)

## Labels

Every issue has **exactly one type label and exactly one priority
label**.

| Type | For |
| :--- | :--- |
| `story` | A user story (`US#`) |
| `task` | Process work with no story (`Chore: …`, `Scrum: …`) |
| `tech-debt` | A MED/LOW/NIT finding deferred while reviewing someone else's PR |
| `bug` | Something that worked and is now broken (task shape, title `Fix: …`) |

| Priority | Means |
| :--- | :--- |
| `P0` | Critical: drop everything and do it now. |
| `P1` | High: do it next, ahead of the usual backlog. |
| `P2` | Normal: schedule it through the backlog. Default for tech debt. |

The Product Owner can change a priority at any time.

## Acceptance criteria ratings

Every acceptance criterion gets exactly one rating:

| Rating | Means | Who decides |
| :--- | :--- | :--- |
| **[HIGH]** | Set in stone. The PR can't merge unless it's met exactly. | Product Owner |
| **[MED]** | Expected. Any deviation is explained in the PR, and the reviewer accepts or rejects it. | Product Owner |
| **[LOW]** | Up to the implementer (human or agent). Any reasonable choice is fine. | Implementer |

When an agent drafts a ticket, it *proposes* ratings and marks new
criteria **(proposed)**. The Product Owner confirms them, and removes the
marks, before the ticket leaves **To Do**.

## Story

**Title:** `US#: Title` exactly as in the README (for example,
`US1: Register`). **Labels:** `story` + a priority
([Labels](#labels)). The body opens with the sprint, the story points, and what it depends
on, so readers see them first. Value, priority, and type go on the
second line. Points are Fibonacci: 1, 2, 3, 5, 8, 13.

```markdown
**Sprint N** · **<points> points** · **Depends on** #<n> (US#) or —

**Value** 1–3 · **Priority** value ÷ points · **Type** Required/Optional · **Label** P0/P1/P2

As a <role>, I want <goal> so that I can <benefit>.

## Why
1–3 sentences: the player's problem and why it matters.

## Scope
**In:** what this story delivers.
**Out:** what it doesn't, and which story or decision covers it.

## Acceptance Criteria
1. **[HIGH]** Given that <context>, when <action>, then <observable result>.

## Rules & Details
Exact limits, formats, and user-facing messages (quoted word for word).

## UI
Route(s), what's on screen, states (empty, loading, error), and the
`data-testid` of every element a test touches.

## Technical Notes
Expected classes and files, by layer: presentation / business / data.
A guide, not a requirement, unless an AC says otherwise.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |

## Tasks
- [ ] **<task>** · Depends on: <other task, #<n>, or none>
  - **What:** 1–2 sentences.
  - **[HIGH]** <checkable statement>
  - **Notes:** files or gotchas. **Tests:** which tests.

## Open Questions
- <question> (who answers)
```

## Task

**Title:** `US#: <verb phrase>` (for example,
`US1: Add the data layer`). Process work with no story uses
`Scrum: …` or `Chore: …`, and a bug uses `Fix: …` (label `bug`).
**One issue per story.** Never split a story into separate task
issues. The story's work goes in its **Tasks** checklist instead. Use a
separate task issue only for process work with no story (`Chore: …`,
`Scrum: …`) or a bug (`Fix: …`).

**Labels:** `task` + a priority. **Tasks have no story points.** The
task's first line shows its sprint and what it depends on.

```markdown
**Sprint N** · **Story** none · **Depends on** #<n> or —

## What
1–3 sentences.

## Acceptance Criteria
- **[HIGH]** <checkable statement>

## Notes
Files or areas likely touched. Gotchas.

## Tests
Which tests this task adds (unit / integration / e2e).
```

## Tech debt

**Title:** `Tech debt: <summary>`. **Labels:** `tech-debt` + a
priority (`P2` unless the reviewer says otherwise). Open one whenever
a MED, LOW, or NIT finding on someone else's PR is deferred instead of
fixed. Never open one from a self-review of your own code: fix it, or
ask your human.
The Product Owner schedules it. Nobody fixes it silently in an unrelated
PR.

```markdown
**From** PR #<n> · `path/file.py:line` · **Original severity** MED/LOW/NIT · **Story** US# or none

**Problem:** one line.
**Why deferred:** one line.
**Suggested fix:** one or two lines.

## Acceptance Criteria
- **[HIGH]** <checkable statement>
```

## Writing rules

1. **Each criterion tests one observable behavior.** Use Given/When/Then
   for stories. Say what the user sees or what data changes, not how the
   code works. The only exception is when the "how" is itself the rule
   (for example, "passwords are hashed").
2. **Every story has at least one [HIGH] and no more than about 6
   criteria.** More than that means the story should be split.
3. **Quote user-facing text word for word** in Rules & Details. Tests
   assert those strings, so they must match exactly.
4. **Name every `data-testid`** a test will use, in kebab-case as
   `<screen>-<thing>` (for example, `register-username`,
   `game-lives`). Selenium tests and the HTML agree because both come
   from the ticket.
5. **Map every criterion to at least one test** in the Test Plan. Every
   [HIGH] criterion on a screen gets an e2e (Selenium) test.
6. **Out of scope names where the work lives instead**, for example
   "Timer: US8" or "Password reset: not planned."
7. **Numbers come from the docs.** Copy tier values, limits, and scoring
   rules from [game-design.md](../docs/game-design.md) and link the
   section, so there's one source. Relative links don't work in issue
   bodies, so use full URLs:
   `https://github.com/msu-denver/rokos-tasks/blob/dev/docs/...`.
8. **Keep the README in sync.** The README holds each story's sentence
   and its rated criteria. The issue holds everything else. When
   criteria change, update the README in the same PR.

## Ready and done

**Ready**, meaning it can be pulled into a sprint:
- every criterion is rated and confirmed by the Product Owner;
- the stories it depends on are done, or come earlier in the sprint;
- the Test Plan is filled in;
- no open question blocks a [HIGH] criterion.

**Done:** the Definition of Done in
[roadmap §9.6](../docs/roadmap.md#96-definition-of-done) is met, and the
issue is closed after its PR merges into `dev`
([workflow §8](workflow.md#8-after-merge-close-the-issue)).

## Posting

```bash
gh issue create --title "US1: Register" --label story --label P1 --body-file scrum/sprint_1/issues/US1.md
```

Don't create task issues or sub-issues for a story's work: it stays
in the story's Tasks checklist. Task status lives in the issues
themselves. There is no Project board.
