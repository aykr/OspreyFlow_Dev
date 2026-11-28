# Slice GR1d · GR1 · A case's saved views on its GOV.UK page: the list, saving a filtered view, sharing and deleting one's own (round 1 merges `away/GR1d`; the owner, 28 November 2026)

- **Build id:** GR1 (the cases-and-views row of `apps/pages/FUNCTIONS.yaml`).
- **After:** nothing on main. It enters through its away branch (D247), built on GR1a and GR1e, which are merged.
- **The owner's ruling:** 28 November 2026, about 12:10 UTC (RULINGS.md, item 2): **every proposal (a)** of `slices/drafts_2026-11-26/GR1d.md`, and (a) to each of the six questions in the away report. Who made a view is left out for 0.7.0.
- **Priority:** GR1d goes as early as the queue allows, because the Cases stream on the server (GR1f1 to GR1f3) waits for it.
- **GOV.UK page only** (item 6). The Default tree's twin is listed for 0.7.5.

## Round 1 (D247): merge `away/GR1d` first

**Your first step: merge the local branch `away/GR1d` into your branch.** It is in the main checkout. Keep both sides where main has moved.
- Its report, `process/lanes/v062/away/GR1d_AWAY_REPORT.md` on that branch, is the record of the away round: read it whole.
- **Every figure in it was taken on the server under its own namespace; none is a measurement here.**

**Where main has moved (expect conflicts; keep both):** GG3b, GG4b, GA1a, GG3a and other page parts change the same append-only lists:
- `server/pageList.ts`;
- `tree-govuk/routes.yaml`;
- `FUNCTIONS.yaml`;
- the route-list pins;
- `test_pages_setting.py`;
- `spec/08`.
**Take every page's entry in each list; drop none.** In `spec/08`, GR1d changes Scenario CS in place. Keep main's other sections exactly as main has them, and add no new section at the end of the file (RULINGS.md, 28 November about 10:45).

## The six questions, as ruled: each (a)

1. **`converted_from_case` and `merged_load` (the rule-3 stop):** (a). The route is right to send them, since the creator chose to share the view. **The page says the two sentences, in words, as proposal 8 (a) said, and never draws either id.** Lift the row's stop:
   - CS19's converted and merged part is built and tested, red first at the real call site;
   - a plant that draws an id on the page is red.
2. **The case model's entity types:** (a). The form offers the date window alone, and says so.
3. **A reader without the right to investigate:** (a). They see GR1a's 404 page, and the views are not asked for.
4. **A view's link before GG2b:** (a). Keep the link.
5. **UTC days:** (a). Keep it.
6. **One failure fails the page:** (a). Keep it.

Also fix the one failure the report found before GR1d: `test_doc_citations_check.py`'s whole-repository case, which fails because GR1a's report cites the build script by a short path (lines 44 and 151). Write the path out in full.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/case-views.test.ts` (from the away branch; red on main, where it does not exist).

## Checks

GR1e's checks, as frozen for GR1:
- the pages' tests, lint, typecheck and `no_react_check`;
- the cases, help and admin-people scenarios;
- the glass-trees gates;
- `test_route_pins.py` and `test_page_lists_merge.py`;
- `test_pages_setting.py`;
- ruff.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**
