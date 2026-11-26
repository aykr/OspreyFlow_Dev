# Slice GG2d · GG2 · The Matrix on the GOV.UK pages: a graph's entities and links as two tables, server-rendered and paged for scripts off, an ARIA grid when scripts run, first on a saved view (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** The scouts' cut of 20 November: "GG2d plain case list and Matrix tables"
(`slices/STAGE4_SCOUTS_2026-11-20.md:86-88`), "the Matrix (two ARIA grids) is mandatory as the textual alternative". The
case list became GR1's (the owner's ruling on GR1a's draft, 25 November: "GR1 owns the case list"), so **GG2d is the
Matrix alone.** GG2b (drafted 25 November) shows a saved view with "the graph as tables" behind a details element
"until GG2d's Matrix replaces them". **Open since GG4a's draft (question 0): the plan's GG4 row also names the Matrix
("Graph extras, drawing boards, Matrix, Ownership, …").** Question 0 below asks it.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The specification** (`OspreyFlow_Build/spec/02_GLASS_FRONTEND.md` about lines 2337 to 2345): the Matrix is "the
  screen-reader-navigable rendering of the same data … Two HTML tables over the working set's own graph — **no request of
  its own**, so nothing the reader may not see can reach it (rule 3) and it carries no count but the rows it shows (rule
  7)": *Entities* (Name as the row header, Type, Marking, Provenance in words, Links in view, *Expand*, *Show*) and
  *Links* (the type's label, From, To, …).
- **The React Matrix.** `apps/workspace/src/matrix/MatrixView.tsx` (610 lines): each table an ARIA grid (one Tab stop,
  arrows, Home and End, Ctrl+Home and Ctrl+End, Page Up and Down), Enter selects, Space adds to the selection; "a long
  view is paged (rule 2: the caption says 'Rows 101 to 200 of 12,481', never a silent cut); a page is a hundred rows"
  (header :1-16). **It does make two requests**: `fetchConnectionStrengths` and `fetchRarity` (:407-425), for ADR-139
  decision 6's sort "by connection strength and by its ends' rarity" (`MATRIX_ACTIONS`' last id). **So `spec/02`'s "no
  request of its own" is out of date** (rule 11: a spec correction in this slice). The routes are
  `POST .../connection-strength` (`services/api/app.py:16122-16125`) and `POST .../rarity` (:16144-16147). **Neither is
  audited, and both compute over the case's working set** (`working_set.current_membership`): "a link named that is not
  in the working set … is left out" (`services/api/connection_strength.py:82-90`, :115-122).
- **The rows' logic.** `apps/workspace/src/matrix/matrixRows.ts` (183 lines), plain TypeScript, "read from the working
  set's own graph and nothing else", `PAGE_SIZE = 100` (:15). It imports `nodeLabel` from
  `apps/workspace/src/canvas/nodeAttributes.ts:100-103`, which uses `labelChoices.ts`'s `chosenLabel` and `defaultLabel`
  (the analyst's own label choice first, ADR-076). **Neither is in `glass-shared` yet**, so a page cannot import them
  (I5: no tree imports the workspace).
- **The keyboard.** `MATRIX_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:1337-1351`, 12 ids), proven
  by `apps/workspace/keyboard/matrix.spec.ts:239`. Of the 12, four belong to a canvas (`selection-carried-to-the-canvas`,
  `canvas-selection-carried-to-the-matrix`, `expand-from-a-row-by-keyboard`, `show-a-row-on-the-graph-by-keyboard`).
- **The data on a page.** GG2b's saved view: `CaseViewOpened`'s `nodes` and `edges` (`packages/schemas/case_views.py`),
  read once by the server.

## Acceptance (red before, green after)

The workspace's own `MatrixView` tests and `matrix.spec.ts`, unchanged and green after `matrixRows.ts` moves (I11);
GV's Matrix rows (GG2b's scenario, extended), written first, and `apps/pages/test/govuk/view-matrix.test.ts`, red on
GG2b's page, green after.

## Questions for the owner (the proposal first)

0. **Whose is the Matrix.** (a) **GG2d's**: it is the canvas's textual alternative (`spec/02`), needed on the first page
   that draws a graph (GG2b), not an R6 extra; GG4h keeps Ownership alone. (b) GG4's, as the plan's row reads; GG2b then
   keeps its plain tables until GG4.
1. **The move first.** (a) **`matrixRows.ts`, `nodeAttributes.ts`'s `nodeLabel` and `labelChoices.ts`'s label
   functions move to `glass-shared` in this slice's first round, behaviour-preserving (I11)**, if they import nothing
   version-bound; if `nodeAttributes.ts` cannot move whole (it is Sigma's display pipeline), only the label functions
   move. (b) The page writes its own rows. **Not proposed:** two Matrices that can disagree.
2. **The analyst's own label choice** (ADR-076). It is "kept in this browser only, never sent to the server"
   (`apps/workspace/src/canvas/labelChoices.ts:7-8`, :38). (a) **The server-rendered table uses the default label and the module, when it runs, redraws the names
   with the reader's own choice. (b) The default label always.
3. **Scripts off.** (a) **Both tables server-rendered, 100 rows a page by `?page=`, the caption saying "Rows 101 to 200
   of 4,213" from the rows the route sent, sorting by a column a link** (`?sort=`); every row reachable. (b) The first
   page only. **Not proposed** (rule 2).
4. **Scripts on.** (a) **A module turns each table into an ARIA grid with the workspace's keys**, reading the same
   markup (decision 3: one delegated listener, `data-action` and `data-id`), and the canvas-bound ids wait for GG2e.
   (b) The tables stay plain.
5. **Strength and rarity.** Both routes compute over the case's working set, not over a saved view, so a view's link
   outside the working set gets no figure. (a) **Left out of GG2d on a saved view**, said as "Sorting by connection
   strength is offered on the live graph"; offered on GG2e's live working set, where the two routes answer for the
   links shown. (b) Offered on a view, with links outside the working set said as "no figure". **The owner's, since a
   view's figures would then depend on what the case's working set holds at that moment.**
6. **The spec correction.** (a) **`spec/02`'s "no request of its own" corrected to name the two routes and why**, with
   ADR-139 decision 6 cited. (b) Your words.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | `matrixRows.ts` moved (round 1) | the workspace's Matrix tests and `matrix.spec.ts` green, unchanged | a relative import left behind (two copies) |
| 2 | A view of 40 nodes and 60 links, scripts off | two tables with the workspace's columns, Name as row header, provenance in words | an inferred node said "confirmed" (rule 5) |
| 3 | 4,213 nodes | "Rows 1 to 100 of 4,213", page links, every row reachable | 100 rows and no caption |
| 4 | Sort by type | `?sort=type`, the whole set sorted then paged | the page's 100 rows sorted alone |
| 5 | A marking above the reader | absent, and not counted (the route never sends it) | a count from another field |
| 6 | Scripts on: the grid's keys | one Tab stop; arrows, Home, End, Page Up and Down as the workspace's | a cell left in the tab order |
| 7 | `assertAllCovered` for the GOV.UK tree over the ids offered | green, the four canvas-bound ids listed as GG2e's | an offered id with no case |
| 8 | Strength refused or silent | the sort absent; the sentence | an empty strength column sorted as zeros |
| 9 | Strength on a saved view (question 5 (a)) | no strength sort; the sentence | the sort offered over figures the routes give only for the working set |
| 10 | No internal id | no node or link id in the HTML outside a link's own path; a node with no name, title, value or identifier is said as its type ("a Person with no name"), since `labelChoices.ts`'s last fallback is the id (:96-98) | the moved label function's id fallback left in the page's path |
| 11 | I1, I13 | no React; nothing version-bound in `glass-shared` | a planted `import "sigma"` in the moved file |

## Files touched

`packages/glass-shared/src/matrix/matrixRows.ts` (moved), the label functions (moved), `src/index.ts`;
`apps/workspace/src/matrix/MatrixView.tsx` and `canvas/nodeAttributes.ts` (imports); `apps/pages/server/` (GG2b's view
page), `tree-govuk/` (the Matrix partial), `apps/pages/modules/matrix.ts`; `spec/02` (the correction), `spec/08` (GV's
Matrix rows); the tests above.

## Checks (frozen when cut)

GG2b's list (with I11's before-and-after for the move), and the workspace's whole suite.

## Out of scope

The four canvas-bound actions (GG2e); Ownership (GG4h); the Matrix over the live working set (GG2e); `apps/workspace`
beyond the imports.
