# LLM Policy: Agents Never Call the API

The project has **$100 of Azure OpenAI credit for the whole month**.
One runaway loop could spend it. So **only humans make live LLM calls**,
deliberately and under supervision.

This is about *our project's* Azure credit. Your own model usage as an
agent is separate and isn't covered here.

## Agents must never

- Set `LLM_MODE=live`, anywhere: shell, `.env`, code defaults, test
  config, or Docker Compose.
- Run `make llm-smoke`, `make generate-campaigns`, or anything with
  `CONFIRM_LIVE=yes`.
- Call the Azure/OpenAI endpoint by any route: a script, `curl`, a
  Python REPL, or a notebook.
- Read, print, copy, or commit `.env`, `AZURE_OPENAI_API_KEY`, or any
  other key.
- Write code that defaults to `live`, or that silently falls back to
  `live` when something else fails.

## Agents may

- Write and change the code that *will* call the API (`src/business/llm/`)
  and the prompt files.
- Test that code with `fake` mode, `replay` fixtures, or a mocked client.
- Prepare a live run for a human: write the exact command and say what
  it will cost, then **stop and hand off**. For example: "Ready for a
  live smoke test. Run `CONFIRM_LIVE=yes make llm-smoke` (about 2k
  tokens)."

## If a task seems to need a live call

Stop. Tell your human what you need and why, and give them the command.
Don't look for another way to make the call.

## The running app

US11's background job refills the campaign pool by calling the LLM
itself. That's allowed only on a server where a human has set the key
and `LLM_MODE=live`, with the budget cap on. Agents never set either,
and the default stays `fake`.

## For the human LLM owner

- The only real protection is that agents never see the key. Keep it out
  of any `.env` file in a checkout where agents run, and supply it only
  in the shell session where you do the live run.
- Claude Code is blocked from these commands in `.claude/settings.json`.
  The other tools have no equivalent, so for them this policy is the
  guard.
