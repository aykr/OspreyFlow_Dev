# Slice GG4c · GG4 · Making, sharing and deleting a drawing board on the GOV.UK pages, as scripts-off forms (the owner, 26 November 2026)

- **Build id:** GG4 (the `drawing-boards` row of `apps/pages/FUNCTIONS.yaml`, about line 260)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GG4a
- **The owner's rulings:** the draft `slices/drafts_2026-11-26/GG4c.md`, every proposal (a) (26 November, about 10:35
  UTC, `RULINGS.md`); **question 5 (a): no unshare route; unshare goes to the backlog.** Read the draft whole.

## The rulings, as built

1. **Q1 (a):** make a blank board, share it, delete it. From a view, from a selection and the no-case drawing wait.
2. **Q2 (a):** "New drawing board" is offered when `GET /v1/me/rights` holds both `draw_on_boards` and `investigate`;
   share and delete only when the opened board says `may_draw`.
3. **Q3 (a):** the page's own words for each refusal; a non-creator's share or delete posted by hand is the same 404 page
   as a missing board; a 422 for the name is the GOV.UK error summary with the words kept.
4. **Q4 (a):** a confirmation page before the delete, with the anti-forgery token; then the delete and a `303` to the
   case's boards with the banner.
5. **Q5 (a):** a button "Share with the case", with the sentence that it cannot be undone. **No unshare route is asked
   for:** write the backlog row's words for an unshare route (a Conduit amendment, decision 11) in your report; the
   conductor adds the row.
6. **Q6 (a): post, then `303` to a `GET`,** the first GOV.UK page to write this way (the Studio's Releases renders on the
   post). GR1b and the later write parts follow it; if GR1b merges first with the same pattern, keep its shape.
7. **Q7 (a):** scenario BD extended (BD18 onward), written first and red first.
8. **What GG4a dropped stays dropped:** GG4a's round 1 removes the source column (the drawn item's source note) until
   GG4b. Add nothing that shows a source note or a document id. **"Who made it" is left out for 0.7.0** (names later
   through `display_names`, a backlog part): no form or banner names the board's maker.
9. **The fixture refuses as the route does, in its order** (case 14), including `BoardInput`'s `extra="forbid"`
   (`packages/schemas/boards.py` about line 104): `_csrf` must never reach the Conduit.

**Re-read every citation:** the draft read `042c882` and `away/GG4a`; on today's main `make_board` is about
`app.py:5021`, `share_board` about :5098 and `delete_board` about :5117.

## The table of cases

The draft's table, cases 1 to 14, each red first at the real call site (rule 15). GG4a's BD1 to BD17 stay green.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/boards-write.test.ts` (new; red on main, green after) and
`OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (GG4a's, extended).

## Checks (pure; store ports pinned to 9)

`npm test --workspace apps/pages` (with `test/server/csrf.test.ts` over the new page route); `npm run lint`; `npm run
typecheck`; `node scripts/no_react_check.mjs`; the GOV.UK scenario tests (boards, cases, help, admin people),
`test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`;
`ruff check .`. (`test_doc_citations_check.py` is left out while main is red on it; the merge's full gate runs
`citation-check`.)

## Out of scope

Boards from a view or a selection; the no-case drawing; drawing on a board (GG4d); an unshare route (the backlog); the
source column (after GG4b); any Conduit change; `apps/workspace`; the Default tree's twin.
