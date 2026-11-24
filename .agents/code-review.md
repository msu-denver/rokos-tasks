# Code Review Rubric

Use this rubric for agent self-review before a PR and for every review on
a PR, whether a human or an agent is reviewing.

## Severities

| Level | Means | Blocks merge? |
| :--- | :--- | :--- |
| **HIGH** | Wrong, unsafe, or breaks a rule | **Always.** The reviewer uses "Request changes." |
| **MED** | A real problem that costs more the longer it sits | Only if it will **break upcoming code** or **must be fixed now** (see below). Otherwise, open a tech-debt issue. |
| **LOW** | A minor quality issue | Same rule as MED. Rarely meets it. |
| **NIT** | Preference or polish | **Never.** The author may ignore it. |

**Always HIGH:**

- Incorrect behavior or a bug on a real path, or a **[HIGH] acceptance
  criterion** that isn't met.
- New behavior without tests, a failing or skipped test, or coverage
  under 90%.
- Breaking any non-negotiable in [AGENTS.md](../AGENTS.md): a live LLM
  call, secrets, a layer violation, a missing header comment, a weakened
  runner sandbox, a hand-edited `htmlcov/`, a check script loosened to make a
  program pass.
- Security problems: injection, missing auth check, CSRF disabled,
  player code escaping the sandbox.
- Data loss or a migration that can't be rolled back.
- A PR body missing `## Manual Testing`, with more than one sentence
  there, or without exactly one screenshot. This is an **automatic
  reject**: request changes without reviewing further.

**Usually MED:** missing edge-case tests, swallowed or overly broad
exceptions, a **[MED]** AC unmet without an explanation, logic in the
wrong class, duplication that will spread, confusing control flow.

**Usually LOW:** unclear names, long functions, magic numbers, thin
docstrings, small duplication.

**NIT:** wording, ordering, anything the linter accepts that you'd just
write differently.

## When a MED or LOW blocks

Request changes for a MED or LOW **only** if one of these is true, and
say which one in the comment:

- **Breaks future code:** work planned in this sprint or the next will
  build on it and break or need rework (for example, a public interface,
  a DB schema, a campaign JSON field).
- **Must be fixed now:** fixing it later costs much more than fixing it
  now (for example, a migration already on `dev`, or a pattern about to
  be copied into other stories).

Otherwise, **approve**, and the reviewer opens a `tech-debt` issue for it
([tickets.md](tickets.md)) and links it in the review. Development keeps
moving, and nothing gets lost.

## Ending the ping-pong

- **The first review raises everything at once.** Don't save findings
  for later rounds.
- **Later rounds only check the earlier findings and the new commits.**
  New findings on unchanged code are allowed only if they are HIGH.
- **After two "Request changes" rounds on the same PR, stop commenting
  and talk** (at stand-up or on a call). Decide together, and record the
  decision in the PR.
- If the author disagrees with a severity, they reply once with their
  reasoning. The Scrum Master breaks ties.

## Format

One finding per comment, inline on the line when possible:

```
**[HIGH]** `src/business/grading_service.py:42`: A program that crashes
on its first tick is reported as a pass, because the verdict only looks
for a broken rule.
**Fix:** treat an exit before the last tick as a fail with the traceback.
```

Put this summary at the top of the review body:

```
**Verdict:** Request changes | Approve | Comment
HIGH 1 · MED 2 · LOW 0 · NIT 3
Deferred to tech debt: #57 (MED: retry logic in RunnerClient)
```

## What to check, in order

1. **PR format.** `## Manual Testing` has one sentence and one
   screenshot. If it doesn't, reject now.
2. **Acceptance criteria.** Every [HIGH] AC is met (check each one
   line by line). [MED] deviations are explained.
3. **Correctness.** Edge cases, error paths, off-by-ones, timeouts,
   empty input.
4. **Tests.** They test behavior rather than implementation, cover the
   failure paths, and include an e2e (Selenium) test for user-facing
   changes. Coverage is at least 90%.
5. **Non-negotiables.** Everything listed in [AGENTS.md](../AGENTS.md).
6. **Standards.** See [coding-standards.md](coding-standards.md).
7. **Design** (any UI change). Check it against [docs/design.md](../docs/design.md). A hard-coded color, font, or size is MED. Helper text, emoji, or off-palette accents are LOW. A breach of design.md §9 "Never" is at least MED.

## Agents reviewing someone else's PR

- Post findings as **comments** (`gh pr review <n> --comment`).
  **Never** use `--approve`, and use `--request-changes` only if your
  human tells you to. The verdict belongs to a human.
- Review only the PR's diff and the issue it links. Don't push commits
  to someone else's branch.
