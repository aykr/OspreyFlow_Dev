# GR4a, round 3 (after main's merge): one id, two pages (the conductor, 25 November 2026, 23:25 UTC)

From the red stop at `58bbf57` (six tries). **One cause behind every red** (`test/server/start.test.ts` 4 of 12,
`test/govuk/alert-monitoring.test.ts` 120 of 121, and the rest): the page server refuses to start,
`PageRegistrationError: the id reports-figures is used by more than one page (/reports and /packs/trends): a page is one
row of FUNCTIONS.yaml.` GR3a (on main) gave `/reports` the id `reports-figures`; the away branch gave `/packs/trends`
the same id. The rule is the registry's since IS5a0 (`server/pages.ts:133-136`) and stays. **This round is the row
below and nothing else; both pages stay (the owner's word).**

| # | Do | Done when |
| --- | --- | --- |
| 1 | Give the board page its own row: a new id in `FUNCTIONS.yaml` (one row, its own; say the name you chose and why), and the same id in `tree-govuk/routes.yaml`, `server/pageList.ts` (its comment says the page is "a second page of the `reports-figures` row": make it say what the code does), and every test and scenario pin that names the board page's id. **`spec/08`'s `reports-figures` row is spec text: if it names the board page under that row, propose the one-line change in your report rather than editing the decision log.** | `npm test --workspace apps/pages` green (the server starts); no two rows of `FUNCTIONS.yaml` share an id; your frozen checks green. |
