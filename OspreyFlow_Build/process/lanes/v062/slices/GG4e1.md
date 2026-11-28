# Slice GG4e1 · GG4 · A board drawn as a picture on its GOV.UK page: server-rendered SVG from the board's layout, no script, the drawn items dashed by class, the tables kept below it

- **Build id:** GG4 (the `drawing-boards` row, `apps/pages/FUNCTIONS.yaml:260-266`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GG4c, GG4b and GG4j, all merged (the page, its writes, and what the route sends since the two security
  parts). **Nothing unmerged:** it can start now. **No hold by decision 9:** the board draws with no library
  (`apps/workspace/src/boards/BoardEditor.tsx:11-49` imports no Sigma).
- **Split, as the 26 November draft proposed (its question 1 (a)):** GG4e is size L, so it is two parts. **GG4e1 (this
  part)** is the picture, with no script. **GG4e2** is the board module: moving by pointer and by keys, and the link
  handle.
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. No question is the owner's.

## What

GG4a's board page, `/cases/boards?case=<id>&board=<id>` (`apps/pages/server/views/boardsWords.ts:181`), gains a
picture of the board above its tables:
- an inline SVG the server writes from `BoardOpened.layout`;
- each item the reader may see at its stored place, and each link between two such items as a line;
- drawn items dashed in the drawn colour, by class, and loaded items plain.

The tables stay below it and carry the content. Nothing on the picture needs a script, and nothing on it moves yet
(GG4e2). ADR-143 C6 (`spec/06_DECISIONS.md:26564-26566`): a board is drawn. Decision 4 (:26625-26629): a drawn item
is "drawn dashed in amber everywhere it appears". GOV.UK page only.

**The answers (each (a), and why):**

1. **The split: (a)** (above). Why: the picture is useful and testable with no script, and the module is a round of
   its own.
2. **(a) The picture is `role="img"` with a short accessible name:** "A picture of the board; the same items and links
   are in the tables below". Its items are not focusable while no script runs. Why (a): the tables carry the content,
   as the GR3a chart rule does. Focusable items that do nothing would be a trap. GG4e2 makes items focusable to move
   them.
3. **(a) Items with no stored place are placed on a grid in the picture only.** Nothing is written.
   - A drawn item always has a stored place: `declare` writes it (`services/api/boards.py:573-576`; `x` and `y`
     default to 0.0, `packages/schemas/boards.py:71-72`), and a place at 0, 0 is a stored place.
   - The items with no place are a board's loaded references from `make()`, which saves `node_ids` only (:399-423).
   - **This part defines the grid:** columns 160 units apart, rows 120 apart, filled left to right below the lowest
     stored place. GG4d's add form, when it is cut, takes its "next free place" from the same function.
   - Why (a): never stack items at the origin, and never write a layout on a read.
4. **(a) The picture's size.**
   - A `viewBox` is fitted to the places, with a 40-unit margin. Its largest drawn size is set in CSS by class.
   - **Past 500 items** the picture is not drawn, and a sentence says "This board is too large to draw here. Its items
     and links are all in the tables below". Never a part of the board (rule 2).
   - The builder measures the render at 500 and records it with the machine. If 500 does not render under the page's
     budget, they bring the figure rather than change the number.
   - Why (a): a stated figure, measured.
8. **(a) No CSSOM helper is needed.** `x`, `y`, `transform` and `viewBox` are attributes, not styles, so the server
   writes them in the markup. Every colour and dash is a class. Why (a): ADR-152 decision 8 forbids an inline `style`
   (`spec/06_DECISIONS.md:41087-41088`), and decision 3's helper (:41001-41002) does not exist yet. None is needed.

**The colour:** the React board draws a drawn item with `var(--warning)`, dashed: `.board__line--drawn { stroke:
var(--warning); stroke-width: 2; stroke-dasharray: 6 4; }` and `.board-item__body--drawn { border: 2px dashed
var(--warning); }` (`apps/workspace/src/boards/boards.css:57`, :71). The page uses the same token. `packages/design/
tokens.css:51` is `--warning:#d9a63f`, and there is no other amber or drawn token. **No token changes.**

## What exists today (re-read at `b79164850`)

- **The layout.** `BoardOpened.layout` is `{node id: {x, y}}` for the items the reader may see: `if k in set(shown)`
  (`services/api/boards.py:468`, over `shown` at :433). So the picture can draw only what the route sent.
  `PUT .../boards/{board_id}/layout` (`app.py:5189-5203`) is GG4e2's.
- **The page:**
  - `apps/pages/server/boards.ts` (`boardsPage`, :237-246: `/cases/boards`, GET and POST, `trees: ["govuk"]`);
  - `tree-govuk/boards.njk`, with tables at :33, :75, :90 and :105;
  - the census `CENSUS.BoardOpened` lists `layout` as left out (`boardsWords.ts:117`). This part moves it to drawn;
  - tests `test/govuk/boards.test.ts`, `boards-write.test.ts`, `boardsConduit.ts`, `boardsServer.ts`,
    `keyboard/boards.spec.ts`, `scripts-off/boards.spec.ts`;
  - the scenario test `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (`PATH = "/cases/boards"`,
    :101);
  - Scenario BD (`spec/08_ACCEPTANCE_SCENARIOS.md:958`), whose last row is BD31 (:1008).
- **The policy:** the page service's `style-src` is nonce-only (`apps/pages/server/headers.ts:38`), so a `style="…"`
  attribute is a `securitypolicyviolation` in the browser. The only browser policy spec is GG5a's
  `apps/pages/test/csp/map.spec.ts`. `findInlineStyle` (`packages/glass-shared/src/layout/panelFrameStore.ts:532`) is
  used only by its own test, and nothing in `apps/pages` calls it.

## Round 1's steps

1. Write BD's picture rows and the acceptance test files first. Show them red on main: no picture.
2. **The view model in `server/boards.ts`:**
   - each item's place, from `layout` or from the grid (item 3);
   - each line's two ends, only between items in the route's `nodes`;
   - the `viewBox`;
   - the 500 cut-off.

   It is pure, with its own tests.
3. **The SVG partial in `tree-govuk/`,** included in `boards.njk` above the tables. Labels by text content (escaped),
   classes for drawn and loaded, and no `style` attribute.
4. **The classes in the GOV.UK stylesheet on `var(--warning)`**, as the React board's are. `colour_drift_check` and
   `design-check` stay green.
5. **A browser policy spec for the board page in `test/csp/`**, Chromium and WebKit.
6. Move `layout` from left to drawn in the census and in BD. Run the checks and every plant.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/board-picture.test.ts` (new; vitest: the view model and the rendered SVG) and
`OspreyFlow_Core/apps/pages/test/csp/board-picture.spec.ts` (new; Playwright, both browsers), with the boards scenario
test `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` extended with BD's picture rows. All are red on
main.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | A board of three drawn items and two loaded, with links | an SVG with five items at their `layout` places and the lines between them; drawn ones by the drawn class | a drawn item given the loaded class |
| 2 | An item the reader may not see | absent from the picture as from the tables; no gap, no line ending in space | a line drawn to an end outside the route's `nodes` |
| 3 | Labels | each by text content, escaped; a label of `<script>` drawn as text | the label written as markup |
| 4 | No inline style | the rendered page has no `style` attribute; the policy spec reports no violation in either browser | a `style="…"` on a line |
| 5 | Colours | every colour and dash by class on a token (`colour_drift_check`, `design-check`) | a hex value in the stylesheet |
| 6 | A board made with loaded references and no layout | the references on the grid, below the stored places; nothing written | a `PUT .../layout` sent on render |
| 7 | 501 items | the sentence, no picture, the tables whole | the first 500 drawn |
| 8 | Scripts off | the picture present and the tables whole (I4) | the picture drawn only by a module |
| 9 | The picture's name | `role="img"` with item 2's name; no item in the tab order | an item given `tabindex="0"` |
| 10 | Two readers of different clearance | each picture holds only the items and lines the route sent that reader | the view model reading the layout's keys rather than the route's `nodes` |
| 11 | No internal id | no node id in the SVG (no `id=`, `data-id` or title holding one) | an id written as the element's `id` |
| 12 | The census | `layout` named as drawn, in the page's `CENSUS` and in BD | `layout` drawn and still listed as left out |

## Checks

GG4f1's row's checks, with `test_route_pins.py` and `test_page_lists_merge.py` (as GA1a's refreeze adds) and `make -C
OspreyFlow_Build design-check` in the merge's full gate.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario BD's picture rows, after BD31** (the last row, :1008), numbered on from
BD32. Whichever of this part and GG4f1 merges second renumbers its rows (rule 5's shared list).

## Out of scope

- moving items and the link handle (GG4e2);
- I7's coverage test in the page service (GG4e2);
- pictures on items, matches and promotion (GG4f);
- drawn items on the canvas (GG2g4);
- any token change;
- any Conduit change;
- `apps/workspace`;
- the Default tree.

## Proposed `slices.tsv` row (not added)

```
GG4e1	GG4	A board drawn as a picture on its GOV.UK page: server-rendered SVG from layout (unplaced loaded references on a grid, nothing written), drawn items dashed by class on var(--warning) as the React board, role img with the tables kept as the content, not drawn past 500 items; no script, no inline style (the owner's standing (a), D274; draft drafts_2026-11-28)	GG4c,GG4b,GG4j	2	lane/slice-GG4e1	full	OspreyFlow_Core/apps/pages/test/govuk/board-picture.test.ts,OspreyFlow_Core/apps/pages/test/csp/board-picture.spec.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/board-picture.test.ts && npm run test:csp --workspace apps/pages -- board-picture.spec.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4e1 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4e1 uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG4e1 uv run --frozen ruff check .
```
