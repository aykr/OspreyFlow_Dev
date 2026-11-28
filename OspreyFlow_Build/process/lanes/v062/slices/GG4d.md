# Slice GG4d · GG4 · Drawing on a board without a mouse: adding a drawn item, drawing a link, changing and withdrawing an item, as scripts-off forms on the GOV.UK board page

- **Build id:** GG4 (the `drawing-boards` row of `apps/pages/FUNCTIONS.yaml`; its route stays empty: the function is whole only after GG4e and GG4f)
- **Dial setting:** balanced
- **Rounds limit:** the dial's
- **After:** GG4c, GG4b, GG4j (all three on main at `b79164850`)
- **How it was cut:** an away build round on the server's build account (D246; the owner's word D295, 28 November 2026), from
  the draft `slices/drafts_2026-11-26/GG4d.md`, **every proposal (a)**, as the away round's instructions say for every
  question that is not the owner's kind. None of the draft's eight questions is the owner's kind (no security finding, key,
  decision record, widened permission or removal): each is a page's shape over routes that already exist and already decide.
  Every citation below was re-read on this tree (`away/GG4d`, cut from `origin/main` at `b79164850`); the draft's line numbers
  had all moved.

## What

ADR-143 C7 (`spec/06_DECISIONS.md`, "with *Draw a link* as the keyboard route") and decisions 4 and 5 (every drawn item
carries its author, marking, grading and source; only its author changes or withdraws it, never deleted). A scripts-off page
has no drag, so **the forms are the whole of drawing here**, and they are the keyboard route GG4e's module will name. The
page is GG4a's board page (`/cases/boards?case=<id>&board=<id>`), written GG4c's way: a page `POST`, one Conduit call built
by the server half, then `303` to a `GET`.

**What exists today (re-read on this tree).**

- The routes (`services/api/app.py`), each behind `_DRAWS` (`draw_on_boards` then `investigate`, :4973) and the case's
  Editor gate (`InvestigationEditorDep`):
  - `POST .../boards/{board_id}/items` (`declare_drawn_item`, :5140-5162), 201 `DrawnItemMade`: `own_board` first (404
    `board_not_found`, then 403 `not_the_boards_creator`), then the grade against the deployment's scheme
    (`_graded_in_the_deployments_scheme`, :5075-5085, 422 `grading_scheme`), then `Boards.declare`
    (`services/api/boards.py:533-577`): 422 `not_in_the_model`, 422 `not_a_property`, `check_marking` (:213-241: 422
    `not_a_marking`, 422 `above_the_deployments_highest_marking`, 409 `above_the_ceiling`, 409 `above_your_clearance`),
    422 `no_such_document`. The body `DrawnItemInput` (`packages/schemas/boards.py:64-72`, `extra="forbid"` from
    `_Asserted`, :44-61): `label` 1 to 200, `marking`, `grading`, `source_note` up to 2,000 **and now required** (since
    GG4b, ADR-143 Amendment 8 item 7: `_has_a_source_note`, :55-61), `source_document`, `type`, `properties`, `icon`, `x`,
    `y`. Audited `draw_item`.
  - `POST .../boards/{board_id}/links` (`draw_link`, :5165-5186), 201: `own_board`, the grade, then `Boards.link`
    (:579-649): 422 `not_in_the_model`, 422 `same_item`, 422 `ends_not_on_the_board`, 422 `wrong_ends`, `check_marking`,
    422 `no_such_document`, 409 `already_drawn`. Body `DrawnLinkInput` (:75-81): `type`, `source`, `target` and the
    assertion.
  - `PATCH /v1/investigations/{id}/board-items/{item_id}` (`edit_drawn_item`, :5206-5229): the grade, then `Boards.edit`
    (:705-789) after `_own_item` (:667-703: 404 `item_not_found`, 403 `not_your_item`, 409 `promoted`, 409
    `drawing_merged`): 422 `not_a_marking`, 409 `link_marking_kept`, 409 `marking_never_lowered`, `check_marking`, 422
    `no_such_document`, 422 `no_source` (an old item gains its note at its next edit), 422 `not_a_property`. Body
    `DrawnItemEdit` (:84-95): "what is not given stays. A marking is never lowered."
  - `POST .../board-items/{item_id}/withdraw` (`withdraw_drawn_item`, :5232-5249), `Withdrawn` (:205-215): the node, the
    drawn links and pictures that went with it that the reader may see, "so nothing is dropped silently (rule 2)"; what they
    may not see is named and counted in nothing (rule 3). `_own_item` first, then 409 `promoted`.
  - Every refusal is `{"error": code, "detail": words}` (`_drawing_refused_handler`, :3233-3236; `ItemNotFound` :3201-3204;
    `NotTheBoardsCreator` :3207-3219; `AboveTheDeploymentCeiling` :3407-3422). **The item routes never call `own_board`.**
- What the forms' choices come from: `BoardOpened` (`packages/schemas/boards.py:157-186`) sends `node_types`,
  `link_types`, `markings` (cut to the reader, `boards.py:345-350`), `ceiling` (capped for the reader since GG4j),
  `layout`, `items` (element id to item id) and, from the route, `grading_scheme` and `grading_grades` (`app.py:5069-5070`).
  A type's required properties come from `GET /v1/ontology` (`app.py:9333`, deployment-wide schema metadata), as the React
  form takes them from the ontology (`apps/workspace/src/boards/BoardEditor.tsx` `EntityTypeShape`, `ItemForm`'s
  `required`).
- Whose item it is: the React editor's own rule (`BoardEditor.tsx:274-275`, `isMine`): drawn, the reader may draw on the
  board (`may_draw`, its creator), the board names its item id, and `asserted_by` equals the board's `created_by`. The
  page uses the same comparison of two ids the route sent, and shows neither.
- `apps/pages/server/conduit.ts` sends `GET`, `POST`, `PUT` and `DELETE` only: **`PATCH` is added** (one word in `Call`).

## The rulings, as built (every proposal (a))

1. **Q1 (a) scope:** add an item, draw a link, change an item, withdraw an item. Moving is GG4e's; pictures, matches,
   watches and promotion are GG4f's. Change and withdraw are offered for drawn **items** (nodes); a drawn link's own change
   and withdrawal are left for GG4e's module (a link's marking cannot change at all: `link_marking_kept`).
2. **Q2 (a) two steps:** `&add=item` lists the case's `node_types` as links (actions as links, decision 13); `&add=item&type=<T>`
   is the form: the label, the marking, the grading, the source note, and the type's required properties (from
   `/v1/ontology`, as the React form) as labelled fields. A type not in `node_types` is the board's 404 page.
3. **Q3 (a) placement:** the page sends the first free place on a plain grid (x from 0.15 by 0.12 to 0.87, rows from 0.15
   by 0.18), worked out from the `layout` the board sent, so three items drawn by form get three places and none sits on
   another. The step-two form's own read of the board gives the layout, and the place it works out goes with the form in
   two hidden fields, `x` and `y` (the post makes one call and reads nothing, BD27's rule). A place that is not two numbers
   from 0 to 1 is no form of this page's: the board's 404 page, nothing sent. Layout is "the board's own layout, not
   data" (`app.py:5201`), so a place changed by hand moves an item and tells no one anything.
4. **Q4 (a) source document:** not offered. GG4b has landed, so the ruling's "until GG4b" is met; how a document is chosen
   (no route lists a case's documents) is a question for a later part, named in the report. The form offers the source
   note alone, which the route requires.
   **Q4b:** GG4b's question 3 was ruled (a) on 27 November: **a note is required.** The form requires it; the change form
   keeps the note an item has unless one is typed (its field starts empty: the page shows no source note, as since GG4a),
   and the route's `no_source` for an old item with none is said as the page's sentence.
5. **Q5 (a) ids:** an item id or a node id travels only in a link's query (`&change=<item id>`, `&withdraw=<item id>`), a
   hidden field, or a `<select>` option's value; never in text.
6. **Q6 (a) lowering a marking:** the change form offers only the `markings` at or above the item's own; a lower one posted
   by hand is the route's `marking_never_lowered`, said in words.
7. **Q7 (a) withdrawing:** a confirmation page, "Links and pictures drawn to it are withdrawn with it. Nothing is
   deleted.", with no count and no name; then one `POST`, then `303` to the board with a banner naming what the route's
   `Withdrawn` says went with it, as the React editor says it (`BoardEditor.tsx:229-248`: "{label} withdrawn, with 2 links
   drawn to it (A, B), and its picture. It is kept in the audit."); a link the answer names that the confirmation's read
   did not show is said as "1 on another board", as there.
8. **Q8 (a) refusals:** each code has the page's own sentence in the GOV.UK error summary above the form, the person's
   words kept; an unknown code is "The board could not take that. Nothing was changed." `not_the_boards_creator`,
   `not_your_item`, `board_not_found` and `item_not_found` are the board's 404 page. The deployment's highest marking is
   never named ("above the highest marking this deployment holds", the owner's GG4f3 Q8b ruling of 27 November).

**After each write** the board's next view says what was done once, in a GOV.UK notification banner held in the session
(never in the address), as GG4c's delete banner: "{label} added to the board, with a watch for it." (the React editor's
words, `BoardEditor.tsx:502`), "{label} drawn.", "{label} changed.", and the withdrawal's sentence above.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/boards-draw.test.ts` (new) and
`OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (extended: the BD rows of drawing, BD32 onward, the
census drawing `node_types`, `link_types`, `markings`, `ceiling`-free, `grading_grades`, `layout`, `items`, and
`DrawnAssertion.asserted_by` checked). Scenario BD's drawing rows are written first in `spec/08`, inside Scenario BD's
section, after BD31. Red on main (no drawing control, no route modelled), green after. GG4a's and GG4c's rows stay green;
where a GG4c test pins the board page's tab order, that pin gains the new stops (the board page's own order), and nothing
else of theirs changes.

The table of cases (each red first, the planted fault at the real call site, rule 15), as the draft's 1 to 16:

| # | Case | Expected | The planted fault |
| --- | --- | --- | --- |
| 1 | The creator adds a Person "J. Ashdown", OFFICIAL, graded B 2 1 in 5x5x5, with a note | one `POST .../items`, exactly the `DrawnItemInput` fields; `303`; the item in the drawn table; the banner once | `_csrf` passed in the body (the fixture refuses an extra field) |
| 2 | Step one, then step two for a type with a required property | the types as links; the property's field with its name in words | another type's fields |
| 3 | A type not in `node_types` posted by hand | the `not_in_the_model` sentence, the words kept | the 422's detail passed through |
| 4 | The markings offered; one above the reader's clearance posted | only `markings`; `above_your_clearance` in words | the list drawn from `ceiling`; the 409 raw |
| 5 | The grade fields; a grade of another scheme posted | `grading_grades`' own; the `grading_scheme` sentence | fields from the built-in 5x5x5 |
| 6 | No note | the error summary's note sentence; nothing sent | the form sent with none |
| 7 | A link between a drawn and a loaded item | one `POST .../links`; listed in the links table | an end offered from outside `nodes` |
| 8 | A link from an item to itself | the `same_item` sentence; nothing sent | the page sending it |
| 9 | Three items drawn by form | three distinct places | every item at 0, 0 |
| 10 | Change a label | one `PATCH` with `{"label"}` alone | the whole item sent |
| 11 | The change form's markings; a lower one posted | only those at or above; `marking_never_lowered` in words | the lower ones offered |
| 12 | Withdraw, after the confirmation | one `POST .../withdraw`; gone from every table; the banner names what went | "withdrawn" alone |
| 13 | Someone else's board (403) or item (403) posted by hand | the board's 404 page for both | either 403 said in words |
| 14 | No `_csrf` | refused, nothing sent | the route outside the check |
| 15 | Keyboard | each form reached and worked, one case per action in `keyboard/boards.spec.ts` (rule 13) | a step out of the tab order |
| 16 | The fixture | refuses each code where and as the route does, in the route's order | a fixture that accepts a lowered marking |

Command (acceptance): `cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/boards-draw.test.ts`
and the scenario test, as GG4c's row.

## Checks

GG4c's list, with `test_route_pins.py` and `test_page_lists_merge.py` added (the owner's ruling of 27 November, about
17:12, item 3, for every page part), and `test/server` (the `PATCH` in `conduit.ts`): `npm test --workspace apps/pages`;
`npm run lint`; `npm run typecheck`; `node scripts/no_react_check.mjs`; the GOV.UK scenario tests (boards, cases, help,
admin people), `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_route_pins.py`, `test_page_lists_merge.py`, `test_ui_words_check.py`,
`test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`; `ruff check .`. Pure only: store ports pinned to 9.

## Out of scope

Moving items (GG4e); a drawn link's change or withdrawal (GG4e's module); pictures, matches, drawn watches and promotion
(GG4f1 to GG4f3); a source document on the form (a later part: question 4); showing a source note (the source column's own
page part); any Conduit change; `apps/workspace`; the Default tree's twin. No new path, no new `FUNCTIONS.yaml` row, no line
in `routes.yaml` or `PAGES` (the page is GG4a's, at its own path). Stop and ask the owner rather than answer: any wish to
widen what a reader is shown of an item (its note, its document, its author), or to offer a write the route's own check
does not already decide.

## Proposed `slices.tsv` row (not written into `slices.tsv`: the conductor adds it)

```
GG4d	GG4	Drawing on a board without a mouse: add an item, draw a link, change and withdraw an item, as scripts-off forms on GG4a's board page (every proposal (a); the note required since GG4b; away round D295, 28 November 2026)	GG4c,GG4b,GG4j	2	lane/slice-GG4d	full	OspreyFlow_Core/apps/pages/test/govuk/boards-draw.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/boards-draw.test.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4d uv run --frozen ruff check .
```

## Round 1 in the line (D247; the owner, 28 November 2026): merge `away/GG4d` first

**Your first step: merge the local branch `away/GG4d` (`96de65d`) into your branch.** Keep both sides where main has moved.
- Its report, `process/lanes/v062/away/GG4d_AWAY_REPORT.md` on that branch, is the record of the away round. Read it whole: every figure in it was taken on the server, and none is a measurement here.
- **Where main has moved:** GG3b, GG3a, GR1d, GA1a and other page parts change the same append-only lists (`pageList.ts`, `routes.yaml`, `FUNCTIONS.yaml`, the route pins, `test_pages_setting.py`, `spec/08`). **Take every page's entry; drop none.**
- In `spec/08`, your rows go in Scenario BD where the away branch put them. Change no other section, and add nothing at the end of the file.
- **The draft's gap, re-check it:** the change form needs `PATCH`, and `apps/pages/server/conduit.ts:28` sent GET, POST, PUT and DELETE only on 26 November. Say in your report how the branch sends the change. If `PATCH` is not supported, add it to the forwarder with its own test, red first.
- **Q4 and Q6** were built as proposed: no source document offered, and no marking below the item's own. They are with the owner as security-rule questions; build nothing different until he rules.
