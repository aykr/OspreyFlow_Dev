# Slice GR1b · GR1 · New case as a GOV.UK form, scripts off: the case's name, the data it reads (a new empty dataset or an existing one) and its domain models, posted once (the owner, 26 November 2026)

- **Build id:** GR1 (the `cases-and-views` row of `apps/pages/FUNCTIONS.yaml`, about line 205; "New case is GR1b", the
  owner on GR1a's draft, 25 November)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GR1a
- **The owner's rulings:** the draft `slices/drafts_2026-11-26/GR1b.md`, every proposal (a) (26 November, about 10:35
  UTC, `RULINGS.md`: "every non-owner question in the 26 November drafts"). Read the draft whole.

## The rulings, as built

1. **Q1 (a):** the form at `/cases?new=1`, handled by the list page's own `POST`, "New case" a button on the list (the
   registry allows one page per `FUNCTIONS.yaml` row: `server/pages.ts` about lines 133 to 136). If GR1a merges with
   another address form, follow GR1a's and say so.
2. **Q2 (a):** offered when `GET /v1/me/rights` holds `create_case`; a hand post without it is said as "You cannot make
   cases".
3. **Q3 (a), Q4 (a), Q5 (a):** both data choices on one form as GOV.UK radios with conditional content; the server sends
   exactly one of `new_dataset_name` and `dataset_ids`; an empty new-dataset name takes the case's (both empty: `Untitled
   case`); three domain boxes as `domainLabels` labels them, sent as ticked, empty included, with "Bespoke POLE (the
   core model)" beside them when none is ticked. Read whether any route says which datasets have a live model; if none
   does, leave that sentence out and always send the boxes, and say so.
4. **Q6 (a):** the one `422 dataset_refused` (no detail) is said by the branch the page sent, the person's words kept,
   nothing made; the page never claims to know which rule refused it.
5. **Q7 (a), Q8 (a):** a `303` to the new case's page with the banner (and a link to the Studio when a new dataset was
   made); scenario CS extended (CS16 onward) written first; the fixture refusing as the route does, in its order.
6. **The write pattern is GG4c's (post, then `303` to a `GET`), with `_csrf` (I17).** If GG4c merges first, follow its
   pattern as merged; if this part merges first, it sets it: say which in your report.
7. **"Who made it" is left out for 0.7.0** (names later through `display_names`, a backlog part): the new case's page
   names no maker.

**Re-read every citation:** the draft read `042c882`; on today's main `create_investigation` is about `app.py:4234` and
`list_datasets_route` about :4278.

## The table of cases

The draft's table, cases 1 to 16, each red first at the real call site (rule 15). GR1a's CS1 to CS15 stay green.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/cases-new.test.ts` (new; red on main, green after) and
`OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py` (GR1a's, extended).

## Checks (pure; store ports pinned to 9)

`npm test --workspace apps/pages` (with `test/server/csrf.test.ts` over the new `POST`); `npm run lint`; `npm run
typecheck`; `node scripts/no_react_check.mjs`; the GOV.UK scenario tests (cases, help, admin people),
`test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`;
`ruff check .`. (`test_doc_citations_check.py` is left out while main is red on it; the merge's full gate runs
`citation-check`.)

## Out of scope

A case's datasets changed later (GR1f); a composite dataset; the no-case drawing; any Conduit change (a reason on
`dataset_refused` would be an amendment); `apps/workspace`; the Default tree's twin.
