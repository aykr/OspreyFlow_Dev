# GG4a away report: a case's drawing boards and one board's drawn items and links as tables, read-only (25 November 2026, D246/D247 away round)

Branch `away/GG4a`, from `away/GR1a`'s tip `005dcbfca`, built under GR1a's case pages. Nothing was pushed or merged, and `main` is
untouched. Every test ran through `REPO=~/away-gg4a ~/osprey-d246/d246_ns.sh` from `OspreyFlow_Core`. All data is synthetic.

These files were not edited: `OspreyFlow_Core/Makefile`, `OspreyFlow_Build/Makefile`, `.github/workflows/ci.yml`, `spec/06_DECISIONS.md`,
`spec/ADR_RESERVATIONS.md`, `osprey.yaml` and `data/`. No decision record changes, so this round has no diff file.

**State: the table is complete and green (about 23:20 UTC). An independent review found 16 defects, and all are fixed or put as
questions. Seven questions for the owner follow.**
- **Question 1:** the rule-3 stop the owner asked for. The route sends something the reader may not see, a drawn item's source document. That part of the row was stopped.
- **Questions 2 and 3:** each built in the conservative reading. Each needs the owner's confirmation.
- **Questions 4 to 7:** smaller points.

## The rulings this round worked from

The owner's rulings on GG4a's draft (25 November) are given here, since they are not yet in `RULINGS.md`. That file is the conductor's
to write, and this round did not edit it.

**Every proposal (a), except question 2**, where he gave the exception (b): GG4a starts now, before GG3, since a board draws without Sigma.
- read-only tables first;
- the paths sit under GR1a's case pages, in the query form GR1a used;
- every refusal gets the same 404 page as a missing page;
- the withdrawn (`missing`) count is shown only to the creator, and only above zero;
- a new scenario, BD, written first and red first;
- the strict reader and the field census;
- drawn watches are not in GG4a.

**One instruction more:** a route that sends something the reader may not see stops that row, and the row becomes a question (rule 3).
It applied once (question 1).

## Commits, in order

| Commit | What |
| --- | --- |
| `200fe1613` | Scenario BD written first in `spec/08`, before Scenario S (the Studio words gate needs S last). The `drawing-boards` row carries BD1 to BD17; its route stays empty. |
| `70f5ec04f` | **Red first:** the page test, its fixture Conduit and the scenario test with the field census. The page test failed to import; the scenario test had 41 failures. |
| `84ada3ef0` | The page: `server/boards.ts`, `server/views/boardsWords.ts`, `tree-govuk/boards.njk`. Its rows went into `pageList.ts` and `routes.yaml`, and its words are bundled with the shared package (`build.mjs`). The case's page links to its boards. The required-field count (BD11) found the may-be-absent list naming fields by bare name, which took `Board.drawn` and `BoardOpened.drawn` out of the required list. Both lists now name `Model.field`. |
| `2588bd691` | The keyboard and scripts-off walks (BK1 to BK3, BO1, BO2). GR1a's CS12 and CK2 now name the case page's new boards link. The route-list pins name the tree's fourth page. |
| `0bb369d85` | GR1a's away report cited `OspreyFlow_Core/apps/pages/scripts/build.mjs` without its folder, twice. `citation-check` was red on this branch's base; the path is now written in full. |
| `3559dd0ed`, `b476303b6` | Fixes for the independent review's findings (below). |
| this commit | This report. |

## What was built

One page, `/cases/boards`, read-only, GOV.UK tree only, GET only, with no form, control or script.
- **`?case=<id>`: a case's boards.** It reads `GET /v1/investigations/{id}/boards` once and draws a table: Board (a link), Shared ("Shared with the case" / "Only you", React's words), Drawn items (the route's own `drawn`), Made. With no board it says "No boards in this case yet." (React's words).
- **`?case=<id>&board=<id>`: one board.** It reads `GET /v1/investigations/{id}/boards/{board_id}` once and draws:
  - the board's facts;
  - the withdrawn sentence, only when the route sends more than zero;
  - three tables in the Conduit's order:
    - **drawn items:** label with "Drawn, not loaded", type, marking, grading as React writes it, source note;
    - **loaded items:** named by React's rule, with "A dataset this case reads: a live reference, not editable here";
    - **links:** both ends named from the route's own items; a link whose end was not sent means the body could not be read.
- **Every refusal is GR1a's 404 page, byte for byte.** That covers someone else's private board, another case's, none at all, no level, another unit, no case, the right to investigate wanting, and any value that is empty, repeated, a dot segment or holds a slash.
- **Past the cap**, the page answers 409 and says so in React's figure. It names the three options in words, says none has a page here, and draws no part of the board.
- **The case's page (GR1a's)** gains one link, "Drawing boards in this case".

## The table of cases (the draft's twelve, as Scenario BD's seventeen rows)

| Draft # | Case | State | Proof |
| --- | --- | --- | --- |
| 1 | Two boards, one shared, one the reader's own | **green** | BD1. In the route's order, which no sort gives (by name, time or count, either way). The count is the route's `drawn`; the hidden fourth item is not counted. |
| 2 | Three drawn items, two references, links | **green, narrower** | BD3: every drawn item has its type, label, marking, grading and source note, and "Drawn, not loaded". **"Drawn by <name>" is not drawn** (question 2). **A source document is not said** (question 1). |
| 3 | A drawn link between a drawn item and a loaded one | **green** | BD4: listed once, both ends named from the route's `nodes`. An end not sent means the body could not be read. |
| 4 | Private, other case's, missing board; no `investigate` | **green** | BD5: the same 404, one call or none. Also no level, another unit, no case; dot segments and slashes ask nothing. |
| 5 | A withdrawn reference, the creator | **green** | BD6: "1 item you placed has since been withdrawn." and the plural, naming none. Another reader of a shared board is sent 0 by the fixture, as by the route, and told nothing. |
| 6 | An item hidden by its marking | **green** | BD7: absent from every table, from the count and from `missing`. No gap, no "hidden" line. The page's words say what is *shown*. |
| 7 | Past the cap | **green** | BD8: 409, the figure, the three options in words. No table. Nodes and links caps both covered. |
| 8 | No answer, or a 401 | **green** | BD10: a 502 "could not be read" as an alert; a 401 gets the Studio's sign-in-again words. |
| 9 | A missing required field | **green** | BD11. 80 fields of nine models, each removed and each given a wrong shape, one case each. Also wrong values, a body of another case or board, ids named twice, a drawn item with no source, and assertions that disagree with `drawn`. |
| 10 | A board with no items | **green, reworded** | BD13: "No items are shown on this board." The draft's "This board has nothing drawn on it yet" would be false when everything on it is hidden. |
| 11 | Keyboard | **green** | `keyboard/boards.spec.ts` BK1 to BK3: tab orders, and Enter on each link, including back to the real case page and back again. CK2 follows the case's new link. |
| 12 | Scripts off | **green** | `scripts-off/boards.spec.ts` BO1, BO2 and BD15: no script but the data block, every link followed. |
| ruling 9 | Strict reader and field census | **green** | BD12 and `test_govuk_boards_scenario.py`. Every field of `Board`, `BoardOpened`, `Node`, `Edge`, `Provenance`, `DrawnAssertion`, `Grading`, `Handling` and `LimitExceeded` is in one of three lists, held to the scenario's two sentences and to the models' own fields: **drawn** (changes a page that is still drawn), **checked** (a change makes the body unreadable) or **left out** (changes nothing). Six closed lists are held to the models' own values. |

### Planted at the real call site (rule 15)

`~/gg4a-tmp/plants.py`, outside the checkout, makes one change to the real `boardsWords.ts`, `boards.ts`, `boards.njk`, GR1a's `cases.ts` or
`cases.njk`, or the fixture (for the fixture's own duty). It runs the page test and restores the file from git; `git status` was empty
afterwards. **All 32 plants went red on the case they name:**
- **The list:**
  - the opened board's items counted in place of `drawn` (BD1);
  - a name not a link (BD1, BD14);
  - the rows turned round (BD1, BD16).
- **A board:**
  - a drawn item's marking or grading taken out (BD3);
  - a document's identifier shown in place of a missing note (BD3);
  - a link's end looked up outside the route's items (BD4);
  - a bare slice of the first items (BD3, BD16);
  - headings with no rows (BD13).
- **Refusals:**
  - a refusal drawn as its own page (BD5);
  - a dot segment, a slash, or a repeated board passed on (BD5);
  - GR1a's case page passing a slash (CS6);
  - the case's link to its boards removed (CS12).
- **The withdrawn count:**
  - said to every reader (BD6);
  - said at zero (BD6);
  - the fixture counting a hidden item as missing (BD7).
- **The cap:** not read (BD8); an option left unsaid (BD8).
- **The reads:** the board read twice (BD9); a failed read drawn as an empty table (BD10).
- **The reader:**
  - a missing count read as zero;
  - a provenance's state unchecked;
  - another case's board drawn;
  - an element named twice;
  - a drawn item with no source;
  - any parseable string taken as a time;
  - `drawn` not held to the assertions.

  All BD11.
- **The census:** a checked field claimed as drawn; a drawn field claimed as left out (BD12).
- **The page:** a script added (BD15).

With the link taken off a board's name in the real template, BK1, BK2, BO1 and BO2 went red.

**Planting and counting found these, each fixed:**
1. The may-be-absent list named fields by bare name (BD11's count, 73 not 75).
2. A plant of `Edge.basis` hit the first `basis` annotation in `domain.py`, which belongs to another class, so the plant could only pass. It now plants in `Edge`'s own body.
3. One plant named BD12 for a drawn row's marking. The census reads `Handling.classification` on a loaded item, so BD3 alone is the case, and the plant now names it.

The scenario test's own plants (37) and BD17's in-page plants run on in-memory copies.

## The independent review and what changed

A read-only lane reviewer read the branch at `2588bd691`. It found 16 defects. Each was checked against the source first, and each claim
below held.

**Fixed:**
1. **A slash in `board` or `case` read other Conduit routes.** `%2F` is decoded by uvicorn before Starlette routes, so `board=b-quay%2Fmatches` read the board's matches.
   - The page now refuses a slash and asks nothing.
   - **GR1a's `cases.ts` had the same hole** (`case=x%2Fbrief`) and is fixed the same way, with CS6 cases.
   - Both fixtures now route the decoded path, as the real server does.
2. **"How it began" was false.** `Boards.wire` sends `selection` when a reference the reader may see is on the board and `blank` otherwise, never `view`. The page no longer says it, and `start` is left out (question 3).
3. **The cap's `LimitExceeded` was not in the census.** It is now; `would_be` is drawn, as React's figure draws it.
4. **"A document of the case" told every reader that a document existed** (question 1). No source document is said now.
5. **The census counted a refusal as a drawing.** A third list, **checked**, now holds the fields read only to know the body is the one asked for. The test tells the three lists apart.
6. **The words said what is not.**
   - "Drawn on this board" covered items drawn on other boards. The caption is now "Drawn items on this board".
   - "Nothing drawn" was false when items were hidden. Every empty sentence now says what is *shown*.
   - The cap's options now say what each is, and that none opens this board.
7. **BD4's column list was wrong in the scenario.** It is corrected.
8. **Three closed values were held to nothing:** `Edge.basis`, `LimitExceeded.cap_kind` and `DrawnAssertion.provenance_class`. Each is now held to its field's own `Literal`.
9. **The fixture was more permissive than the route.**
   - It now blanks `board_id` for anyone but the author (`_board_as_known`).
   - It sends the audit's `reverted` and `withdrawn_by_load`.
   - It withdraws only drawn items, and refuses to start with a loaded one marked so.
   - It models the links cap.
10. **The strict reader was loose.** It now holds:
    - the case and board asked for;
    - the Conduit's form of a moment;
    - a drawn item's source;
    - non-empty grades and labels;
    - distinct ids.
11. **The keyboard walks stopped at a 500.** A small front in `boardsServer.ts` now sends the case's own routes to GR1a's fixture, so the way back lands on the real case page, and BO2 follows every way back.
12. **BD7's check was never shown red.** It is now a function with two plants.

**Not done here:**
- **Duplication:** `ask`/`refused`/`notFound` repeat `cases.ts`, as GR1a's repeat `adminPeopleWords.ts`. A shared module is a structural part, not an away round's.
- **Nested left-out models are not checked inside.** The strict reader checks only that `audit`, `resolution`, `sources` and `layout` are objects. They are left out, so nothing on the page depends on them.
- **No page of the GOV.UK tree has an axe scan,** as GR1a reported.

## Tests run, all through D246 (about 23:15 UTC, after the last fix)

**Page tests (`apps/pages` vitest):**
- Whole suite: **932 passed, 2 failed.** The two failures are the asset route's traversal probes, the wrapper's dot-named `TMPDIR`, as GR1a found. With a plain `TMPDIR` both files pass, 32 of 32. They touch no file of this part.
- `boards.test.ts` (23) and `cases.test.ts` (22): 45 of 45.

**Playwright, the GOV.UK keyboard and scripts-off folder:** 19 of 19.

**Python, 14 files, 882 tests: all passed.** The files:
- `test_govuk_boards_scenario.py` (45)
- `test_govuk_cases_scenario.py`
- `test_functions_yaml.py`
- `test_tree_parity.py`
- `test_no_react_check.py`
- `test_pages_foundation.py`
- `test_design_gates_reach.py`
- `test_pages_image_carries_no_react.py`
- `test_govuk_help_scenario.py`
- `test_govuk_admin_people_scenario.py`
- `tests/harness/test_pages_setting.py`
- `test_ui_words_check.py`
- `test_copy_says_no_client.py`
- `test_doc_citations_check.py`

**Static checks, all clean:**
- root `tsc --noEmit`
- the pages build's `tsc -p tsconfig.build.json`
- `eslint apps/pages`
- `no_react_check.mjs` (PASS)
- `ruff check .` in Core
- `node apps/pages/scripts/build.mjs --out` to a scratch folder: the built `boardsWords.js` imports no workspace package.

**`ruff` on the new Build test:** Core's settings give line-length findings only. GR1a's Build test gives 89 under the same command, and
CI lints Core alone.

**`make` gates, with `make`'s own exit code, all 0** (rerun after the fixes):
- `design-check` (it runs `colour_drift_check`), `ui-words-check`, `citation-check`, `product-tree-link-check`
- `test-file-coverage-check`, `route-coverage-check`, `schemas-check`, `no-branches-check`
- `authorized-query-check`, `demo-guide-check`, `decision-log-publication-check`, `provenance-annotation-check`
- `domain-model-coverage-check`, `no-langchain-check`, `confinement-check`

**`slice-line-check`:** 825 passed, 1 skipped, before the fixes, which touch no slice-line file. The wrapper's clean-up then refuses to
remove read-only files a test leaves behind, as GR1a saw.

**Not run:**
- `client-name-check`: its local hash file is not on this machine.
- `lanes-check`: D246's Docker socket, as GR4a found.
- `graphify update .`: not installed on this account.

## What is left

- **Merge order:** this branch carries GR1a's whole branch and two changes to GR1a's files. One is the slash fix in `cases.ts` and its fixture; the other is the boards link in `cases.njk`, with the CS12, CK2 and Scenario CS stop lists. **GR1a merges first.** If it merges without these, they come with GG4a.
- **Overlap with GR4a:** the same lines as GR1a's: `build.mjs`'s entry list, `routes.yaml`, `pageList.ts` and the route-list pins. Whichever merges last takes every entry.
- **GR3b:** the fixture is hand-written and models the real routes as read. Its answers should come from the real routes' goldens when GR3b lands.
- **A later part:** move `itemLabel`/`linkLabel` from `apps/workspace/src/boards/boardModel.ts` to `glass-shared`. BD3 holds the page's copy in step line by line until then.
- **The `RULINGS.md` entry** for these rulings is the conductor's to write.

## Questions for the owner (each is a ruling; none was guessed)

1. **A drawn item's source document (the rule-3 stop you asked for).**
   - What happens: `open_board` sends each drawn item's `source_document` identifier to every reader of the board. `_source_document_check` checks only the author's view when drawing, and `_board_as_known` blanks only `board_id`. So a reader who may not read the document is told one is there.
   - **Built:** no document is said, by identifier or by kind. The note is said; where there is none, "No note given".
   - **The leak that remains:** a drawn item must have a note or a document, so "No note given" still implies a document. Nothing the page can draw avoids that inference.
   - Options:
     - (a) Keep it.
     - (b) A Conduit part withholds `source_document` (and so the inference) from a reader who may not read the document, as `_board_as_known` does for `board_id`; the page then says "A document of the case" where one is sent.
     - (c) Drop the source column until (b).
2. **Who made a board and who drew an item.**
   - What happens: `created_by` and `asserted_by` are accounts' identifiers. React shows the identifier ("Read only: drawn by {created_by}", "Drawn by"). No route this page may read turns them into names.
   - **Built:** left out, as GR1a did for `created_by` (GR1a's question 2; one ruling covers both).
   - Options:
     - (a) Keep it.
     - (b) Show the identifier, as React does.
     - (c) A later part adds names to the route.
3. **How a board began.**
   - What happens: `Board.start` says only whether a reference the reader may see is on the board. It is never `view`. React does not show it either.
   - **Built:** not said, left out.
   - Options:
     - (a) Keep it.
     - (b) A Conduit part stores and sends how a board began, and the page says it.
4. **The opened board's `ceiling`.** It is the strictest marking of the case's datasets, sent to every reader, and may name a marking above the reader's clearance. **The page does not draw it, so no row was stopped**, but it is a route-side rule-3 question. Options:
   - (a) A Conduit part sends it only to a reader cleared for it.
   - (b) Leave it: a marking's name is not the data.
5. **The list's heading does not name the case:** "Drawing boards in this case". The boards route does not send the name, and the page reads one route. Options:
   - (a) Keep it.
   - (b) Read the case too: two reads and two audit rows.
6. **The cap's page answers 409, as the route does.** Its options are sentences, since no GOV.UK page for them exists, and it says none of them opens this board. Options:
   - (a) Keep it.
   - (b) Answer 200.
   - (c) Your words for the options.
7. **The address:** `/cases/boards?case=…&board=…`, under GR1a's ruled-pending query form (GR1a's question 1). If you amend ADR-152 decision 6 to allow path patterns, this page follows.

## Notes for the verifier

- **The fixture** (`test/govuk/boardsConduit.ts`) answers in the real order:
  - the router, on the decoded path (404/405; every other route of a case or a board is 500, not modelled);
  - then the bearer (401);
  - then the route-level rights (403 `right_required`: `investigate` to read; `draw_on_boards` first for a write);
  - then the case's gate (404 `investigation_not_found`);
  - then the board (404 `board_not_found` for someone else's private board, another case's, or none);
  - then the cap (409 `limit_exceeded`, on nodes or links).
- **What the fixture sends:**
  - It filters items and links by the reader's clearance, as the adapter does.
  - It wires `drawn` and `start` as `Boards.wire` does.
  - It counts `missing` for the creator alone, from withdrawn drawn references only.
  - It blanks `board_id` for anyone but the author.
  - A successful write is deliberately not modelled (500).
- **`boardsServer.ts`** puts one small front before the boards fixture and GR1a's cases fixture, so the keyboard walks reach the real case page.
- **The scratch scripts** (`plants.py`, the `edit*.py` patches, `gates.sh`) and the build output are in `~/gg4a-tmp/`, outside the checkout.
