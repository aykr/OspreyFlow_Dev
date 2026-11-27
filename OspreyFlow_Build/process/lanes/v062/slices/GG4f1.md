# Slice GG4f1 · GG4 · A board's drawn watches and *Looks like a loaded item*: the watches said, and each match decided by form (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GG4a`. No row in `slices.tsv`; no builder
starts from this paper. **Size M.** The first of GG4f's three parts (the plan's split: GG4f1 drawn watches and matches,
GG4f2 pictures, GG4f3 promotion).

**Where it comes from.** ADR-143 decision 6 (`spec/06_DECISIONS.md` :26640-26643): "the board's *Looks like a loaded
item* panel offers the pair; *Same* writes a confirmed `SAME_AS` (score 1.0, as a manual link …) in the analyst layer;
*Not the same* writes `NOT_SAME_AS`. Neither changes the loaded item. **The suggestion itself is `inferred` and never acts
on its own.**" ADR-143 Amendment 2 decision 8 (:27752-27756): drawing an item sets a watch for it, owned by the item's
author; "it is withheld whole from a reader who may not see the drawn item (rule 3)". Decision 13 (:26682-26686): every
board screen under GOV.UK uses GOV.UK forms and tags. Rules 2, 3, 5 and 6.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The match routes** (`OspreyFlow_Core/services/api/app.py`):
  - `GET .../boards/{board_id}/matches` (`board_match_suggestions`, :5242-5254), behind `_READS_BOARDS` and the case's
    **Viewer** gate, `boards.board(...)` (so any reader of the board, shared or own): answers `MatchSuggestions`.
  - `POST .../boards/{board_id}/matches` (`decide_board_match`, :5257-5276), 201, behind `_DRAWS`, the case's **Editor**
    gate and `own_board` (the board's creator only; 403 `not_the_boards_creator` otherwise); body `MatchDecision`
    (`drawn`, `loaded`, `same`, `extra="forbid"`, `packages/schemas/boards.py:231-239`); audited `decide_board_match`;
    answers `MatchDecided` (`edge_id`).
- **How suggestions are found** (`services/api/boards.py:853-920`): for each live drawn node on the board, loaded nodes of
  its type the reader may see, by an identifier equal (score 1.0, "the same {key}") or a name alike (at least
  `MATCH_AT = 0.75`, "a name alike", :93), read through the reader alone, "so one the reader may not see is never a
  candidate, never counted, never ordered" (:866-869). A pair already decided is left out (:906-916). **At most
  `MATCH_LIMIT = 20` (:95); past it the list is cut and `more` is `True` (:918-919)**, which the schema says is "said, never
  cut silently" (`packages/schemas/boards.py:225-228`). Each `MatchSuggestion` (:214-222) carries `drawn` (an id),
  **`loaded` (a whole `Node`)**, `score`, `why` and `state: "inferred"`.
- **What a decision writes** (`boards.py:922-961`, `match_writes` :1216-1253): one `SAME_AS` (score 1.0, asserted, source
  `manual:<drawn>:<loaded>`) or `NOT_SAME_AS` into the layer, marked as the stricter of the two ends and checked against
  the ceiling and the decider's clearance (`check_marking`, :943-944); no node is written (rule 6); the decision is kept
  as the board's own item of kind `match`, so withdrawing the drawn node takes it too (:951-960). Refusals: `ItemNotFound`
  (404 `item_not_found`) for a drawn item not on this board, withdrawn, or a loaded end the decider cannot see or that is
  itself drawn (:926-940); `DrawingRefused` from `check_marking` (409 `above_the_ceiling`, `above_your_clearance`).
  **There is no route that undoes a decision** other than withdrawing the drawn item.
- **The watches.** `GET /v1/investigations/{id}/drawn-watches` (`list_drawn_watches`, :5389-5395), Viewer gate: the
  case's live drawn watches the reader may see, "a watch on an item they may not see is withheld whole"
  (`boards.py:1199-1213`). `DrawnWatch` (`packages/schemas/boards.py:264-276`): `id`, `item_id`, `element_id`,
  `case_id`, `dataset_id`, **`owner`** (a principal id), `created_at`, `ended_at`, `kind`. The watch's alerts go to its
  owner alone, in that case (`services/api/alerts.py:365`; `services/api/drawn_watches.py:1-35`). **A drawn item's
  author is not always the board's creator**: the item routes never call `own_board` (they check `_own_item`, GG4d's
  draft), and a node drawn on one board may be placed on another as a reference (`boards.py:965-980` accepts it there,
  then refuses another's item with 403 `not_your_item`). So "your watch" is known only by the watch's `owner` against the
  reader's own id, which `GET /v1/me` sends (`app.py:20604`; the page service already reads it, `studio.ts:208`).
- **`may_draw`** is "its creator, holding `draw_on_boards`" (`boards.py:450`; `app.py:5051`, `_may_draw` :5078-5079), **not** the case's Editor
  level the drawing routes also ask (`InvestigationEditorDep`, :5263). A creator lowered to Viewer is offered the controls
  and refused by the route.
- **The React panel.** `apps/workspace/src/boards/BoardEditor.tsx:1395-1441`: "Looks like a loaded item"; "{drawn} looks
  like {loaded} ({why}, {score}%)"; a grey tag "Suggested"; "Same: {drawn} is {loaded}" and "Not the same: {drawn} and
  {loaded}" (only with `mayDraw`); "More looked alike than are shown here."; "A suggestion does nothing by itself. Same
  keeps a link in this case; nothing is merged."; "Nothing drawn here looks like a loaded item." After drawing: "{label}
  added to the board, with a watch for it." (:502). The React editor never reads `/drawn-watches`.
- **The page it extends.** GG4a's board page, `/cases/boards?case=<id>&board=<id>` (`away/GG4a`,
  `apps/pages/server/boards.ts:5-6`), with GG4c's write pattern (a page `POST`, the hidden `_csrf`, then `303` to a `GET`;
  GG4c's ruling Q6 (a)). The page service's Conduit client sends JSON bodies with `GET`, `POST`, `PUT` or `DELETE`
  (`apps/pages/server/conduit.ts:26-33`), enough for this slice.

## Acceptance (red before, green after)

Scenario BD's rows for the watches and the matches (after GG4c's and GG4d's), written first, and
`apps/pages/test/govuk/boards-matches.test.ts`, red on GG4c's page, green after; every earlier BD row unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **The watches said on the board's drawn items, and the *Looks like a loaded item* part with its two
   decisions.** Pictures are GG4f2, promotion GG4f3. (b) Matches only; the watches with the alerts page.
2. **Where it sits.** (a) **Parts of GG4a's board page** (`/cases/boards?case=…&board=…`), the decisions posted to the same
   page, as GG4c's forms are; no new path, no new `FUNCTIONS.yaml` row. (b) A page of its own (a new row, as GR4a's board
   page was given).
3. **Who is shown the suggestions.** The read admits every reader of the board. (a) **Every reader of the board sees the
   suggestions, as the React panel shows them; the two buttons only when `may_draw`.** (b) The creator alone.
4. **What a suggestion says.** (a) **The React panel's sentence and tag**: "{drawn} looks like {loaded} ({why}, {score}%)"
   with a grey GOV.UK tag "Suggested, not confirmed" (rule 5: `inferred` said in words), the loaded item named by GG4a's
   rule for a loaded item. **Never its id, its datasets, its sources or its properties beyond the name** (rule 7): the
   census names them as left out. (b) The loaded item's whole row (type, marking and its properties).
5. **More than are shown.** `more` is set when the list is cut at twenty (`boards.py:918-919`) and also when any one
   search reaches `MATCH_LIMIT` (:881, :895), before decided pairs are removed (:906-916), so deciding does not promise
   that more appear. (a) **The React sentence alone: "More looked alike than are shown here."** (rule 2: said, never cut
   silently). (b) A sentence promising the next ones: not proposed (it would be false).
6. **Deciding.** No route undoes a decision; only withdrawing the drawn item takes it away. (a) **Each button opens a
   confirmation page** ("{drawn} is {loaded}: this keeps a link in this case. Nothing is merged and neither item is
   changed. It cannot be undone here; withdrawing the drawn item takes it with it."), then one `POST`, then `303` to the
   board with a banner naming what was kept. As GG4c's delete (its Q4 (a)). (b) One press, as the React panel; the banner
   after.
7. **The watches.** (a) **The drawn items table gains a column "Watched"**, from one `GET .../drawn-watches` per render,
   matched on `element_id`: **when the watch's `owner` equals the reader's own id (one `GET /v1/me` per render, as
   `studio.ts:208` reads it)**, "Yes: you are alerted when a load looks like it"; to any other reader, "Yes" alone (the
   watch and its alerts are its owner's, never named: the "who made it" ruling of 26 November). `owner`, `dataset_id` and
   the ids are never shown. (b) Not shown; the alert queue alone.
8. **The watch's alert, *Open the board*.** (a) **Not in this slice**: the GOV.UK alert queue is the `alerts-rules-watches`
   row's, and its link to this page is that slice's. (b) Here.
9. **A creator below the Editor level.** `may_draw` does not ask the level the route asks. (a) **The buttons follow
   `may_draw`; the route's refusal is the board's own 404 page, as GG4d's case 13**; the finding goes to the backlog as a
   possible Conduit part (`may_draw` asking the level: an amendment under decision 11). (b) The page asks the level
   itself from another read: not proposed (a second read to guess what the route decides).
10. **Refusals in words.** (a) **`above_your_clearance` and `above_the_ceiling` each said in a sentence** ("These two
    together are marked higher than you may mark a link" / "higher than this case may hold"), naming no marking but the
    capped ceiling the board already sent this reader (the GG4j ruling); `item_not_found` and every other 4xx the 404
    page; nothing written either way. (b) The Conduit's detail.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A board with two drawn items, one alike a loaded item by its passport number (synthetic) | one row: "R. Halloran looks like Rory Halloran (the same passport_number, 100%)", tagged "Suggested, not confirmed" | the tag left out (an `inferred` suggestion said as fact: rule 5) |
| 2 | The route sends `more: true` | "More looked alike than are shown here." under the list | `more` read and dropped |
| 3 | No suggestion | "Nothing drawn here looks like a loaded item." and no list | an empty list drawn |
| 4 | The loaded item's id, datasets and sources in the body | none of them anywhere on the page or in an attribute but the decision form's hidden fields | the loaded `Node` drawn by a generic property list |
| 5 | The creator presses *Same*, then confirms | one `POST .../matches` with exactly `{"drawn", "loaded", "same": true}`; `303` to the board; the banner names both; the pair gone from the next read | `_csrf` passed in the body (`MatchDecision` is `extra="forbid"`; the fixture refuses it as the route does) |
| 6 | *Not the same*, confirmed | one `POST` with `same: false`; the banner says they are kept apart | `same` sent as the string "false" |
| 7 | A shared board read by another Editor | the suggestions shown, no button, no form | the buttons drawn from the case's level rather than `may_draw` |
| 8 | A decision posted by hand by another reader (403 `not_the_boards_creator`) or for an item withdrawn meanwhile (404 `item_not_found`) | the board's 404 page for both | either said in words |
| 9 | `above_your_clearance` from the route | question 10's sentence; nothing written | the 409 shown raw, or the real ceiling named |
| 10 | No `_csrf` on the confirmation's post | refused, nothing sent (I17) | the post outside the check |
| 11 | Watches: two drawn items, one watched | "Yes: you are alerted…" when the watch's `owner` is the reader's id from `/v1/me`; "Yes" for any other reader, the board's creator included when the item is a reference drawn by someone else; nothing on the other | the owner's id or `dataset_id` printed, or "you" decided by the board's creator rather than the watch's `owner` |
| 12 | A watch the route withholds (its item hidden from the reader) | no column value and no count anywhere for it | a count of watches from another read |
| 13 | One render | exactly one `GET` of the board, one of `matches`, one of `drawn-watches`, one of `/v1/me` | a read per item |
| 14 | A body missing a field `MatchSuggestions`, `MatchSuggestion`, `MatchDecided` or `DrawnWatch` requires, or a `state` other than `inferred` | "could not be read" | each required field removed in turn |
| 15 | Keyboard | each decision and its confirmation reachable and working, one case per action in `test/govuk/keyboard/boards.spec.ts` (rule 13) | a button out of the tab order |
| 16 | Scripts off | the parts whole; every form works by posting | a decision that needs a script |
| 17 | The fixture | refuses as the route does, in the route's order (`own_board`, then the item, then the loaded end, then `check_marking`), and cuts at 20 with `more` | a fixture that accepts a decision from a non-creator |

## Waits on

GG4c merged (the write pattern); GG4b and GG4j merged (they change what the board route sends); GG4d for the shared
refusal words.

## Files touched

`spec/08` (BD's watch and match rows); `apps/pages/server/boards.ts`, `server/views/boardsWords.ts`;
`tree-govuk/boards.njk` and a confirmation template; `test/govuk/boards-matches.test.ts`, `boardsConduit.ts` (the two
routes and their refusals), `keyboard/boards.spec.ts`, `scripts-off/boards.spec.ts`; `apps/pages/FUNCTIONS.yaml` (the
`drawing-boards` row's scenario ids); `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (the census
gains `MatchSuggestions`, `MatchSuggestion`, `MatchDecided`, `DrawnWatch`).

## Checks (frozen when cut)

GG4c's list.

## Out of scope

Pictures (GG4f2); promotion (GG4f3); the alert queue's *Open the board* (question 8); any Conduit change (question 9's
finding goes to the backlog); `apps/workspace`.
