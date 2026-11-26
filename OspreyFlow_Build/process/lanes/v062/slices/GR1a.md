# Slice GR1a · GR1 · The reader's cases and one case's page with its brief, read-only, on the GOV.UK tree (round 1 merges `away/GR1a`; the owner, 25 and 26 November 2026)

- **Build id:** GR1 (the cases-and-views row of `apps/pages/FUNCTIONS.yaml`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** nothing on main (it enters through its away branch, D247)
- **The owner's rulings:** 25 November (every proposal (a) of `slices/drafts_2026-11-25/GR1a.md`; GR1a starts before GG2b by his exception) and 26 November, about 10:35 UTC (`RULINGS.md`): question 2 "who made it" left out for 0.7.0 (names later through `display_names`, a backlog part); questions 3 to 5 (a). **Question 1, the address, is not named in the 26 November batch: build it as the away branch has it (`/cases` and `/cases?case=<id>`, the GR4a precedent; GR1c is not in the owner's order); the conductor confirms with the owner before the merge.**

## Round 1 (D247; the conductor, 26 November 2026): merge `away/GR1a` first

**Your first step: merge the local branch `away/GR1a` into your branch** (the owner fetched it to the Mac; D247's exception
for away rounds). Keep both sides where main has moved. Its report, `process/lanes/v062/away/GR1a_AWAY_REPORT.md` on that
branch, is the record of the away round: read it whole. **Every figure in it was taken on the server under its namespace;
none is a measurement here.**

**Where main has moved (expect conflicts, keep both):** GR3a (merged) and GR4a (building; whichever of GR1a and GR4a merges
second takes both) change the same lists the away branch changes: `OspreyFlow_Core/apps/pages/scripts/build.mjs`'s entries
(GR4a adds `packTrendsWords.ts`, GR1a `casesWords.ts`; both move `outfile` to `outdir`), `server/types/glassShared.d.ts`,
`tree-govuk/routes.yaml`, `server/pageList.ts`, `FUNCTIONS.yaml`, the route-list pins (HP7/HP9/HP10, AP10,
`test_govuk_help_scenario.py`, `test_govuk_admin_people_scenario.py`, `test_tree_parity.py`, `test_pages_setting.py`), and
`spec/08`'s scenario order (every GOV.UK scenario before Scenario S). **Take every page's entry in each list; drop none.**
Since IS5a0 the registry refuses two pages under one id (`server/pages.ts`); the cases page keeps its own row,
`cases-and-views`.

Then:

1. **The rulings, as built:** questions 2 to 5 stay as the away branch built them (2: `created_by` left out and named in
   Scenario CS's "Left out, by field name"; 3: "None shown"; 4: three reads per case page, the case read once; 5: the
   Conduit's order). Write the backlog row's words for question 2 in your report (a later Conduit part names the maker
   through `principal_names.display_names`, as the questions route does at `services/api/app.py` about lines 8280 and
   8281); the conductor adds the row.
2. **Show the report's table green here:** `cases.test.ts` (22), `test_govuk_cases_scenario.py` (39), the GOV.UK keyboard
   and scripts-off specs (`npm run test:keyboard:govuk --workspace apps/pages`), and the route-list pins. Run three of
   the report's planted faults again at the real call site (rule 15): a case skipped (CS1), the brief's 403 passed through
   in its own words (CS7), a slash in `case` passed on (CS6). Restore each from a saved copy, never by `git checkout`.
3. **Say whether `assetsTraversal.test.ts` and `foundation.test.ts` pass here** (the away report put their two failures
   down to the namespace's dot-named `TMPDIR`).

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/cases.test.ts` and `OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py`
(both from the away branch; neither is on main, so both are red on main and green after round 1's merge).

## Checks (pure; store ports pinned to 9)

`npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`; `node scripts/no_react_check.mjs`; the GOV.UK
scenario tests (cases, help, admin people), `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`,
`test_pages_foundation.py`, `test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`,
`tests/harness/test_pages_setting.py`; `ruff check .`. (`test_doc_citations_check.py` is left out while main is red on
it from a line hand-back; the merge's full gate runs `citation-check`.)

## Out of scope

Named path parts (GR1c, only if the owner rules question 1 (b)); New case (GR1b); saved views (GR1d); history (GR1e); any
Conduit change; the axe scan the GOV.UK tree lacks (named in the away report: its own part).
