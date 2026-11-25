# Slice GG4a · GG4 · A case's drawing boards as GOV.UK pages, read-only: the list of boards and one board's drawn items and links as tables (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper.

**Where GG4 comes from.** `OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:258-264` gives the row `drawing-boards`, "Drawing
boards (and a watch or alert drawn from them)", in `apps/workspace/src/boards/`, with slice `GG4`, no scenario, no route
and status planned. ADR-152 decision 6 puts the "drawing board" among the interactive modules kept once in
`apps/pages/modules` (`OspreyFlow_Build/spec/06_DECISIONS.md` about lines 41037 to 41038 and 41060). The critical path
"PL7 → GG2 → GG3 → GG4" is in `slices/NEXT_BATCH_2026-11-24.md:1`. **Question 0, rechecked against the plan's row (the owner, 25 November 2026, later the same day):** "**GG4: Graph
extras, drawing boards, Matrix, Ownership, query builder, metrics (R6)**", which **needs GG3**. **Changed:** GG4 is
wider than the boards. It also holds the `graph-extras` row (`FUNCTIONS.yaml:251-257`: Explore, find connections),
`matrix-ownership` (:266-272) and `query-builder` (:274-280: the query builder, metrics, match strictness,
cross-filter). **The boards stay the proposed first slice**: they are the only GG4 row that draws nothing with Sigma
and reads a route that already answers without an oracle, and the Matrix's two grids are GG2d's by the scouts' cut
(`STAGE4_SCOUTS_2026-11-20.md:86-88`, where the plain case list and Matrix tables are GG2d). **Question 2's proposal now
follows the plan's "needs GG3"**, and starting earlier becomes the owner's exception. **Open:** whether the Matrix is
GG2d's (the scouts' cut) or GG4's (the plan's row), since both name it.

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **The decision.** ADR-143 (`spec/06` about line 26527, "ACCEPTED (design)"; its status line, about 26531, still says
  "Not built", but the code below is on main). Relevant here:
  - C6, an explicit drawing board, opened blank, from a case view or from a selection (about 26564);
  - C7, move by dragging, link by the handle, Alt-drag or right-click, with *Draw a link* as the keyboard route (about
    26567);
  - C15, drawn items shown on the analysis canvas dashed and read-only (about 26594);
  - decision 3: nothing in an analyst layer is visible outside its case, including by degree, path length or a count;
  - decision 4: every drawn item carries `asserted_by`, `asserted_on`, a marking, a grading and a source note, with the
    provenance class `analyst_drawn`, "drawn dashed in amber everywhere it appears";
  - decision 5: a board is a case view with drawing switched on and keeps its own layout; only its author edits or
    withdraws its items (never deleted); every board action has its keyboard case.

  `spec/02_GLASS_FRONTEND.md` §2.0b "Boards" (about lines 617 to 644) covers the surface, the item and link forms and
  the inspector.
- **The Conduit (no change needed for reading).** `services/api/app.py`: `_READS_BOARDS = [require_right(INVESTIGATE)]`
  and `_DRAWS` = `DRAW_ON_BOARDS` plus `INVESTIGATE` (:4908-4912).
  - `GET /v1/investigations/{id}/boards` (`list_boards`, :4955) and `GET /v1/investigations/{id}/boards/{board_id}`
    (`open_board`, :4984) are both behind `_READS_BOARDS`.
  - Writes: create (:4965), share (:5045), delete (:5061), items (:5079), links (:5104), layout (:5128), item change
    (:5144), withdraw (:5171), matches (:5191, :5206), pictures (:5228 to :5321), drawn watches (:5337) and promotions
    (:5460 to :5504). The no-case `POST /v1/drawings` is near :11163.
- **Refusals, already free of oracles.** `BoardNotFound` answers **404 `board_not_found`** for "someone else's private
  board, another case's, and none at all alike" (`app.py:3161-3164`; raised by `Boards.board`,
  `services/api/boards.py:339-346`, also for a case view that is not a board). `ItemNotFound` answers 404 alike
  (:3167-3170). `NotTheBoardsCreator` answers drawing by anyone but the creator (:3173; `own_board`,
  `boards.py:348-354`).
- **What opening a board answers.** `BoardOpened` (`packages/schemas/boards.py:155`) carries the board, its `nodes` and
  `edges` as the reader may see them, `drawn` (which are drawn, as opposed to live references), `items`, `layout`,
  `missing`, the model's types, the markings up to the ceiling, the grading scheme, and `may_draw` / `may_promote`.
  `Board` (:132) is "a board as listed: never naming its items", with `shared`, `drawn` (a count of the drawn items the
  reader may see, withdrawn ones not counted) and `start`. **`missing` counts only what was lost, never what the reader
  was never allowed to see**: references whose drawn item has since been withdrawn, told to the board's creator alone
  (`boards.py:412-422`). Past the working-set cap the open raises the typed `LimitExceededError` (:423-426; CLAUDE.md
  rule 2). The deployment's ceiling is enforced on drawing (`boards.py:164-166`, :214-226; SE1).
- **The React screens.** `apps/workspace/src/boards/`: `BoardEditor.tsx` (1,397 lines; drag at :151-185, the link
  handle at :451), `BoardsPlace.tsx` (282), `PromoteSheet.tsx` (217), `boardModel.ts` (93), `BoardAlerts.tsx` (26),
  `drawnWatchWords.ts` (8) and four test files. **The board is drawn with the DOM and SVG, not Sigma**: no file in
  `src/boards/` imports `sigma` (its imports are React, `glass-shared` and its own files, `BoardEditor.tsx:11-49`), and
  it is not among the fifteen files that import Sigma (WS4a's scout). The keyboard walk is
  `apps/workspace/keyboard/boards.spec.ts` (about 37 cases, :39 to :445); `keyboard.spec.ts` has no board step. A11y
  findings are open on the link handle and a photo label (`a11y/contrastFindings.json:3-5`, :10-20; a backlog row
  placed under GG4, ruling D19 "Later").
- **"A watch or alert drawn from them."** A watch is set when an item is drawn (`boards.py:546-547` for a node,
  :622-623 for a link, `board_store.py:109-118`). The alert is raised by `services/api/drawn_watches.py:79` and
  :97-104 (ADR-143 C16: a new load that matches a drawn item alerts the case). The screen reads them with
  `GET .../drawn-watches` (:5337) and `BoardAlerts.tsx`.
- **The shared client.** `packages/glass-shared/src/boards/boardsApi.ts`: `listBoards` (:94-95), `makeBoard` (:97-113)
  and `openBoard` (:116). `boardPromotions` is imported from `glass-shared` by `BoardEditor.tsx:49`.
- **The page service.** `apps/pages/server/pageList.ts:13-20` lists studioFrame, studioReleases, studioDatasetMap,
  studioModel, help and adminPeople. `tree-govuk/routes.yaml:8-10` lists `/help` and `/admin/people` (GR3a and RM1a
  add theirs on their branches). `apps/pages/modules/` holds only `studio-frame.ts`. The forwarder already names a
  board picture upload path (`apps/pages/server/forward.ts:109`). **There is no GOV.UK case page yet** (no `/cases`
  route), so a board page has no case page to sit under (GR1, question 3).
- **No scenario** in `spec/08` mentions a board.

## Questions for the owner (the proposal first)

1. **The first slice's scope.** (a) **Read-only, as tables:**
   - a case's boards: name, who made it, whether it is shared, how it began, and the count of drawn items the route
     sends;
   - one board: its drawn items (type, label, marking, grading, source note, who drew it, "drawn, not loaded"), its
     live references (named as loaded items), and the links among them (from, type, to, drawn or loaded).

   This is the scripts-off core that the 20 November rule asks every page to have ("a table in place of the graph"), so
   it is never a parity exception. (b) Read-only with the board drawn as plain positioned SVG from `layout` (classes
   only, no inline style), plus the tables. (c) Drawing as well, which is too big for one slice.
2. **Whether GG4 waits (changed after the plan's row was given).** (a) **It waits for GG3, as the plan's row says**,
   which itself waits for GG2 and PL8. The boards then open from the case workspace's panels like every other GG4
   function. (b) An exception to the plan's needs, for the owner alone to give: GG4a needs no Sigma and no panel frames,
   so it could start once a GOV.UK case page exists (GR1a), and decision 9's "no other page that draws with Sigma 4
   merges until WS4 is in" does not reach a board, which does not draw with Sigma. The first draft proposed this.
3. **The path.** (a) **`/cases/{case_id}/boards` and `/cases/{case_id}/boards/{board_id}`** in the GOV.UK tree, under
   the case path GR1 chooses. No code, route or word reuses "trends shown together" (GR4a's own rule, the other way
   round). (b) `/boards/{board_id}` with the case taken from the board.
4. **Who may open it.** (a) **Whoever the route lets read it** (`INVESTIGATE` in the case; a private board only its
   creator). Every refusal, for a board that is someone else's private one, another case's, missing, or a reader
   without the right, is the same GOV.UK 404 page, words and status, as a page that does not exist (GR4a's ruling 3 and
   AD3a's rule). The page filters nothing (decision 5). (b) Shared boards only, which the route does not offer and
   would need a page-side filter. Not proposed (rule 3).
5. **The `missing` count.** (a) **Shown only when the route sends more than zero**, in words to the creator ("2 items
   you placed have since been withdrawn"). The page never computes one. (b) Never shown.
6. **Past the cap.** (a) **The typed refusal is shown with its three options in words** (save a smaller view, apply a
   filter, promote to a batch job: `00_ARCHITECTURE.md` rule 2), each a link where a page for it exists and a sentence
   where none does yet. Never a part of the board. (b) A sentence only.
7. **Drawn watches.** (a) **Not in GG4a.** The board's alerts (`drawn-watches`) are listed by a later GG4 slice beside
   the drawing; RM1's alert queue already shows the alerts themselves. (b) A list of the board's drawn watches in
   GG4a.
8. **The scenario.** (a) **A new `spec/08` scenario, BD, written first and red first, from these rulings** (the owner's
   rule for every page). (b) Your words.
9. **The fixture.** (a) **The strict reader and the field census, as ruled for GR3a**: a body missing a field
   `BoardOpened` or `Board` requires is "could not be read", never an empty board; every field of the generated types
   is drawn or named in the scenario as left out (the left-out list would be the model's types, markings and grading
   scheme, which only drawing needs, and `may_draw` and `may_promote`). **The answers come from the real routes when
   GR3b lands** (rule 15).

## The table of cases (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A case with two boards, one shared and one the reader's own | both listed as the route sends them, each a link to its board; the count of drawn items is the route's `drawn` | the page counting the opened board's nodes in place of `drawn` |
| 2 | A board with three drawn items, two live references and links among them | a table of drawn items and one of links, every drawn item said as "drawn by <name>", each reference as a loaded item | a drawn item shown without its marking or grading (the census turns red) |
| 3 | A drawn link between a drawn item and a loaded one | listed once, with both ends named as the route names them | an end looked up outside the route's `nodes` |
| 4 | Someone else's private board, another case's board, a board that does not exist, a reader without `INVESTIGATE` | the same 404 page, words and status, for all four | a "not shared with you" sentence for the first |
| 5 | A board with one withdrawn reference, opened by its creator | "1 item you placed has since been withdrawn"; no name | the sentence drawn for another reader too (the page must draw only what is sent: the fixture sends 0 to others, as the route does) |
| 6 | An item the reader may not see because of its marking | absent from every table and every count; no gap, no "1 hidden" | the fixture sending a hidden item's count as `missing` (the real route never does: the fixture models that) |
| 7 | A board past the cap | the typed refusal's three options in words; no partial table | a bare slice of the first N items (rule 2) |
| 8 | The Conduit gives no answer, or 401 | the 502 "could not be read" page; an ended session says to sign in again (AD3a's AP4) | a blank table |
| 9 | A body missing a field the generated types require | "could not be read", never an empty board | each required field removed in turn (one case per field, from the type's own field list) |
| 10 | A board with no items | "This board has nothing drawn on it yet", and a link back to the case's boards | an empty table with headings only |
| 11 | Keyboard | every link reachable and working in the GOV.UK keyboard folder; one case per page (rule 13) | a link left out of the tab order |
| 12 | Scripts off | both pages whole, with no control that needs a script | none: they hold no script; the spec proves it |

## Checks (frozen when cut)

GR3a's list, adapted: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; the new scenario's test
and the pages' tests; `tests/glass_trees/test_functions_yaml.py` (the row's scenario id), `test_tree_parity.py`,
`test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`; `test_ui_words_check.py`,
`test_copy_says_no_client.py`, `test_doc_citations_check.py`; **`tests/harness/test_pages_setting.py`** (the route
list, about line 2352: the new paths added with their words); `ruff check .`; `make -C OspreyFlow_Build design-check`;
`colour_drift_check`; the cheap checks of 20 November.

## Out of scope

Drawing, moving, linking, withdrawing, pictures, matching and promotion (later GG4 slices, with the board module and
its keyboard routes); drawn watches (question 7); the analysis canvas's dashed display of drawn items (C15: GG2's);
any Conduit change; `apps/workspace`; the Default tree's twin; the a11y findings on the React board's handle (a backlog
row, placed "Later").
