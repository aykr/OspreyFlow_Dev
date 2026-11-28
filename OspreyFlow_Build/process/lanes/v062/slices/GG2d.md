# Slice GG2d · GG2 · The Matrix on GG2b's saved-view page: the view's entities and links as two tables, server-rendered and paged for scripts off, an ARIA grid when scripts run

- **Build id:** GG2 (the owner, 26 November about 10:35 UTC: "**The Matrix is GG2d's**"; the `matrix-ownership` row of
  `apps/pages/FUNCTIONS.yaml:268-274`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GG2b (the view page it replaces the tables on). **Its merge waits for WS4b** (decision 9,
  `spec/06_DECISIONS.md:41101-41102`); it may be written meanwhile.
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. **One question is the owner's: O2** (sorting a saved view's links by strength and rarity). It does not
  stop the start. The merge waits for it.

## What

On GG2b's page, `/cases/views?case=<id>&view=<id>`, the Matrix takes the place of GG2b's "The graph as tables". It
has two tables over the view's own answer, *Entities* and *Links*, with the columns `spec/02` names
(`OspreyFlow_Build/spec/02_GLASS_FRONTEND.md:2337-2346`):
- **Entities:** Name as the row header; Type; its own Marking; Provenance in words, so an inferred node reads
  "Inferred" (rule 5); Links in view.
- **Links:** the type's label as the row header; From; To; Marking; Provenance.

*Expand* and *Show on the graph* are left out of the scope (GG2f and GG2e2). With scripts off, both tables are
server-rendered and paged. With scripts on, a module makes each an ARIA grid with the workspace's keys. GOV.UK page
only.

**The answers (each (a), and why):**

0. **Ruled: GG2d's** (the owner, 26 November).
1. **(a) The move first, behaviour unchanged (I11).**
   - `apps/workspace/src/matrix/matrixRows.ts` (183 lines) and its test `matrixRows.test.ts` move to
     `packages/glass-shared/src/matrix/`. The label becomes a parameter: `entityRows(graph, label, dimmed)`. Today it
     imports `nodeLabel` from `canvas/nodeAttributes.ts:10`, a file that also imports `iconChoices`.
   - `defaultLabel`, a plain function with no storage (`apps/workspace/src/canvas/labelChoices.ts:103-121`), moves to
     `glass-shared` with `asText` and `IDENTIFYING`. `labelChoices.ts` re-exports it.
   - `labelChoices.ts` itself (the browser's own choice, kept in `localStorage`, :13, :38), `nodeAttributes.ts` and
     `nodeLabel.ts` stay in the workspace.
   - Why (a): one Matrix's rows, never two that can disagree. Moving the plain function alone keeps the owner's slice-E
     answer 4 ("labelChoices and iconChoices stay", 22 November, file 013) and its answer 1 ("the other plain files move
     when a slice needs them"). See *Readings for the conductor* in `INDEX.md`.
2. **(a) The server-rendered table uses the default label.** The module, when it runs, redraws a name with the
   reader's own choice, if this browser holds one. Why (a): the choice is "kept in this browser only, never sent to the
   server" (`labelChoices.ts:7-8`).
3. **(a) Scripts off, every row reachable.**
   - 100 rows a page (`PAGE_SIZE`, `matrixRows.ts:16`) by `?entities=<n>` and `?links=<n>`.
   - The caption is "Rows 101 to 200 of 4,213", from the rows the route sent.
   - A column is sorted by a link (`?sort=<column>&order=<ascending|descending>`): the whole set is sorted, then paged.
   - Why (a): rule 2.
4. **(a) Scripts on, a module (`apps/pages/modules/matrix.ts`) turns each table into an ARIA grid** with the
   workspace's keys: one Tab stop; arrows, Home and End, Ctrl+Home and Ctrl+End, Page Up and Down; Enter selects;
   Space adds to the selection. It reads the same markup, with one delegated listener on `data-action` and `data-id`
   (ADR-152 decision 3). It imports no drawing library. It offers these `MATRIX_ACTIONS` ids
   (`packages/glass-shared/src/keyboard/actionRegistry.ts:1337-1351`):
   - `reach-the-matrix-view-by-keyboard`, a skip link to the Matrix heading;
   - `move-between-cells-by-keyboard`;
   - `select-a-row-by-keyboard` and `add-a-row-to-the-selection-by-keyboard`;
   - `sort-a-column-by-keyboard`;
   - `turn-the-page-by-keyboard`;
   - `select-a-link-row-by-keyboard`.

   The four that need the live canvas go to GG2e2: `selection-carried-to-the-canvas`,
   `canvas-selection-carried-to-the-matrix`, `expand-from-a-row-by-keyboard` and `show-a-row-on-the-graph-by-keyboard`.
   Why (a): the page's own markup stays the one source, and scripts only add keys.
5. **The strength and rarity sort: the owner's (O2).** ADR-139 decision 6 says "The Matrix view can sort by both"
   (`spec/06_DECISIONS.md:22653`), and `MATRIX_ACTIONS`' last id is
   `sort-links-by-strength-and-rarity-by-keyboard`. But both routes compute over **the case's working set**, not over
   a saved view:
   - `POST .../connection-strength` (`services/api/app.py:16132-16135`) and `POST .../rarity` (:16154-16157);
   - "a link named that is not in the working set … is left out" (`services/api/connection_strength.py:82-84`);
   - rarity gives "no score (None)" outside it (:115-122).

   On a saved view, the figures would depend on what the case's working set holds that minute. **Proposed (a) for the
   owner:** left out on a saved view, said as "Sorting links by connection strength is offered on the live graph", and
   offered on GG2e2's live Matrix. Until he answers, the builder builds without the sort. If he rules (b), offer it on
   a view with "no figure" for links outside the working set, in one more round.
6. **(a) `spec/02`'s "no request of its own" corrected** (`spec/02_GLASS_FRONTEND.md:2341`; rule 11).
   - The React Matrix makes two requests: `fetchConnectionStrengths` and `fetchRarity`
     (`apps/workspace/src/matrix/MatrixView.tsx:407`, :419), for ADR-139 decision 6.
   - The sentence is corrected to name the two routes, why they are made, and that they answer only for links the
     reader may see in the working set.
   - On a saved view the page makes no request beyond GG2b's one read.
   - A spec sentence, not a decision record. Why (a): the spec must say what the code does.
7. **(a) A node with no name, title, value or identifier is said as its type**, for example "A Person with no name".
   It is never its id, though `defaultLabel`'s last fallback is `node.id` (`labelChoices.ts:120`). The workspace's own
   fallback is unchanged (I11). Why (a): rule 7, no internal id on the page.

## What exists today (re-read at `b79164850`)

- `MatrixView.tsx` is 610 lines. Its header (:1-16) says: "Rows 101 to 200 of 12,481", "a page is a hundred rows".
- `matrixRows.ts` exports `entityRows`, `linkRows`, `provenanceText`, `sortRows`, `pageOf` and `pageContaining`. It
  imports `ProvenanceState` from `packages/schemas/generated/Node` by a relative path (:9), and `linkTypeName` from
  `glass-shared` (:11).
- The keyboard proof in the workspace is `apps/workspace/keyboard/matrix.spec.ts`, with `assertAllCovered` at :238-239.
- `matrix-ownership` (`FUNCTIONS.yaml:268-274`): slice R6, no scenario ("C5 … is proposed, not owner-ruled; the
  Matrix has none"). GG4h (cut 27 November) narrows it to the Matrix and gives Ownership a row of its own. Whichever
  merges second takes both sides.
- GG2b's page (this line's brief) is the host. No Matrix code is in `apps/pages` or `glass-shared` today.

## Round 1's steps

1. Write GV's Matrix rows in `spec/08` and the acceptance test files first. Show them red on GG2b's page: no Matrix,
   only the plain tables.
2. **The move (item 1), as its own commit.**
   - The workspace's `MatrixView.test.tsx`, `MatrixView.budget.test.tsx`, `matrixRows.test.ts` (moved),
     `labelChoices.test.ts` and `keyboard/matrix.spec.ts` stay green, unchanged but for import lines.
   - `deltaClientHome.test.ts`'s pattern holds the new homes: no copy, no relative import left in the workspace.
3. Build the server half: the Matrix partial in `tree-govuk/`, `server/views/matrixWords.ts`, and GG2b's
   `savedView.ts` passing the paged and sorted rows. The `details` tables go.
4. Build `modules/matrix.ts` (a plain page module; `buildAssets` bundles `.ts` files directly in `modules/`,
   `scripts/assets.mjs:13`, :209-215) and its keyboard spec, with `assertAllCovered` over the offered ids.
5. Correct `spec/02` (item 6). Fill in `matrix-ownership`'s slice ("GG2d") and scenario ids.
6. Run the checks and every plant.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/view-matrix.test.ts` (new) and the GV scenario test
`OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py` (GG2b's, extended with the Matrix rows). Both are
red on main, which has no view page and no Matrix. The browser cases are in `keyboard/view-matrix.spec.ts` and
`scripts-off/saved-view.spec.ts` (GG2b's, extended).

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | The move (round 1's first commit) | the workspace's Matrix tests and `matrix.spec.ts` green, unchanged but for imports; one home for each moved function | a relative import of the old path left behind (two copies) |
| 2 | A view of 40 nodes and 60 links, scripts off | two tables with `spec/02`'s columns, Name as the row header, provenance in words | an inferred node said "Confirmed" (rule 5) |
| 3 | 4,213 nodes | "Rows 1 to 100 of 4,213", page links, every row reachable | 100 rows and no caption (rule 2) |
| 4 | Sort by Type | `?sort=type`: the whole set sorted, then paged | the page's 100 rows sorted alone |
| 5 | A node above the reader's clearance (the route never sends it) | absent and not counted; its links absent | a count read from another field than the rows |
| 6 | Scripts on: the grid's keys | one Tab stop; arrows, Home, End, Page Up and Down as the workspace has them | a cell left in the tab order |
| 7 | `assertAllCovered` over the offered ids | green; the four canvas-bound ids and the strength sort listed as not offered, each naming its slice (GG2e2) | an offered id with no case |
| 8 | Strength on a saved view (O2 (a)) | no strength sort; the sentence; no request to either route | a request to `connection-strength` from the view page |
| 9 | A node with no name or identifier | "A Person with no name", never its id | the moved `defaultLabel`'s id fallback reaching the page |
| 10 | The reader's own label choice, scripts on | the module redraws that type's names with the choice; scripts off shows the default | the server reading a choice it was never sent |
| 11 | No internal id | no node or link id in the HTML outside a link's query | an id printed in a cell |
| 12 | I1, I13 | no React; nothing version-bound in `glass-shared` | a planted `import "sigma"` in the moved file |

## Checks

GG2b's row's checks. Also `npm test --workspace packages/glass-shared` and `npm test --workspace apps/workspace`
(the move, I11).

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario GV's Matrix rows, after GG2b's rows** in GV. GV itself sits after
Scenario AQ.

## Out of scope

- the four canvas-bound ids and the live Matrix (GG2e2);
- *Expand* from a row (GG2f1);
- Ownership (GG4h);
- `apps/workspace` beyond import lines;
- any Conduit change;
- the Default tree.

**Stop and ask** if `matrixRows.ts` cannot take its label as a parameter without changing the workspace's behaviour.

## Proposed `slices.tsv` row (not added)

```
GG2d	GG2	The Matrix on GG2b's saved-view page: entities and links as two server-rendered tables, paged and sorted by link for scripts off, an ARIA grid with the workspace's keys when scripts run; matrixRows and defaultLabel moved to glass-shared (I11); spec/02's "no request of its own" corrected; merges after WS4b; WAITS FOR THE OWNER before its merge: O2, the strength and rarity sort on a saved view (the owner's standing (a), D274; draft drafts_2026-11-28)	GG2b	2	lane/slice-GG2d	full	OspreyFlow_Core/apps/pages/test/govuk/view-matrix.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/view-matrix.test.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm test --workspace packages/glass-shared && npm test --workspace apps/workspace && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && node scripts/version_isolation_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_saved_view_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/glass_trees/test_version_isolation_check.py ../OspreyFlow_Build/tests/glass_trees/test_glass_shared_plain_logic.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GG2d uv run --frozen ruff check .
```
