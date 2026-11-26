# RM1a, round 7: Scenario AQ says what round 6 built, and a check holds it (the conductor, 26 November 2026, 14:55 UTC)

From the round-6 verifier's record (tip `b173404e49`): one fault, one gap. Rounds 5 and 6 stand. **This round is the two
rows below and nothing else.** (Round 7 of 8: say plainly in your report if anything else is open.)

| # | Do | Done when |
| --- | --- | --- |
| 1 | **Scenario AQ (`spec/08_ACCEPTANCE_SCENARIOS.md` about 908 and 911) is this slice's own scenario:** row AQ10 still says "`/alert-queue` is the `alerts-rules-watches` row's route", and line 911 "the route names the first". Say what was built: the row's `route` stays `""` until the whole function has its page (as AD3a's `admin` and GR4a's board rows do), the row is in `INCOMPLETE_ROWS`, and `/alert-queue` is in the tree's route list as the queue's own page. Change no other spec text. | `git grep -n "row's route" -- OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md` finds no claim that the row's route is `/alert-queue`; AQ10's text, `FUNCTIONS.yaml`, `alert-queue.test.ts` and the scenario test agree. |
| 2 | **The gap (`test_govuk_alert_queue_scenario.py` about 171-236):** no check compares what Scenario AQ says about the row's route with the row. Add one that reads AQ's route sentence(s) and the row's `route` in `FUNCTIONS.yaml` and fails when they disagree, with a `PLANTS` entry putting the round-5 sentence ("`/alert-queue` is the `alerts-rules-watches` row's route") back into the section: red, then restored (rule 15). | The new check red with the plant, green without; your frozen checks green. |


## Continued after round 7 passed (the owner's send-back line, 26 November 2026, 20:15 UTC): the conflicts only

**Rows 1 and 2 above are done and verified (`686379a089`); do not redo them.** The line kept this at round 7 (a conflict spends no round); the owner allows this one round only.

Round 7 is verified at `686379a089`. GR4a (`300e3fe`) and GR1a (`5614900`) merged since, and RM1a conflicts with main in
`spec/08_ACCEPTANCE_SCENARIOS.md`, `test_govuk_admin_people_scenario.py`, `test_govuk_help_scenario.py`,
`test_govuk_pack_trends_scenario.py`, `test_tree_parity.py`, `test_pages_setting.py`, `server/pageList.ts`,
`test/govuk/admin-people.test.ts`, `test/govuk/help.test.ts` and `tree-govuk/routes.yaml`. **This is the last round
(the owner's word): this row and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | Merge main into your branch. **Append-only, both sides kept, main's first:** in every shared list (page lists, route lists, `FUNCTIONS.yaml` rows, scenario rows, pinned counts and the tests that pin them), main's entries stay as main has them, in main's order, and RM1a's are added after them. A pinned count becomes main's count plus RM1a's own. Change nothing of rounds 1 to 7, and nothing else. If a pin or a scenario row cannot hold both without changing what a test asserts, **stop and say which**: do not choose. | Your frozen checks green on the new tip; `git diff main...HEAD` is round 7's diff with main's changes added, and in every shared list main's entries come first and unchanged. |
