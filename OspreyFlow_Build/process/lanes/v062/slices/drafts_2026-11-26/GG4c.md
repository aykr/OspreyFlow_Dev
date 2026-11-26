# Slice GG4c · GG4 · Making, sharing and deleting a drawing board on the GOV.UK pages, as scripts-off forms (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** GG4a (built on `away/GG4a`, `c92a1f4ed`, not merged) shows a case's boards and one board as
tables at `/cases/boards?case=…&board=…`, read-only. ADR-143 decision 5 (`spec/06_DECISIONS.md` about line 26527 onward):
"a board is a case view with drawing switched on"; only its author edits or withdraws its items; every board action has
its keyboard case. `spec/02_GLASS_FRONTEND.md` §2.0b *Boards* (about lines 659 to 733). This is the first GOV.UK page
that **writes**, so it also fixes the pattern the later write slices (GG4d, GR1b, GA1b) follow.

## What exists today (read on `origin/main` at `042c882f2` and on `away/GG4a`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`), all behind `_DRAWS` = `draw_on_boards` and `investigate`
  (:4963) and the case's **Editor** gate (`InvestigationEditorDep`):
  - `POST /v1/investigations/{id}/boards` (`make_board`, :5016-5033), 201, body `BoardInput`
    (`packages/schemas/boards.py:99-118`: `name` 1 to 200 characters; `start` `blank` | `view` | `selection`; `view_id`;
    `node_ids` up to 10,000; "a blank board starts from nothing"). Audited `make_board` with `start`.
  - `POST .../boards/{board_id}/share` (`share_board`, :5097-5109): no body; `own_board` first, so only the creator
    (`boards.py:348-354`, 403 `NotTheBoardsCreator`, handler `app.py:3206-3211`). Audited.
  - `DELETE .../boards/{board_id}` (`delete_board`, :5112-5127), 204, creator only: "**Deleting a board never deletes
    what was drawn on it: that stays in the case's layer.**" Audited.
  - Refusals: `BoardNotFound` 404 `board_not_found` for someone else's private board, another case's or none
    (:3194-3197). There is **no unshare route**.
- **What the reader's page knows.** `open_board` answers `may_draw` = creator and `draw_on_boards`
  (`app.py:5050-5052`, `_may_draw` :5078). **The list route (`list_boards`) says nothing about whether the reader may make
  a board**; `GET /v1/me/rights` is read by the Studio frame for the same purpose (`apps/pages/server/studio.ts:201-213`).
- **How a scripts-off page writes today.** The Studio's Releases page is a page route with `methods: ["GET", "POST"]`
  (`studio.ts:732-738`); its server half calls the Conduit with the person's token and **renders its answer on the
  `POST`** (`releasesPost`, `studio.ts:522-727`, e.g. :727); the one `303` in the Studio is the frame's dataset switch
  (`studio.ts:241`). **So no page writes by post-then-redirect yet**: question 6 (a) would be the first. The anti-forgery token is a hidden `_csrf` field (`csrf.ts:61-103`; `res.locals.csrfToken`,
  `app.ts:407-409`). **The only POST form in the GOV.UK tree is sign-out** (`tree-govuk/layout.njk:21-22`). An HTML form
  sends only `GET` and `POST`, so the delete is the page's own `POST`, which the server half turns into the Conduit's
  `DELETE`.
- **The React screens.** `BoardsPlace.tsx` (291 lines) makes boards (blank, from a view, from a selection) and starts a
  no-case drawing (`POST /v1/drawings`, which also needs `CREATE_CASE`, `app.py:11300-11303`). The keyboard ids are
  `BOARD_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:517-544`, 25 ids).

## Acceptance (red before, green after)

Scenario **BD**'s new rows (BD18 onward, written first in `spec/08` from these rulings) and
`apps/pages/test/govuk/boards-write.test.ts`, red on `away/GG4a`'s page (no form exists), green after, with GG4a's own
BD1 to BD17 unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Make a blank board, share it, delete it.** "From a view" and "from a selection" wait: a view needs
   the saved views list (GR1d) and a selection needs the canvas (GG2e). The no-case drawing (`/v1/drawings`) is a later
   slice. (b) Blank and from a view, reading `GET .../views` for the choice.
2. **When the forms are offered.** (a) **"New drawing board" is offered when `GET /v1/me/rights` holds both
   `draw_on_boards` and `investigate`** (one more read on the list page, so the page reads two routes); share and delete
   are offered only when the opened board says `may_draw`. The route refuses all the same, and a refusal is said in
   words. (b) Always offered, the refusal said after the post.
3. **What a refusal says.** (a) **The page's own words for each**: a 403 for the right or the level is "You cannot make
   boards in this case"; a 403 `NotTheBoardsCreator` cannot be reached from the page (the controls are the creator's)
   and is said as the same 404 page as a missing board, since a non-creator was never offered it; a 422 for the name is
   the GOV.UK error summary with the words kept. (b) The Conduit's own detail.
4. **Delete.** (a) **A confirmation page first** ("Delete this board? What was drawn on it stays in the case."), with
   the anti-forgery token, then the delete and a `303` to the case's boards with a GOV.UK notification banner. No
   script, no dialogue. (b) Delete at once with the banner.
5. **Share.** (a) **A button "Share with the case", with the sentence that it cannot be undone** (no unshare route
   exists), and the board's state after it as GG4a already shows it. (b) Ask for an unshare route (a Conduit change,
   decision 11: not proposed).
6. **After a write.** (a) **Post, then `303` to a `GET`, a new pattern (Releases renders on the post)** (the board's page after make and share; the case's boards after
   delete), so a reload sends nothing again. (b) Render on the POST, as Releases does.
7. **The scenario.** (a) **Scenario BD extended (BD18 onward), written first and red first.** (b) A new scenario.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A reader with `draw_on_boards`, `investigate` and the Editor level makes "Supply routes" | exactly one `POST .../boards` with `{"name": "Supply routes", "start": "blank"}`; `303` to its board page; the board listed | the form's fields passed through whole, `_csrf` included: the real route refuses an extra field (`BoardInput` is `extra="forbid"`, `boards.py:104`), and so does the fixture |
| 2 | A name of 201 characters, or empty | the error summary in GOV.UK form, the words kept, nothing sent | the page sending it and showing the 422's detail |
| 3 | A reader without `draw_on_boards` | no "New drawing board" form; a post made by hand is refused and said as "You cannot make boards in this case" | the form drawn from the case level alone |
| 4 | A Viewer-level reader with the right (the route answers 403 for the level) | the same words as case 3 | the 403's detail passed through |
| 5 | The creator shares their board | one `POST .../share`; `303`; the board shown as shared | a second post on reload (no `303`) |
| 6 | Share and delete are offered only when `may_draw` | absent for a reader of a shared board that is not theirs | the controls drawn for every reader |
| 7 | A share or delete posted by hand by a non-creator | the same 404 page as a missing board | the 403 `not_the_boards_creator` said in words |
| 8 | Delete: the confirmation page, then the delete | one `DELETE .../boards/{id}` only after the confirmation's post; `303` to the boards with the banner "The board was deleted. What was drawn on it stays in the case." | the `DELETE` sent on the first click |
| 9 | A post without `_csrf`, or with another session's | refused by `csrf.ts`, nothing sent to the Conduit (I17) | the page route registered outside the check |
| 10 | The Conduit gives no answer, or 401, on a write | the 502 "could not be read" page says nothing was changed; a 401 says to sign in again | a success banner on a 502 |
| 11 | Each write is audited once | one Conduit call per write (one audit row) | a read-back call made with the write's verb |
| 12 | Keyboard | each form and button reachable and working in `test/govuk/keyboard/` (rule 13), one case per action | a button out of the tab order |
| 13 | Scripts off | every write completes by form (I4) | none: the page holds no script |
| 14 | The fixture | refuses as the route does, in its order: the rights (403), the case's gate (404, or 403 for a level too low), the body (422), then `own_board`: the board (404 `board_not_found`) before the creator (403) (`boards.py:351-353`), as GG4a's fixture already orders them | a fixture that accepts a body the route refuses (rule 15's second worked example) |

## Files touched

`OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md` (BD18 onward); `OspreyFlow_Core/apps/pages/server/boards.ts` (the
`POST` half, as `studio.ts` does), `server/views/boardsWords.ts`; `tree-govuk/boards.njk` and a confirmation template;
`test/govuk/boards-write.test.ts`, `boardsConduit.ts` (the write routes' refusals), `keyboard/boards.spec.ts`,
`scripts-off/boards.spec.ts`; `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py`;
`tests/harness/test_pages_setting.py` (only if a path is added: none proposed).

## Checks (frozen when cut)

GG4a's list: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; the scenario's test;
`test_functions_yaml.py`, `test_tree_parity.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`,
`test_ui_words_check.py`, `test_copy_says_no_client.py`, `test_doc_citations_check.py`, `test_pages_setting.py`;
`apps/pages/test/server/csrf.test.ts` (I17) with the new page route; `make -C OspreyFlow_Build design-check`; the cheap
checks of 20 November.

## Out of scope

Boards from a view or a selection (question 1); the no-case drawing; drawing on a board (GG4d); any Conduit change;
`apps/workspace`; the Default tree's twin.
