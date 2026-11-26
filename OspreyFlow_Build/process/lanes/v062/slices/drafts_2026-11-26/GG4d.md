# Slice GG4d · GG4 · Drawing on a board without a mouse: adding a drawn item, drawing a link, changing and withdrawing an item, as scripts-off forms (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** ADR-143 C7 (`spec/06_DECISIONS.md` about lines 26567 to 26569): items move by dragging and links
are drawn by the handle, by Alt-drag or by right-click, "**with *Draw a link* as the keyboard route**"; decision 4: every
drawn item carries `asserted_by`, `asserted_on`, a marking, a grading and a source note or document; decision 5: only its
author edits or withdraws its items, never deleted. A scripts-off page has no drag, so **the form is the whole of drawing
here**, and it is also the keyboard route the board module (GG4e) will reuse. It follows GG4c's write pattern (a page
`POST`, the Conduit called by the server half, a `303` to a `GET`).

## What exists today (read on `origin/main` at `042c882f2` and on `away/GG4a`; re-read, lines move)

- **The routes** (`services/api/app.py`), each behind `_DRAWS` and the case's Editor gate. **The board routes
  (items, links) start with `own_board`** (the board, 404, then its creator, 403 `not_the_boards_creator`); **the item
  routes (change, withdraw) never call `own_board`**: they check the item's author in `_own_item`, refusing another's
  item with **403 `not_your_item`** (`services/api/boards.py:656-660`), and the change route checks the grade first
  (`app.py:5209`):
  - `POST .../boards/{board_id}/items` (`declare_drawn_item`, :5130-5152), 201, `DrawnItemInput`
    (`packages/schemas/boards.py:62-70`): `type` (one of the case model's types, C14), `properties` (checked against the
    type), `icon`, `x`, `y`, and the assertion (`_Asserted`, :43-59): `label` 1 to 200, `marking`, `grading`,
    `source_note` up to 2,000, `source_document`; "give a source note, a document of the case, or both". The grade is
    checked against the deployment's scheme first (`_graded_in_the_deployments_scheme`, :5060-5068). Audited
    `draw_item` with the type and the marking.
  - `POST .../boards/{board_id}/links` (`draw_link`, :5155-5176), 201, `DrawnLinkInput` (:73-79): `type`, `source`,
    `target` (two items on the board, drawn or loaded) and the assertion. Audited `draw_link`.
  - `PATCH /v1/investigations/{id}/board-items/{item_id}` (`edit_drawn_item`, :5196-5219), `DrawnItemEdit` (:82-93):
    "what is not given stays. **A marking is never lowered.**" A raised marking raises a waiting promotion's.
  - `POST .../board-items/{item_id}/withdraw` (:5222-5239), `Withdrawn`: "out of every read, never deleted; its watch
    ends". A drawn link touching a withdrawn node goes with it, as does a picture (`boards.py:761-791`), and "what the
    reader may not see goes too, but is told to them in nothing: not named, not counted".
  - Refusals (`DrawingRefused`, 409 by default, handler `app.py:3232-3235`): `not_a_marking` 422, `above_the_ceiling`,
    `above_your_clearance`, `not_in_the_model` 422, `same_item` 422, `not_a_property` 422, `no_such_document` 422,
    `grading_scheme` 422; also `ends_not_on_the_board` and `wrong_ends` 422 (`boards.py:575`, :584), `already_drawn` 409
    (:599), `marking_never_lowered` and `link_marking_kept` 409 (:694, :700), `promoted` and `drawing_merged` 409,
    `not_your_item` 403, `no_source` 422 (:720-727); `ItemNotFound`, 404 `item_not_found` (`app.py:3200-3203`);
    `AboveTheDeploymentCeiling` (`app.py:3406`). **The builder lists every code from the code, not from this draft.**
- **What the form's choices come from.** `BoardOpened` already sends `node_types`, `link_types`, `markings` (cut to the
  reader, `boards.py:448`), `ceiling`, and the route adds `grading_scheme` and `grading_grades` (`app.py:5054-5060`).
  **GG4a named these as left out** of its census, as "only drawing needs" them. `Grading` is `scheme`, `source`,
  `intelligence` and `handling` (`packages/schemas/domain.py:301-320`; the built-in schemes' parts at :293-296).
- **The React form.** `BoardEditor.tsx` (1,442 lines): the *Draw a link…* form, the withdraw confirmation (:227-248,
  :579-599), "Drawn by" (:1238). Keyboard ids in `BOARD_ACTIONS` (`actionRegistry.ts:517-544`), among them
  `draw-a-link-from-the-selected-item-by-keyboard` (:529) and `draw-a-link-from-an-items-menu-by-keyboard` (:530).

## Acceptance (red before, green after)

Scenario BD's rows for drawing (after GG4c's), written first, and `apps/pages/test/govuk/boards-draw.test.ts`, red on
GG4c's page, green after; GG4a's and GG4c's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Add an item, draw a link, change an item, withdraw an item.** Moving (layout) has no form here: it is
   the module's (GG4e). Pictures, matches and promotion are GG4f. (b) Add and link only; change and withdraw later.
2. **The item's type and its properties, scripts off.** (a) **Two steps:** a first form chooses the type from
   `node_types`; the second, at the same page with `&type=…`, shows that type's key properties as fields, with the
   label, marking, grading and source. (b) One form with every type's fields, hidden by script: impossible with scripts
   off.
3. **Where a new item is placed** (`x`, `y`, which the route defaults to 0). (a) **The page sends the next free place on a
   plain grid**, worked out from the board's `layout` as the route sent it, so items drawn by form never sit on one
   another when the module draws them. Layout is "the board's own layout, not data" (`app.py:5188`). (b) Send 0 and
   leave arranging to GG4e.
4. **The source document on the form.** (a) **Not offered until GG4b is ruled and built**: the form offers the source
   note alone, which the schema already accepts. Once GG4b lands, how a document is chosen is a question
   of its own: **no route lists a case's documents** (GG3b's finding), so a choice needs a list route (an amendment) or
   a document reached from another page (a citation, a search result) and carried to the form. (b) A document id typed by hand. **Not proposed** (rule 7).
4b. **This depends on GG4b's question 3.** If the owner rules that a source note is required from now on, the form
   requires it; if not, the note is still the form's only source until GG4b.
5. **Ids on the page.** The item routes take an `item_id`, and a link takes two node ids. (a) **They travel only in a
   form's hidden field or a link's own path, never in text**, as GG4a's rule for ids in a link's path. (b) Your words.
6. **Lowering a marking.** (a) **The change form offers only markings at or above the item's own**, and the route's
   refusal is said in words if one is sent by hand. (b) Every marking, the refusal said after.
7. **Withdrawing.** (a) **A confirmation page that says "Links and pictures drawn to it are withdrawn with it. Nothing is
   deleted."**, with no count and no name of what goes with it (the route tells the reader nothing of what they may not
   see), then a `303` to the board with a banner **naming what the route's `Withdrawn` answer says went with it**: it
   returns the links and pictures the reader may see "so nothing is dropped silently (rule 2)"
   (`packages/schemas/boards.py:201-210`), as the React editor says them (`BoardEditor.tsx:237-248`). (b) No count on the
   banner either. **Not proposed** (rule 2).
8. **Refusals in words.** (a) **Each `DrawingRefused` code has the page's own sentence**, said in the GOV.UK error
   summary above the form with the person's words kept (`not_in_the_model`: "That type is not in this case's model";
   `above_your_clearance`: "You cannot mark it higher than your own clearance"; and so on, one per code), and an
   unknown code is "The board could not take that. Nothing was changed." (b) The Conduit's detail.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The creator adds a Person "J. Ashdown" (synthetic), marked OFFICIAL, graded B2 1 in 5x5x5, with a note | one `POST .../items` whose body is exactly the `DrawnItemInput` fields given; `303` to the board; the item in GG4a's table | `_csrf` passed through in the body (the assertion's model is `extra="forbid"`, `packages/schemas/boards.py:46`; the fixture refuses an unknown field as the route does) |
| 2 | Step one, then step two for a type with two key properties | both fields offered, with the type's own names | the fields of another type |
| 3 | A type not in `node_types` posted by hand | "That type is not in this case's model", the words kept | the 422's detail passed through |
| 4 | The marking list offered, and a marking above the reader's clearance posted by hand | only `markings` (cut to the reader) offered; the hand post said as "You cannot mark it higher than your own clearance" | (offered) the list drawn from `ceiling`; (hand post) the 409 `above_your_clearance` shown raw |
| 5 | The grade fields offered, and a grade of another scheme posted by hand | the deployment's scheme's grades (`grading_grades`); the hand post said as the `grading_scheme` sentence | (offered) the fields drawn from the built-in 5x5x5 whatever the deployment's; (hand post) the 422 shown raw |
| 6 | No note (question 4 (a)) | the error summary: a source note is needed | the form sent with neither, the 422 shown raw |
| 7 | A link between a drawn item and a loaded item | one `POST .../links`; listed in GG4a's links table | an end chosen from outside the board's `nodes` |
| 8 | A link from an item to itself | the `same_item` sentence | the page sending it |
| 9 | The next free place (question 3 (a)) | three items drawn by form get three distinct places | every item at 0, 0 |
| 10 | Change an item's label | one `PATCH`, with only the changed field | the whole item sent (a `PATCH` must send only what changed: "what is not given stays", `boards.py:82-93`) |
| 11 | The change form's markings, and a lower marking posted by hand | only markings at or above the item's own offered; the hand post's 409 `marking_never_lowered` said in words | (offered) the lower markings offered; (hand post) the 409 shown raw |
| 12 | Withdraw, after the confirmation | one `POST .../withdraw`; the item gone from every table; the banner names what `Withdrawn` says went with it | the banner saying only "withdrawn" (the answer's links dropped: rule 2) |
| 13 | Someone else's board (403 `not_the_boards_creator`), or an item not the reader's (403 `not_your_item`), posted by hand | the same 404 page as a missing board for both | either 403 said in words |
| 14 | No `_csrf` | refused, nothing sent (I17) | the route outside the check |
| 15 | Keyboard | each form reachable and working, one case per action in `test/govuk/keyboard/`; these are the keyboard routes GG4e's module will name | a step left out of the tab order |
| 16 | The fixture | refuses each `DrawingRefused` code where and as the route does, in the route's order (for the board routes `own_board`, the grade, then `declare`'s checks; for the item routes the grade, then `_own_item`) | a fixture that accepts a lowered marking |

## Files touched

`spec/08` (BD's drawing rows); `apps/pages/server/boards.ts`, `server/views/boardsWords.ts` (the refusal sentences);
`tree-govuk/boards.njk` and the add, link, change and withdraw templates; `test/govuk/boards-draw.test.ts`,
`boardsConduit.ts`, `keyboard/boards.spec.ts`, `scripts-off/boards.spec.ts`;
`OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (the census now draws `node_types`, `link_types`,
`markings` and the grading fields, which GG4a left out).

## Checks (frozen when cut)

GG4c's list.

## Out of scope

Moving items (GG4e); pictures, matches, drawn watches, promotion (GG4f); a source document (question 4, after GG4b);
any Conduit change; `apps/workspace`.
