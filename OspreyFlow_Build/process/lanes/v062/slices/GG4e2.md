# Slice GG4e2 · GG4 · The board module: moving an item by pointer and by the arrow keys, and the link handle opening the Draw a link form, with I7's coverage test for the GOV.UK board page

- **Build id:** GG4 (the `drawing-boards` row)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:**
  - GG4e1 (the picture the module works on);
  - **GG4d** (the *Draw a link* form the handle opens). **GG4d has no row in `slices.tsv`:** it is drafted only
    (`drafts_2026-11-26/GG4d.md`). Its draft leaves one gap, in `INDEX.md`: its change form needs `PATCH`, which
    `apps/pages/server/conduit.ts:28` cannot send.

  **No hold by decision 9** (no drawing library).
- **Split:** the second of GG4e's two parts (see GG4e1).
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. No question is the owner's.

## What

With scripts on, a page module (`apps/pages/modules/board.ts`) makes the board's creator able to move an item on
GG4e1's picture, by dragging it or by the arrow keys. A move is kept by the board's layout route. Dropping an item's
link handle on another item opens GG4d's *Draw a link* form with both ends filled. ADR-143 C6 and C7
(`spec/06_DECISIONS.md:26564-26569`) say items move by dragging, links by the handle, and each drag has its keyboard
route (I7, rule 13). **This part also adds the first I7 coverage test in the page service** for the board page. GOV.UK
page only.

**The answers (each (a), and why):**

5. **(a) Moving by keys.**
   - The arrow keys move the focused item by 8 units, and Shift with an arrow by 40.
   - Each move is sent as **one `PUT .../boards/{board_id}/layout` with that item alone**, after the keys stop for
     400 ms. It goes through the `/v1` forwarder with `X-CSRF-Token` (the page service's check, `apps/pages/server/
     csrf.ts:48`; the forwarder carries `PUT`, `forward.ts:85`).
   - One `PUT` is in flight at a time. A refused or failed move puts the item back and says so in a live region.
   - Why (a): a send per key press would make tens of writes for one move, and the store keeps the last write for
     each key (`services/api/case_views.py:216`, `{**board.layout, **(layout or {})}`), so order matters.
6. **(a) The link handle opens GG4d's *Draw a link* form with both ends filled** (`source` and `target` in hidden
   fields). Nothing is sent until the form is submitted. Why (a): no new write path, so the form stays the one place a
   link is checked.
7. **(a) I7 in the page service.**
   - A `test/govuk/keyboard/registryCoverage.test.ts`, built as the workspace's
     `apps/workspace/keyboard/registryCoverage.test.ts` is (a text scan of the folder's specs for `assertAllCovered`).
   - A `BOARD_ACTIONS` `assertAllCovered` in `keyboard/board-module.spec.ts` over the ids the GOV.UK board page offers.
   - **No GOV.UK keyboard spec names a registry id today**: `keyboard/boards.spec.ts` proves GG4a's and GG4c's forms
     by their own BK cases, with no id. So the ids those cases already prove are named in them:
     `open-a-board-from-the-boards-list-by-keyboard`, `make-a-blank-board-by-keyboard`,
     `share-a-board-with-the-case-by-keyboard` and `go-back-to-the-boards-by-keyboard`, each only where its case
     exists. This part adds `move-an-item-by-the-arrow-keys` and `draw-a-link-from-the-selected-item-by-keyboard`.
   - **The test holds a list of the ids not yet offered, each naming the slice that will offer it**, so an id leaves
     the list only by gaining a case:
     - GG4d: declaring an item, with or without a source document, editing and withdrawing, and the item menu's three;
     - GG4f1: the two match decisions;
     - GG4f2: the two picture ids;
     - GG4f3: promotion, and closing its sheet by Escape.
   - **`unowned` is written for the ids no brief owns:** `make-a-board-from-a-view-by-keyboard` and
     `make-a-board-from-the-selection-by-keyboard` (GG4c left them out), `start-a-drawing-with-no-case-by-keyboard`,
     `choose-an-items-icon-by-keyboard`, `inspect-an-item-by-keyboard` and `inspect-an-item-from-its-menu-by-keyboard`
     (`packages/glass-shared/src/keyboard/actionRegistry.ts:518-543`).
   - Why (a): rule 13 for this page, made visible rather than claimed. Covering every id at once is not possible
     before GG4f.
8. **(a) No CSSOM helper.** Moving sets `x` and `y` (or `transform`) with `setAttribute`, which are SVG attributes,
   not styles. A pointer's cursor during a drag is a class. Why (a): ADR-152 decision 8 forbids an inline style, and
   decision 3's helper (`spec/06_DECISIONS.md:41001-41002`) is not needed.

## What exists today (re-read at `b79164850`)

- **The layout route** `PUT .../boards/{board_id}/layout` (`services/api/app.py:5189-5203`):
  - 204, `_DRAWS` (`DRAW_ON_BOARDS` and `INVESTIGATE`, :4973), `InvestigationEditorDep` (:5195) and `own_board`
    (:5202, the board's creator only);
  - **not audited**: "the board's own layout, not data".
  - Its body is `BoardMove` (`packages/schemas/boards.py:197-202`): `positions`, at most 10,000 keys,
    `extra="forbid"`.
  - `boards.move` (`services/api/boards.py:651-665`) keeps only items the board holds that the reader can see, and
    raises nothing.
- **`may_draw`** is `created_by == principal.id` (`boards.py:474`), and the route ANDs `_may_draw` (`app.py:5061`,
  :5088-5089). It does not check the Editor level the drawing routes require, so a creator who is now a Viewer is
  offered a move the route refuses. The module says that refusal as any other (case 11).
- **The keyboard registry:** `BOARD_ACTIONS` (`actionRegistry.ts:517-544`, 25 ids). No `assertAllCovered` runs under
  `apps/pages/test`, and the GOV.UK keyboard specs are `apps/pages/test/govuk/keyboard/*.spec.ts`.
- **Modules:** `scripts/assets.mjs` bundles each `.ts` directly in `modules/` as one hashed ES module (:13, :209-215),
  under the empty drawing list (:31). The board module imports no drawing library.

## Round 1's steps

1. Write BD's moving and handle rows (after GG4e1's) and the acceptance test files first. Show them red on GG4e1's
   page: nothing moves.
2. Write `modules/board.ts`, with one delegated listener on `data-action` and `data-id` and a latest-answer-wins guard
   (decision 3). It attaches only when the page's JSON block says `may_draw`. Items become focusable only then.
3. Make the fixture Conduit refuse as the route does (rule 15): 404 for a board deleted meanwhile, 403 for the rights
   or a non-creator, 422 for a body that is not a `BoardMove`. `boards.move` itself refuses nothing.
4. Add the handle's hand-off to GG4d's form (a link to the form's address with both ends in the query, carried into
   hidden fields).
5. Add the coverage test and the ids (item 7). Run the checks and every plant.

## Acceptance test (new, red on main)

All are red on main:
- `OspreyFlow_Core/apps/pages/test/govuk/board-module.test.ts` (new; vitest over the module's pure parts and a fake
  forwarder);
- `OspreyFlow_Core/apps/pages/test/govuk/keyboard/board-module.spec.ts` (new; Playwright, both browsers);
- `OspreyFlow_Core/apps/pages/test/govuk/keyboard/registryCoverage.test.ts` (new; vitest);
- the boards scenario test `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py`, extended.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | Move by the arrow keys | one `PUT` with the item's new place, after the 400 ms pause; the picture and the stored place agree on reload | a `PUT` per key press |
| 2 | Move by pointer | the same, sent on drop | the move sent before the drop |
| 3 | The `PUT`'s body | exactly `{"positions": {"<item>": {"x": …, "y": …}}}`, that item alone | the whole layout sent |
| 4 | A refused move (404 board deleted, 403 rights or not the creator), or no answer | the item back where it was; the live region says the move was not kept | the item left at the new place |
| 5 | Two moves in quick succession | one `PUT` in flight; the second sent after the first's answer; the stored place is the last move | two `PUT`s in flight at once |
| 6 | No `X-CSRF-Token` | refused by the page service, nothing reaches the Conduit (I17) | the module sending the token as a form field |
| 7 | The handle dropped on an item | GG4d's form with both ends filled; nothing sent until it is submitted | the link posted by the module |
| 8 | A reader who is not the creator (`may_draw` false) | no handle, no move; items not focusable | the module attached whatever `may_draw` says |
| 9 | Scripts off | GG4e1's picture and the tables, unchanged (I4) | the picture built only by the module |
| 10 | No inline style | no `style` attribute written during or after a move; the policy spec green | `el.style.transform` set during a drag |
| 11 | A creator who is now a Viewer (offered by `may_draw`, refused by the route) | the move put back and said, as case 4 | the 403 left unsaid |
| 12 | I7: the coverage test | green with the offered ids proved; red with one offered id's case removed; red if a listed id gains a case and stays listed | an offered id with no case |
| 13 | The not-yet-offered list | every `BOARD_ACTIONS` id is offered or listed, each listed one naming a slice or `unowned` | an id in neither |
| 14 | No internal id | an item's id only in `data-id` and the hidden fields, never in text or the live region | an id announced |

## Checks

GG4e1's row's checks.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario BD's moving and handle rows, after GG4e1's picture rows** in BD.

## Out of scope

- drawing, editing and withdrawing items (GG4d);
- pictures, matches and promotion (GG4f);
- a CSSOM helper;
- auditing a move (the route's own choice);
- the ids listed `unowned` (each to the backlog, in `INDEX.md`);
- any Conduit change;
- `apps/workspace`;
- the Default tree.

**Stop and ask** if a move needs a style rather than an attribute, or if GG4d's form takes its ends some other way.

## Proposed `slices.tsv` row (not added)

```
GG4e2	GG4	The board module on GG4e1's picture: an item moved by pointer and by the arrow keys (8 units, Shift 40), one PUT .../layout with that item after a 400 ms pause, one in flight, put back and said when refused; the link handle opens GG4d's Draw a link form with both ends filled; the first I7 coverage test in the page service for BOARD_ACTIONS, every id offered or listed with its slice (the owner's standing (a), D274; draft drafts_2026-11-28)	GG4e1,GG4d	2	lane/slice-GG4e2	full	OspreyFlow_Core/apps/pages/test/govuk/board-module.test.ts,OspreyFlow_Core/apps/pages/test/govuk/keyboard/board-module.spec.ts,OspreyFlow_Core/apps/pages/test/govuk/keyboard/registryCoverage.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/board-module.test.ts test/govuk/keyboard/registryCoverage.test.ts && npm run test:govuk --workspace apps/pages -- keyboard/board-module.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4e2 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4e2 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4e2 uv run --frozen ruff check .
```
