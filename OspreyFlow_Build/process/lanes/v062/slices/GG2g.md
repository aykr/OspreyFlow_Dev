# Slice GG2g · GG2 · The canvas's editing actions on the GOV.UK live graph: select, open and hide links, drag, remove, find groups, mark for suppression, and drawn items shown dashed and read-only (a draft; size L, proposed as GG2g1 to GG2g4)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GG2a`. No row in `slices.tsv`; no builder
starts from this paper. **Size L, split by action group into four parts (question 1), each with its own table below.**
**Every part draws with Sigma 4, so by decision 9 it merges only after WS4b** (`spec/06_DECISIONS.md` about lines 41091
to 41102).

**Where it comes from.** The `graph-canvas` row of `apps/pages/FUNCTIONS.yaml` (:190-196: "select, open links, drag,
remove, find groups, mark for suppression"; scenarios A9, A10, B5, B7, B15); the plan's row GG2g ("each with its
keyboard case, and drawn items shown dashed and read-only (ADR-143 C15)"); rule 13 (a keyboard case per action); GG2e's
question 4 (`assertAllCovered` names the rest of `CANVAS_ACTIONS` as GG2f's and GG2g's). It builds on GG2e (the live
page `/cases/graph?case=…`, its read-only actions) and GG2f1 (the node's menu and the forwarder calls).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The keyboard ids** (`packages/glass-shared/src/keyboard/actionRegistry.ts:87-203`) not taken by GG2e or GG2f1:
  selection `space-toggle-ring-membership` (:111), `ctrl-arrow-cycles-ring` (:99), the selection's menu (:157-162:
  `menu-opens-on-the-context-menu-key`, `menu-opens-on-shift-f10`, `menu-arrows-home-and-end-move-through-it`,
  `menu-offers-the-selections-actions-in-the-bars-words`, `menu-folds-types-with-no-links-and-opens-them-in-place`);
  links `delete-hides-selected-link` (:172), `show-hidden-links-by-keyboard` (:173); saving
  `save-selected-as-a-view-from-the-selection-bar` and `…-from-a-selected-nodes-menu` (:152-153); moving
  `move-the-selection-with-shift-and-arrows` (:96), `show-previous-positions-by-keyboard` (:93), `grid-toggles-by-keyboard`
  (:94), the layouts (:168-170); removing `delete-removes-selected-nodes` (:148), `clear-view-by-keyboard` (:149); groups
  `communities-button-by-keyboard`, `g-folds-and-opens-the-focused-nodes-group`, `box-fold-button-by-keyboard`,
  `collapse-all-and-expand-all-by-keyboard` (:187-190); suppression `menu-item-mark-for-suppression` (:123). **Not
  `graph-canvas` functions, and so not proposed here** (question 6): `menu-item-manual-link`, `menu-item-manual-split`,
  `menu-item-explain-cluster`, `overlay-dismiss-cluster-explain`, the pathfinder's four (:115-137),
  `menu-item-view-messages`, `menu-item-set-picture`, `icons-menu-by-keyboard`, `icon-picture-from-file`, the labels and
  value-icon ids, `match-strictness-by-keyboard`, the timeline's `select-what-is-lit…` pair (:162-167).
- **Plain logic already in `glass-shared/src/canvas/`:** `nodeDrag.ts`, `removeNodes.ts`, `edgeSelection.ts`,
  `linksAmong.ts`, `forceLayout.ts`, `layoutModes.ts`, `settledAnchor.ts`, `communityLinks.ts`, `provenancePatterns.ts`.
  **Still React-side:** the community finder (`apps/workspace/src/canvas/communities.ts`, 264 lines; its Web Worker
  `communityWorker.ts`; `graphology-communities-louvain` is a dependency of the workspace alone,
  `apps/workspace/package.json:32`).
- **The page's policy already admits a same-origin worker:** `"worker-src": ["'self'"]`
  (`apps/pages/server/headers.ts:40`). No change to `headers.ts` is needed for the groups worker.
- **The routes** (`services/api/app.py`): `DELETE .../nodes` (:5887-5918), `INVESTIGATE` and **Editor**, "remove from
  the working set (not from the Vault)", answers `{seq}`, history `REMOVED`. `POST .../views` (:4803-4825), `INVESTIGATE`
  and the **Viewer** gate, `CaseViewInput` with `node_ids` (at most 10,000, `packages/schemas/case_views.py`). The
  suppression mark: `GET .../suppression-marks` (:6348 onward, Viewer, the marks on the reader's own projection only),
  `POST` and `DELETE .../nodes/{node_id}/suppression-mark` (:6379 and :6414 onward, **`EDIT_GRAPH`** and Editor), a node
  not visible answering **404 `node_not_found`**, "not 403" (:6437-6440). `spec/02` §9.5 (:2487 onward): the reason box,
  "Why should it be suppressed? (required, kept with the mark)", *Mark for suppression (hides nothing yet)*, 1,000
  characters, trimmed, Escape writes nothing.
- **Drawn items** (ADR-143 C15, `spec/06` :26594): "Drawn items show on the case's analysis canvas, dashed and read-only,
  with *Edit on board*." The React canvas dashes a drawn link (`apps/workspace/src/canvas/nodeAttributes.ts:471-479`).
  **No *Edit on board* exists in the React workspace.** A drawn element's `provenance.drawn.board_id` is **kept for its
  author alone and sent empty to everyone else** (`packages/ontology/handling.py:385-398`).

## Acceptance (red before, green after)

For each part, Scenario **GW**'s rows for that part, written first, and its Playwright spec in
`apps/pages/test/govuk/` (named below), red on the previous part's page, green after; the earlier rows unchanged and
green; `assertAllCovered("CANVAS_ACTIONS", …)` over the page's offered ids green at each part's end.

## Questions for the owner (the proposal first)

1. **The split.** (a) **Four parts, one merge each:** GG2g1 the selection, its menu, links hidden and shown, saving the
   selection as a view; GG2g2 dragging, the layouts, removing and clearing; GG2g3 finding and folding groups; GG2g4 the
   suppression mark and drawn items dashed and read-only. Each is M or S. (b) Three: GG2g3 folded into GG2g2.
2. **Pointer and keyboard as one action.** (a) **Every pointer gesture the part offers has its keyboard id, proved
   end to end in the page's keyboard folder** (rule 13), and lasso stays exempt as the registry says (:80-85). (b) Your
   words.
3. **Positions** (GG2g2). The React canvas keeps positions in the browser, not on the server. (a) **The same on the
   page: a drag or a layout moves the node for this reader only, and nothing is written to the Conduit**; a saved view
   from the selection sends the layout it had (`CaseViewInput.layout`). (b) Store the positions: an amendment, not
   proposed.
4. **Removing and clearing** (GG2g2). (a) **Remove selected: one `DELETE .../nodes` with the selection's ids; Clear the
   graph asks first in the React's words ("Clear the graph", "Clear all …") and sends every node on the reader's canvas
   once; both Editor**, the stream's frame drawing the result for every reader. The confirmation says "This takes them off
   the case's graph for everyone in the case. Nothing is deleted from the data." (b) No confirmation.
5. **Groups** (GG2g3). (a) **`communities.ts` and its worker move to `glass-shared` (I11, the React file re-pointed,
   behaviour unchanged), `graphology-communities-louvain` moves with them** (MIT, checked by `make licence-check`'s
   Node half), and the page's module runs the worker same-origin under the existing `worker-src 'self'`. (b) A copy in
   the page module: two copies, against I11.
6. **The ids that are not this row's.** (a) **Left to their own rows:** manual link and split and explain cluster to
   GG4i (match strictness and explain); the pathfinder to GG4g (find connections); messages to GG3b's reader; pictures and
   icons to GG4f2; labels and value icons with the legend in GG2e's look; select-what-is-lit with the timeline (GG3c).
   Each part's `assertAllCovered` lists them as not offered on the page. (b) Your list.
7. **The suppression mark** (GG2g4). (a) **As `spec/02` §9.5 says it, on the node's menu: the reason box by keyboard,
   *Mark for suppression* off until there are words, Escape writing nothing; the marks read back from `GET
   .../suppression-marks` on load and as nodes arrive, so a marked node offers *Remove suppression mark***; offered to a
   holder of `edit_graph` at Editor; a marker on the node is **not** drawn (§9.5: "Not built"; Explore's list is
   GG4g's). (b) Also draw a marker: a spec change.
8. **Drawn items** (GG2g4). **(owner: this narrows ADR-143 C15, `spec/06` :26594, which gives every drawn item *Edit on
   board*; the fix is a C15 amendment as a diff file, never an edit to `spec/06`.)** (a) **Drawn nodes and links are dashed (as `nodeAttributes.ts:479` dashes a drawn link),
   no editing action is offered on them (no drag that writes, no remove from the menu, no mark), and *Edit on board*
   links to GG4a's `/cases/boards?case=…&board=…` only when `provenance.drawn.board_id` is not empty**, which by
   `handling.py:385-398` is only for its author; to anyone else the item says "Drawn on a board" with no link, and the
   amendment diff says so. The document behind a drawn item is GG4b's, and the canvas shows none. (b) *Edit on board* for every reader of a shared
   board: needs the board's id, which the stream withholds (rule 3): not proposed.
9. **Saving the selection as a view** (GG2g1). (a) **The selection bar's and the menu's *Save as a view* open a small
   form (name, default as the React gives it), one `POST .../views` with `node_ids` and `layout`; then "Saved as a view:
   ‹name›" and a link to it.** A selection over 10,000 is refused on the page with the figure, "Select 10,000 or fewer",
   never cut (rule 2). (b) Your words.

## GG2g1 · The selection, its menu, hiding and showing links, saving the selection (M)

`apps/pages/test/govuk/live-graph-select.spec.ts`. **Case 6 depends on GG2e's `l-steps-through-the-focused-nodes-links`**
(`actionRegistry.ts:171`), which GG2e owns and proves: a link is reached by `l` before Delete hides it.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Space on two focused nodes in turn | both selected; the selection bar says "2 selected" | Space replacing the selection |
| 2 | `Ctrl`+arrow | cycles the ring of selected nodes | cycling over every node |
| 3 | The menu by `\`, the ContextMenu key and Shift+F10 | the same menu each way, focused on its first item; Home, End and the arrows move | one key not wired |
| 4 | The menu's selection actions | in the bar's words, the same list | a word of the menu's own |
| 5 | Types with no links | folded into "‹n› types with no links", opened in place | every empty type listed |
| 6 | A selected link, Delete | hidden for this reader; "Show hidden links" brings it back; nothing sent to the Conduit | a `DELETE` sent for a link |
| 7 | Save as a view, 12 selected | one `POST .../views` with 12 `node_ids` and their `layout`; the sentence and the link | the ids of every node in view sent |
| 8 | 10,001 selected | refused on the page with the figure; nothing sent | the first 10,000 sent |
| 9 | No id in the HTML or live region | none | a node id in the bar |
| 10 | Keyboard | one case per id of this part; `assertAllCovered` red with one removed | an id offered with no case |

## GG2g2 · Dragging, the layouts, removing and clearing (M)

`apps/pages/test/govuk/live-graph-arrange.spec.ts`.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Drag a node; Shift+arrows on a selection | moved; nothing sent to the Conduit | a write per drag |
| 2 | Show previous positions; the grid | each toggles by keyboard and by pointer | a toggle with no keyboard route |
| 3 | Each layout from the Layout menu | the three layouts by keyboard; the settled nodes stay where they were on a later expansion (GG2f1's id) | the layout rerun on every delta |
| 4 | Remove selected (Editor) | one `DELETE .../nodes` with exactly the selected ids; drawn from the stream's frame | the response's `seq` applied without the frame |
| 5 | Clear the graph | asks first; Enter on "Clear all" sends every node on the canvas once; Escape sends nothing | sent on the first Enter |
| 6 | A Viewer | neither offered; a hand post's 403 in words | offered without the level |
| 7 | A drawn node selected (GG2g4's rule, here first) | Remove not offered for it | removed with the rest |
| 8 | Keyboard | one case per id of this part | an id offered with no case |

## GG2g3 · Finding and folding groups (M)

`apps/pages/test/govuk/live-graph-groups.spec.ts`; the moved `communities` unit tests in `glass-shared`.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Communities, by keyboard | groups found in the worker; each group's box drawn; the page's main thread not held (the module's frame clock) | Louvain run on the main thread |
| 2 | `g` on a focused node | its group folds into one node and opens again | another group folded |
| 3 | The box's fold button; collapse all and expand all | each by keyboard | a button out of the tab order |
| 4 | The worker | loaded from the page's own origin; no `securitypolicyviolation` (I2) | the worker built as a `blob:` URL |
| 5 | Two readers of different clearance | each reader's groups over their own stream-fed canvas only (rule 3) | the worker fed the second reader's stream frame (the fixture opens two streams; the plant passes the other's graph to the worker) |
| 6 | I11 | the React workspace's suite and budget unchanged | a behaviour change in the moved file |
| 7 | Keyboard | one case per id of this part | an id offered with no case |

## GG2g4 · The suppression mark, and drawn items dashed and read-only (S)

`apps/pages/test/govuk/live-graph-suppression.spec.ts`.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Mark a node with a reason | the reason box by keyboard; the button off until there are words; one `POST` with the trimmed reason | the button on with an empty reason |
| 2 | Escape in the reason box | nothing sent | the mark sent with no reason |
| 3 | Reload | the mark read back; *Remove suppression mark* offered; one `DELETE` removes it | the mark offered again over its reason |
| 4 | A reader without `edit_graph` | not offered; a hand post's 403 in words | offered by level alone |
| 5 | The route's 404 `node_not_found` | "That item is no longer on the graph." | "hidden" said |
| 6 | A drawn node and link | drawn dashed; no editing action offered | a drawn item draggable with a write, or removable |
| 7 | *Edit on board* for the author | links to `/cases/boards?case=…&board=…` | the link offered from an empty `board_id` |
| 8 | Another reader of the same item | "Drawn on a board", no link, no board id in the HTML | a link built from another field |
| 9 | Keyboard | `menu-item-mark-for-suppression` proved end to end | the item reached only by pointer |

## Waits on

GG2f1 (the node's menu and the forwarder calls); GG2e (the live page and its read-only actions, `l` among them); GG4a
(`/cases/boards?case=…&board=…`, *Edit on board*'s target); the owner's ruling on question 8; **WS4b to merge**
(decision 9).

## Files touched

`spec/08` (GW's rows, part by part); `apps/pages/modules/graph/` (the actions, the selection bar, the menu, the layouts,
the groups worker); `packages/glass-shared/src/canvas/communities.ts` and its worker, moved (GG2g3), with
`packages/glass-shared/package.json` and `apps/workspace/package.json` (the dependency moved) and the React importers
re-pointed (I11); `test/govuk/live-graph-*.spec.ts`, `keyboard/`, `csp/`; the fixture Conduit's routes.

## Checks (frozen when cut)

GG2e's list; for GG2g3 also the React workspace's whole suite and its budget (I11) and `make licence-check`.

## Out of scope

The ids of question 6; a marker drawn on a marked node; storing positions; the inspector (GG3d); any Conduit change;
`apps/workspace` beyond GG2g3's move.
