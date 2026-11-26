# GR1a, round 1 (continued): take main in after GR4a (the conductor, 26 November 2026, 13:55 UTC)

Round 1 is verified at `746dedb`. GR4a merged (`300e3fe`) and conflicts with it in `spec/08_ACCEPTANCE_SCENARIOS.md`, the
GOV.UK scenario tests (`test_govuk_admin_people_scenario.py`, `test_govuk_help_scenario.py`, `test_tree_parity.py`),
`test_pages_setting.py`, `server/pageList.ts`, `tree-govuk/routes.yaml` and the pages tests. **This round is the row below
and nothing else; no round is spent (a conflict).**

| # | Do | Done when |
| --- | --- | --- |
| 1 | Merge main into your branch. **Keep every page from both sides:** GR4a's `/packs/trends` (its own id, `reports-trends-shown-together`) and your case pages; every route list, page list, `FUNCTIONS.yaml` row and pinned count holds both. Change nothing else. If a pinned count or a scenario row cannot hold both without changing what a test asserts, stop and say which. | Your frozen checks green on the new tip; `git diff main...HEAD` is round 1's diff with only main's changes added. |
