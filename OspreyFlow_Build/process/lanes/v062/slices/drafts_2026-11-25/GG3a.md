# Slice GG3a · GG3 · The case workspace's panels on the GOV.UK tree, first the search panel, read-only and scripts off, laid out as PL8's scripts-off frame (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper.

**Question 0, rechecked against the plan's row (the owner, 25 November 2026, later the same day).** The plan's row is
"**GG3: Inspector, search, timeline, documents (R5)**", which **needs GG2 and PL8**. The first draft read GG3 as the
inspector, search and the timeline. **Changed: documents are GG3's too** (`FUNCTIONS.yaml:243-249`, `documents`:
the reader, a node's messages, adding files; scenarios A6, B6). Ask & Chat is GA1's, not GG3's. **Also changed:
question 2's proposal now follows the plan's "needs".** The first draft proposed starting before PL8; the plan's row
says GG3 needs both GG2 and PL8. The rows GG3 holds are `inspector` (`FUNCTIONS.yaml:211-217`), `search` (:219-225),
`timeline-playback` (:227-233) and `documents` (:243-249). The record agrees: "GG3 needs PL8" (`RULINGS.md` line 373)
and "PL7 → GG2 → GG3 → GG4" (`slices/NEXT_BATCH_2026-11-24.md:1`).

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **PL8 is not merged.** PL8a, "the panel frame's logic and storage in plain TypeScript, no page" (`slices/PL8a.md`),
  is on round 13 today (`RULINGS.md` lines 6 to 12). **Nothing mounts a frame on a page**, and the slice that does
  waits for PL9's second half (PL8a.md:3 and :10; PL9b is cut). The ten actions are `PANEL_FRAME_ACTIONS`
  (`packages/glass-shared/src/keyboard/actionRegistry.ts` about lines 1308 to 1319). The plain layout modules in
  `packages/glass-shared/src/layout/` are `layoutSizes.ts` (`MIN_SIDE_WIDTH = 300` at :14), `sidePanelState.ts` and
  `panelOrder.ts`. `panelFrameStore.ts` is PL8a's, on its branch. **The owner's PL8 ruling 3 (24 November,
  `RULINGS.md` line 55): "scripts off: every panel open in its normal state, no controls".**
- **The search panel today.** `apps/workspace/src/search/`: `GlobalSearch.tsx` (303), `SearchResults.tsx` (468),
  `AddFromList.tsx` (186), `SearchFilters.tsx` (89), `searchOptions.ts` (118), `drawSearchResult.ts` (19) and
  `useSearchResultsOverlay.ts` (67). `GlobalSearch.tsx:67` names `/v1/search` and `/v1/suggest`, which have **no
  Conduit route at those paths** (a scout's reading: say what calls them before relying on it).
- **The search route** (`services/api/app.py` about lines 6632 to 6684): `POST /v1/investigations/{id}/search`, behind
  `require_right(INVESTIGATE)` and the case viewer gate. It builds "the reader's access filter ... from their own
  principal ... into the index's query" (ADR-149), searches only the case's datasets, and **audits every search** with
  the query, group, filters, page and source (about :6675-6683). A bad query is 422 (:6667). Request (`SearchPageRequest`,
  `packages/schemas/search.py`): `query` (1 to `MAX_QUERY_CHARS`), `limit`, `group`, `filters`, `page`,
  `page_size` (at most 50). Answer (`SearchPageResponse`, same file): `nodes`, `query`, `source` (`index` or
  `fallback`), **`limited` and `limited_reason`**, `total`, `counts_exact`, `groups`, `filters`, `page`, `page_size`,
  `more` and `results`. The suggest route is `POST .../suggest` (:6688).
- **The inspector and the timeline**, for the later slices. Inspector: `apps/workspace/src/inspector/` (`Inspector.tsx`
  683, `LinkChange.tsx` 495, `LinkEvents.tsx` 484, `LinkNotes.tsx` 378 and others). Its reads are link history
  (`app.py:7688`), events (:7704), notes (:8679) and shared contacts (:7011), each behind `INVESTIGATE`; link change is
  `EDIT_GRAPH` (:7446). Timeline: `apps/workspace/src/timeline/Timeline.tsx` (846), reading `fetchCaseEvents` and
  `fetchHistogram` (`packages/glass-shared/src/analytics/api.ts:43`, :58), with routes not traced.
- **The case gate.** `_authorized_at` (`app.py:2851-2878`): no level, another unit and no case are the same 404; a
  level too low is 403.
- **The page service.** No case page exists yet (GR1a is drafted beside this). There is no graph module and no frame on
  a page. Decision 9: no page that draws with Sigma 4 merges before WS4. **A search panel draws nothing with Sigma.**
- **Scenarios.** Search's row names B4 (`FUNCTIONS.yaml:223`, a row of scenario B in `spec/08`). There is no scenario
  for a GOV.UK search page.

## Questions for the owner (the proposal first)

1. **The first slice.** (a) **The case's search panel, read-only, scripts off**, at `/cases/{case_id}/search`: a `GET`
   form (the words, the group and the filters the route offers) whose server half calls `POST .../search` once, and
   the results as a table in the route's order, a page at a time (`page`, `more`). It is laid out as PL8's scripts-off
   frame (the panel open in its normal state, no controls), so that the mounting slice adds controls and changes no
   markup. **Adding a result to the working set is GG2b's** (the working set's), not GG3a's. (b) The inspector first,
   for a node named in the address. That needs a node's identity in the URL and the canvas's selection, which are GG2's.
   (c) Wait for PL8's mount.
2. **Whether GG3a waits (changed after the plan's row was given).** (a) **It waits for both GG2 (its first page with a
   working set, GG2b) and PL8's mounting slice, as the plan's row says.** Then the panel is mounted in the real frame
   from the start, "add to the working set" can be offered in the same slice, and PL8's keyboard cases cover its frame.
   (b) An exception to the plan's needs, for the owner alone to give: start after GR1a. GG3a uses no frame code, only the
   frame's scripts-off layout (the owner's ruling 3), with the markup's `data-action` and `data-id` hooks (decision 3)
   named for PL8's attach function, and a search panel draws nothing with Sigma. The first draft proposed this.
3. **Search is a `POST` at the Conduit and a `GET` on the page.** (a) **The page's form is `GET`** (a search changes
   nothing, so the result can be linked and the back button works). The server half turns it into one `POST` with the
   person's token. No anti-forgery token is needed for a `GET` (I17 covers state-changing requests). (b) A `POST` form
   with the token, which loses the link.
4. **A limited result (rule 2).** (a) **When the route says `limited`, the page says so in words with
   `limited_reason`, above the table**, and never shows a partial table as if it were whole. When `counts_exact` is
   false, the count is said as "about N". (b) Show `total` alone.
5. **The search's audit.** (a) **One `POST` per search**, pinned by a test, so the Conduit's audit row is written once
   (as GR1a's case 8). (b) No test.
6. **What a result shows.** (a) **Exactly the route's `results` and `nodes`**: each result's type, its match, its passage, its date and
   its datasets' names (`SearchResult`, `packages/schemas/search.py` about lines 63 to 71), with no internal id on the page outside a link's own path (rule 7). (b) Your list.
7. **The scenario.** (a) **A new `spec/08` scenario, SP, written first and red first**, its id added to the `search` row
   for this page only. (b) Your words.
8. **The fixture.** (a) **The strict reader and the field census (GR3a's)** over `SearchPageResponse`, with the
   fixture refusing as the route refuses: 422 for a query over the limit, 404 or 403 by the case gate. Answers come
   from the real route when GR3b lands (rule 15).

## The table of cases (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A search with five results | a table of the five in the route's order: each label (from the route's `nodes`), type and datasets; the query kept in the form | the results sorted by the page |
| 2 | A second page | `page=2` in the address; the route's second page; a "Next" link only while `more` is true | a "Next" link drawn from `total` |
| 3 | A limited result | the sentence with `limited_reason` above the table | the table drawn with no sentence (rule 2) |
| 4 | `counts_exact` false | "about N results" | the bare `total` |
| 5 | Two readers of different clearance over the leak test's world | the lower reader's results and counts are the route's, with nothing added by the page | the page counting a total from a second read |
| 6 | An empty query or one over the limit | the route's 422 said in the form's error summary (GOV.UK pattern), the words kept | a 422 shown as "no results" |
| 7 | No level, another unit, no case, no `INVESTIGATE` | the same 404 page, words and status, as a page that does not exist | the route's 403 passed through |
| 8 | One search | exactly one `POST .../search` (one audit row) | the page searching twice (for the count and the rows) |
| 9 | The Conduit gives no answer, or 401 | the 502 "could not be read" page; an ended session says to sign in again | an empty table |
| 10 | A body missing a required field | "could not be read", never "no results" | each required field removed in turn |
| 11 | No internal id on the page | no node id in the HTML outside a link's own path | a node id printed in a cell |
| 12 | The frame's markup | the panel's region carries the `data-action` and `data-id` hooks PL8's attach function reads, with no inline style | a `style` attribute (I2's policy) |
| 13 | Keyboard | the form and each link reachable and working, one case in the GOV.UK keyboard folder (rule 13) | the submit button out of the tab order |
| 14 | Scripts off | the page whole and the search completes by the form (I4) | none: it holds no script; the spec proves it |

## Checks (frozen when cut)

GR3a's list, adapted: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; the new scenario's test
and the pages' tests; `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`,
`test_pages_foundation.py`, `test_design_gates_reach.py`; `test_ui_words_check.py`, `test_copy_says_no_client.py`,
`test_doc_citations_check.py`; `tests/harness/test_pages_setting.py` (the route list); `ruff check .`;
`make -C OspreyFlow_Build design-check`; the cheap checks of 20 November.

## Out of scope

Adding to the working set (GG2b); the inspector, the timeline and documents (later GG3 slices); suggestions as you type (a module,
later); the frame's controls and their keyboard cases (PL8's mount slice); any graph drawing; any Conduit change;
`apps/workspace`.
