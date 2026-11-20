**Value** 3 · **Points** 3 · **Priority** 1.00 · **Depends on** US2 · **Type** Required · **Sprint** 1

As a player, I want to pick a difficulty tier and start a campaign so that I can get a challenge that matches my skill.

## Why
This is the doorway into the game: the player chooses how hard they want it, and the game hands them a campaign they haven't seen. It also creates the campaign data that US4–US11 all read.

## Scope
**In:** the start screen with all six tiers, starting a run, campaign assignment, the `GameRun` record, the campaign JSON schema and seed loader, and the first hand-written seed campaigns.
**Out:** showing the stage and the editor (US4), the timer (US8), AI-generated campaigns (US11), the tutorial (US15).

## Acceptance Criteria
1. **[HIGH]** Given that I am logged in, when I open the start screen, then I see all six tiers with their stage count, time per stage, starting lives, and score multiplier.
2. **[HIGH]** Given that I have chosen a tier, when I click Start, then I am assigned a validated campaign I haven't played (or the one I played least recently), my lives are set from the tier, and Stage 1 opens.
3. **[MED] (proposed)** Given that a tier has no validated campaign yet, when I view the start screen, then that tier shows "Coming soon" and can't be started (no error page).
4. **[MED] (proposed)** Given that I already have a run in progress, when I open the start screen, then I see a "Resume run" option, and starting a new run ends the old one as abandoned (it scores 0).
5. **[HIGH] (proposed)** Given that I click Start, when the run is created, then no LLM call is made (campaigns come only from the pre-validated pool).
6. **[LOW] (proposed)** Tier card design, and how to break a tie between equally eligible campaigns.

## Rules & Details
Tier values, copied from [game-design §3.1](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#31-difficulty-tiers):

| Tier | Stages | Time / stage | Lives | Multiplier |
| --- | :---: | :---: | :---: | :---: |
| Beginner | 2 | 4 min | 4 | 1.0x |
| Easy | 3 | 5 min | 3 | 1.25x |
| Medium | 3 | 6 min | 3 | 1.5x |
| Hard | 4 | 7 min | 3 | 2.0x |
| Expert | 5 | 8 min | 2 | 2.5x |
| Impossible | 5 | 8 min | 1 | 3.0x |

**Campaign assignment** (`CampaignSelector`), for a player and tier:
1. Only campaigns with status `validated` and that difficulty are eligible.
2. If any eligible campaign has never been played by this player, pick one of those.
3. Otherwise, pick the one this player most recently started the *longest* time ago.
4. If none are eligible, raise `NoCampaignAvailableError`. The route shows "No campaigns for this tier yet." and stays on the start screen.

**New run:** `lives` = the tier's starting lives, `current_stage` = 1, `status` = `in_progress`, `score` = 0, and `started_at` and `stage_started_at` set to now (US8 uses this for the timer).

**A run belongs to its player.** Anyone else opening it gets a 404.

## UI
- **Route:** `GET /start` (login required) shows the tier cards. `POST /runs` with `difficulty` starts a run and redirects to `/play/<run_id>` (that page's content is US4).
- **Elements:** `start-tier-<tier>` (card, for example `start-tier-beginner`), `start-tier-<tier>-stages`, `-time`, `-lives`, `-multiplier`, `start-tier-<tier>-button`, `start-tier-<tier>-coming-soon`, `start-resume-run`, `start-error`.
- The home screen gets a big "Start a run" link to `/start`.

## Technical Notes
- **Presentation:** `src/presentation/game_routes.py` (blueprint `game`), `templates/game/start.html`.
- **Business:** `Difficulty` enum with the table above as data (one source in code, matching the doc). `CampaignSelector.choose(user_id, difficulty)`. `GameService.start_run(user, difficulty) -> GameRun` (abandons any in-progress run first).
- **Data:** `Campaign`, `Stage`, `TestCase`, and `GameRun` models + migrations. `CampaignRepository.validated_for(difficulty)`, `RunRepository.last_started_by_user(user_id)`, `RunRepository.active_for(user_id)`.
- **Content:** `content/campaigns/seed/<tier>/*.json` in the [§4.7 schema](https://github.com/msu-denver/rokos-tasks/blob/dev/docs/game-design.md#47-campaign-schema-abridged-example). `make seed` loads them (safe to run twice). `make validate-campaigns` checks the schema and runs each reference solution against its tests.

## Test Plan
| AC | Test | Type |
| --- | --- | --- |
| 1 | Start screen lists six tiers with the table's values | integration |
| 1, 2 | Log in → Start → pick Beginner → lands on `/play/<id>` | e2e |
| 2 | `CampaignSelector`: unplayed preferred; all played → least recent; only `validated` used | unit |
| 2 | `start_run` sets lives from the tier, stage 1, `in_progress` | unit |
| 3 | Empty tier → `NoCampaignAvailableError`, and the card shows "Coming soon" | unit + integration |
| 4 | Existing run → abandoned when a new one starts, and "Resume run" links to it | unit + integration |
| 5 | `start_run` makes no LLM call (the LLM client is never constructed; assert with a fake that fails if called) | unit |
| — | Every seed file passes `make validate-campaigns` | CI |

## Tasks
- [ ] T6: US3: Campaign schema, difficulty tiers, and seed loader
- [ ] T7: US3: Write the first seed campaigns
- [ ] T8: US3: Start screen and start-run flow

## Open Questions
- How many seed campaigns for `v1`: one Beginner + one Easy, or one per tier? (Product Owner)
- Is AC4 (resume or abandon) the behavior we want, or should starting a new run be blocked while one is active? (Product Owner)
