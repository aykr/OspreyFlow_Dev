# Slice GG4e · GG4 · The board drawn as a picture: server-rendered SVG from the board's layout for scripts off, and a board module that moves items by pointer and by arrow keys (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **Size L: proposed as two slices,
GG4e1 (the picture, no script) and GG4e2 (the module: move by pointer and by keys, and the link handle).**

**Where it comes from.** ADR-152 decision 6 keeps a "drawing board" among the interactive modules held once in
`apps/pages/modules` (`spec/06_DECISIONS.md` about lines 41024 to 41071). ADR-143 C6 and C7 (about 26564 to 26569): a
board is drawn, items move by dragging, links by the handle; decision 4: drawn items are "drawn dashed in amber
everywhere they appear". GG4a's draft question 1 (b) offered "the board drawn as plain positioned SVG from `layout`
(classes only, no inline style)"; the owner ruled tables first. **The board draws with no library** (`BoardEditor.tsx`
imports no Sigma: GG4a's draft, `apps/workspace/src/boards/BoardEditor.tsx:11-49`), so decision 9's hold does not reach it.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The layout.** `BoardOpened.layout` is `{node id: {x, y}}` for the items the reader may see
  (`services/api/boards.py:444`: `if k in set(shown)`), so the picture draws only what the route sent. Moving is
  `PUT .../boards/{board_id}/layout` (`app.py:5179-5193`), 204, `BoardMove` (`packages/schemas/boards.py:193-198`:
  `positions`, up to 10,000), creator only (`own_board`), "the board's own layout, not data". Not audited.
- **The policy.** Decision 8 (about 41083 to 41089): no inline `style` attribute, no `unsafe-inline`. Decision 3 (about
  40997 to 41003): DOM built with `textContent`, one delegated listener reading `data-action` and `data-id`, a
  latest-answer-wins guard, "a CSSOM write is allowed only through a named helper the pattern note lists".
  **No such helper or pattern note exists yet** (`packages/glass-shared/src` has none; `layout/panelFrameStore.ts:521-537`
  holds `findInlineStyle`, the check that no panel code sets a style). **SVG geometry needs none:** `x`, `y`,
  `transform` and `viewBox` are attributes, not styles, so a server can write them in the markup and a module can set
  them with `setAttribute`.
- **Modules.** `apps/pages/modules/` holds `studio-frame.ts` only; `scripts/assets.mjs` bundles each `.ts` directly in
  `modules/` to one hashed ES module (:13, :209-222) and refuses a drawing library outside its allow-list (:31-33,
  :182-184). The board module imports none.
- **Keyboard.** `BOARD_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:517-544`, 25 ids), among them
  `move-an-item-by-the-arrow-keys`, `draw-a-link-from-the-selected-item-by-keyboard`, `inspect-an-item-by-keyboard`.
  **No `assertAllCovered` runs over `apps/pages/test`** (a search finds none), so I7's "per tree's keyboard folder" has no
  test in the page service yet.
- **The colours.** `packages/design/tokens.css` is authoritative (CLAUDE.md); the drawn amber must be a token, never a
  literal.

## Acceptance (red before, green after)

**GG4e1:** BD's picture rows, written first, and `apps/pages/test/govuk/board-picture.test.ts`, red on GG4d's page (no
picture), green after; `findInlineStyle` and the CSP spec over the page green. **GG4e2:** the module's keyboard and
pointer cases, and I7's coverage test for the GOV.UK tree, each red first.

## Questions for the owner (the proposal first)

1. **The split.** (a) **GG4e1: the picture, server-rendered SVG, no script**: items at their `layout` places, links as
   lines, drawn items dashed in the drawn token's colour by class, loaded items plain; GG4a's tables stay below it as the
   text alternative. **GG4e2: the module**: move by pointer and by arrow keys, and the link handle. (b) One slice.
2. **The picture's role for a screen reader.** (a) **`role="img"` with a short name ("A picture of the board; the same
   items and links are in the tables below")**, the items not focusable while no script runs; the tables carry the
   content (as the GR3a chart rule). With the module, each item becomes focusable to move it. (b) Every item focusable
   in the picture as well, with scripts off: they would do nothing.
3. **Items with no place in `layout`.** A drawn item always has one: `declare` writes its place, at 0, 0 when none is
   given (`services/api/boards.py:548-551`), and a place at 0, 0 is a stored place (GG4d's question 3 avoids it). **The
   items with no place are a board's loaded references** from `make()` (:396-399; saving the board writes no layout).
   (a) **The server places the loaded references on GG4d's grid in the picture only**, without writing a layout, and
   says nothing about it. (b) All at the origin.
4. **The picture's size.** (a) **A `viewBox` fitted to the places, with a margin, and a fixed largest size in CSS by
   class**; past 500 items (a stated figure, measured in the slice), the picture is not drawn and a sentence says the
   board is too large to draw here and the tables hold it all (never a part of the board: rule 2). (b) No limit.
5. **Moving by keys (GG4e2).** (a) **Arrow keys move the focused item by 8 units, Shift + arrow by 40; each move is sent
   as one `PUT .../layout` with that item alone, after the keys stop for 400 ms**, through the `/v1` forwarder with
   `X-CSRF-Token`; a refused or failed move puts the item back and says so in a live region. (b) A send per key press.
6. **The link handle (GG4e2).** (a) **Dropping the handle on another item opens GG4d's *Draw a link* form with both ends
   filled**: no new write path, so the form stays the one place that checks a link. (b) The module posts the link itself.
7. **I7 in the page service.** (a) **GG4e2 adds `assertAllCovered` for the GOV.UK tree over the board ids it offers,
   with a list, in the test, of the `BOARD_ACTIONS` ids the tree does not yet offer, each naming the slice that will**
   (GG4f for pictures, matches and promotion; GG4c's question 1 for boards from a view or a selection; a later GG4
   slice for `start-a-drawing-with-no-case-by-keyboard`; GG4d after GG4b for
   `declare-an-item-with-a-source-document-by-keyboard`; and **no slice yet** for `choose-an-items-icon-by-keyboard`,
   `inspect-an-item-by-keyboard` and `inspect-an-item-from-its-menu-by-keyboard`, `actionRegistry.ts:524-527`, :539,
   which the list names as unowned), so an id can
   leave the list only by gaining a case. (b) Coverage of every id at once: not possible until GG4f.
8. **The CSSOM helper.** (a) **None needed: geometry is attributes.** If GG4e2 finds a style it must set (a cursor
   during drag, say), it is a class, never a style. (b) Write decision 3's pattern note and its helper here.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A board of three drawn items and two loaded, with links (GG4e1) | an SVG with five items at their `layout` places and the links between them; drawn ones by the drawn class | a drawn item drawn with the loaded class |
| 2 | An item the reader may not see | absent from the picture as from the tables; no gap, no line ending in space | a line drawn to an end outside the route's `nodes` |
| 3 | Labels | each by text content, escaped; a label of `<script>` drawn as text | the label written as markup |
| 4 | No inline style | `findInlineStyle` over the templates and the module finds none; the CSP spec reports no violation | a `style="…"` on a line |
| 5 | Colours | every colour from a token by class (`colour_drift_check`, design-check) | a hex value in the stylesheet |
| 6 | A board made with loaded references and no layout (question 3 (a)) | the references drawn on the grid, nothing written | a `PUT .../layout` sent on render |
| 7 | 501 items (question 4 (a)) | the sentence, no picture, the tables whole | the first 500 drawn |
| 8 | Scripts off | the picture present and the tables whole (I4) | the picture drawn only by the module |
| 9 | Move by arrow keys (GG4e2) | one `PUT` with the item's new place after the pause; the picture and the stored place agree on reload | a `PUT` per key press |
| 10 | Move by pointer | the same as 9 | the move sent before the drop |
| 11 | A refused move (the route's own refusals: 404 for a board deleted meanwhile, 403 for the rights or the creator; `boards.move` itself refuses nothing, `boards.py:626-640`), or no answer | the item back where it was; the live region says the move was not kept | the item left at the new place |
| 12 | Two moves in quick succession | one `PUT` in flight at a time, the second sent after the first's answer, so the stored place is the last move (the store merges in arrival order, `case_views.py:216`) | two `PUT`s in flight at once |
| 13 | The handle dropped on an item | GG4d's form with both ends filled; nothing sent until it is submitted | the link posted by the module |
| 14 | A non-creator | no handle, no move; items not focusable for moving | the module attached to a board with `may_draw` false |
| 15 | I7 for the GOV.UK tree | `assertAllCovered` green with the offered ids; red with one offered id's case removed | an offered id with no case |

## Files touched

`spec/08` (BD's picture and moving rows); `apps/pages/tree-govuk/boards.njk` and a picture partial;
`apps/pages/server/boards.ts` (the picture's view model: places, grid, `viewBox`); `apps/pages/modules/board.ts` (GG4e2);
the GOV.UK stylesheet (classes on tokens); `packages/design/tokens.css` only if no drawn-amber token exists (**a token
change is design-check's and the owner's**); `test/govuk/board-picture.test.ts`, `keyboard/board-module.spec.ts`,
`scripts-off/boards.spec.ts`, a coverage test for I7; the scenario test.

## Checks (frozen when cut)

GG4c's list, plus the GOV.UK CSP spec over the board page (I2, I3, Chromium and WebKit), `colour_drift_check`,
`node scripts/no_react_check.mjs`, and `apps/pages/scripts/assets.mjs`'s own tests (a new module).

## Out of scope

Pictures on items, matches, promotion (GG4f); the canvas's dashed display of drawn items (GG2g); any Conduit change;
`apps/workspace`.
