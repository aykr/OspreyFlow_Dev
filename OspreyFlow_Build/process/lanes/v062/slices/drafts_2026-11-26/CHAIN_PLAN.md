# The chain plan for GG2, GG3, GG4, GG5, WS4, GA1 and GR1 (an away drafting session, 26 November 2026, D246)

**Status: a plan, not ruled.** Written on the branch `drafts/2026-11-26` in `~/away-drafts-26`. Nothing is pushed or
merged, and no row is in `slices.tsv`. **Release scope A (the owner, 26 November): 0.7.0 keeps the graph and map
modules**, so every slice below is in 0.7.0 unless the owner moves it out.

**The tree this plan was read from.** This branch was cut from local `main` (`2b2124d69`, 25 November 05:54), which is
169 commits behind `origin/main` (`042c882f2`, 26 November 01:35). Every fact below was read from a read-only snapshot of
`origin/main` (`git archive`, not a worktree) and from the three away branches. **Re-read every line before cutting.**

## What already exists (the first slices)

| Slice | State on 26 November (read from the refs) | What it settles for the chain |
| --- | --- | --- |
| GG2a | **Built** on `away/GG2a` (`759a45233`); row cut on `origin/main`; "its merge waits for the owner's Mac measurement" | Sigma 4.0.6 meets the workspace's CI gate on a quiet machine with about 18% to spare (first frame about 24,700 ms against 30,000), and misses it in 2 of 3 runs under another account's load. **The owner's question 1 (go on with Sigma 4 or fall back) gates WS4b and every Sigma page's merge.** |
| GR1a | **Built** on `away/GR1a` (`005dcbfca`); ruled as an away round (16:25) | Built at **`/cases` and `/cases?case=<id>`**, not `/cases/{case_id}`: `apps/pages/server/pages.ts:55` (`PLAIN_PATH`) and `checkTree` (:106) admit a plain path only, and one page for each `FUNCTIONS.yaml` row in a tree. **Its question 1 decides the path form of every later case page.** |
| GG4a | **Built** on `away/GG4a` (`c92a1f4ed`), stacked on `away/GR1a`; the owner's exception to start before GG3 | At `/cases/boards?case=…&board=…`. **A rule-3 stop: `open_board` sends each drawn item's `source_document` to every reader of the board** (question 1), and the board's `ceiling` names the strictest marking to every reader (question 4). |
| GG2b, GG3a, GG5a, WS4a, GA1a | Drafted on 25 November, copied to `origin/main`'s `slices/drafts_2026-11-25/` "for his rulings tonight"; **no ruling recorded** in `RULINGS.md` up to 19:50 | as drafted |
| PL8a, PL9b, PL10, PL7f, GG6 | **Merged** on `origin/main` | PL8a's store exists, but **no slice mounts the panel frame on a page**, and none is drafted. GG3's "needs PL8" means that mount (called PL8b below; it is not in this plan's streams). GG6 merged, so decision 9's "the map module is not merged until GG6" is met. |

## The rules the order follows

1. **Decision 9** (`spec/06_DECISIONS.md` about lines 41091 to 41116): no page that draws with Sigma 4 merges until WS4 is
   in; it "may be written meanwhile". A page that draws nothing with Sigma (a table, a form, MapLibre alone, the board's
   own SVG) is not held by its first sentence. **But decision 9 also says "The rest of R4 may be written meanwhile, but
   it waits to merge"** (about line 41102), and `FUNCTIONS.yaml` puts the `graph-canvas` and `working-set` rows in GG2
   and the case list in R4 (:193, :200, :208). **So every GG2 slice (GG2b's tables, GG2c, GG2d included) merges before
   WS4b only by the owner's exception**; the "Exception" column says so where it is offered. (Corrected after review.)
2. **Decision 11** (about 41136 to 41160): any change below the Glass beyond X1 to X8 "comes back to the owner as an
   amendment". Every Conduit slice below is marked **amendment**, and its record is a diff file, never an edit to
   `spec/06`.
3. **The plan's rows** (the owner, 25 November): GG3 needs GG2 and PL8; GG4 needs GG3; GG5 needs GG2; WS4, GA1 and GR1 need
   GG2. The owner's exceptions so far are GR1a and GG4a, which started before GG2b. **Each further exception is listed in the
   "Exception" column as the owner's, never assumed.**
4. **Each page slice adds to the same few lists**: `apps/pages/server/pageList.ts`, `tree-govuk/routes.yaml`,
   `FUNCTIONS.yaml`, `tests/harness/test_pages_setting.py`'s route list, the keyboard and scripts-off folders, and
   `spec/08`. The additions are append-only, so two page slices can be built side by side, and the second to merge
   takes both sides (as the line's append-only merges already do).

## Sizes

**S**: one round, up to about 8 cases, one surface. **M**: one or two rounds, about 9 to 15 cases. **L**: more than one
round's work. An L is split before it is cut (the "Split" note says how).

## The table

"Side by side" names the slices this one can be built beside, in a separate worktree, with no shared file other than
the append-only lists above. ✱ marks the slices drafted in this session (`<ID>.md` in this folder).

| Slice | What | Depends on | Size | Side by side with | Exception the owner could give |
| --- | --- | --- | --- | --- | --- |
| **Paths and the page registry** | | | | | |
| GR1c ✱ | **A page owns a path pattern** (`/cases/{case_id}`, `/cases/{case_id}/boards/{board_id}`), and a function row may have more than one page in a tree. `pages.ts`'s registration rule, the route list's patterns, the harness's route list, the tree parity check. **Only if the owner answers GR1a question 1 with (b)**; with (a) this slice is not needed | GR1a's question 1 (b); GR1a and GG4a merged | M | GG4b, GG4c, GG3b, GA1b, GG5b, WS4a | none needed |
| **GR1: cases, brief, saved views, history** | | | | | |
| GR1a | The reader's cases and one case's page with its brief, read-only | built (away) | M | | (given) |
| GR1b ✱ | **New case**: a scripts-off form (name, "What data does this case read?": an existing dataset, or a new empty one) posting one `POST /v1/investigations` (which makes a new dataset itself from `new_dataset_name`, `app.py:4256-4258`) with the anti-forgery token | GR1a merged; NEXT_BATCH question 7 (New case is GR1's or GG2's) | M | GR1d, GG4c, GA1b, GG3b | start before GG2b (as GR1a) |
| GR1d ✱ | **A case's saved views**, read-only list with links to each view's page (GG2b), and save, share and delete as forms | GR1a merged; for the links, GG2b's path | M | GR1b, GG4c, GA1b | the list before GG2b (each view then links to GG2b's tables) |
| GR1e | **A case's history**, read-only (what changed, by whom, when), as the history route sends it | GR1a merged | S | every page slice | start before GG2b |
| GR1f | **A case's settings, access, datasets and domains**: the reads first, then each change as a form (Author's rights) | GR1a merged | L (split: GR1f1 reads, GR1f2 access changes, GR1f3 datasets and domains) | every page slice | start before GG2b |
| **GG2: the graph canvas and the working set** | | | | | |
| GG2a | The budget page (Sigma 4, measured) | built (away); merge waits for the Mac | M | | |
| GG2b | A saved view drawn read-only by the graph module, with paged tables for scripts off | GG2a merged; **merges after WS4b** (decision 9) | M | WS4a, WS4b (written beside, merged after) | the tables alone, merged before WS4b, the canvas half after |
| GG2c ✱ | **The delta client moved to `glass-shared`** (behaviour-preserving, no page; the React workspace's whole suite and its budget as the gate, I11), so a page module can hold the live working set | nothing: a live page needs it on Sigma 4 or Sigma 3 alike | S | WS4a, every page slice | **merging before WS4b is the owner's exception** (decision 9: "the rest of R4 … waits to merge"); writing it needs none |
| GG2d ✱ | **The Matrix**: two ARIA grids over the working set's own graph (`spec/02` about lines 2337 to 2363), the textual alternative, first on GG2b's saved view in place of its "details" tables | GG2b built; the owner's word on whether the Matrix is GG2d's or GG4's (GG4a question 0) | M | GG2e, WS4b | written now; **merged before WS4b only by the owner's exception** (decision 9) |
| GG2e ✱ | **The live working set on a page**, `/cases/{case_id}/graph`: the module subscribes through the stream proxy (CO3) with GG2c's client, read-only actions only (pan, zoom, fit, focus, select); scripts off answers with the case's saved views and the Matrix | GG2b, GG2c, GG2d; merges after WS4b | L (split: GG2e1 the subscription and draw, GG2e2 the read-only actions and their keyboard cases) | GG3b, GG4c | none: it draws with Sigma 4 |
| GG2f | **Seed, expand and the cap refusal**: the working-set writes (seed, expand, preview, links among, add by ids) with the three-option refusal in the canvas prompt's words (NEXT_BATCH question 9), and batch expansion | GG2e | L (split: GG2f1 seed and expand with the refusal, GG2f2 batch expansion) | GG3c, GG4d | none |
| GG2g | **The canvas's editing actions**: select, open links, drag, remove, find groups, mark for suppression (the `graph-canvas` row; A9, A10, B5, B7, B15), each with its keyboard case, and drawn items shown dashed and read-only (ADR-143 C15) | GG2f | L (split by action group, 3 to 4 slices) | GG4f, GG3d | none |
| **WS4: the React workspace on Sigma 4** | | | | | |
| WS4a | The gates WS4 is held to, on Sigma 3, shown red (the canvas-look comparison, `VERSION_WINDOW.yaml` with I20's check, readiness marks) | GG2a merged (question 0's reading) | M | GG2c, GR1 and GG4 page slices | start beside GG2a (the 25 November draft's first proposal) |
| WS4b ✱ | **The port**: `GlassCanvas.tsx`, the five version-bound files and the other nine importers to Sigma 4.0.6, judged by WS4a's three gates; the window closed in the same merge | WS4a merged; GG2a's question 1 answered "go on", and the Mac's figures in; the `@sigma/*` 4.x releases exist | L (**one merge, in rounds**: one npm workspace cannot hold Sigma 3 and 4 at once; WS4b question 1) | GG2c, GG2d, every table page | none |
| WS4c | **The way back, only if needed**: leave undrawn links out of the GPU program (ADR-119's lever), its own ADR, measured on CI first (NEXT_BATCH question 4) | GG2a or WS4b missing the budget | M | | |
| **GG3: inspector, search, timeline, documents** | | | | | |
| GG3a | The case's search panel, read-only, scripts off | GG2b (the plan's row) and PL8b | M | GG3b, GG4c | start after GR1a, as GG4a did |
| GG3b ✱ | **One document in the reader, read-only**: its title, handling, text and designations as `GET .../documents/{document_id}/reader` sends them, and the file by `.../file`, at the case's path, reached by link (an Ask citation, a search result, a brief's attachment). **No route lists a case's documents** (`services/api/app.py` has none), so a list would be an amendment | GR1a merged; the plan's GG2 and PL8b | M | GG3a, GG4c, GA1b | start after GR1a: it draws nothing and needs no selection |
| GG3c | **The case's timeline**, read-only: the events and the histogram as a table and a plain SVG chart (the GR3a chart rule), with playback later | GG3b's case path; the timeline module waits for decision 6's module rules | M | GG3a, GG3b | the table and chart before GG2 |
| GG3d | **The inspector** for a selected node or link (history, events, notes, shared contacts), then link change as a form | GG2e (a selection) | L (split: GG3d1 reads, GG3d2 notes and link change) | GG2f | none: it needs the canvas's selection |
| GG3e | **Adding files to a case** (upload through the page service's multipart forwarding) | GG3b | M | GG3c, GG4d | |
| **GG4: boards, graph extras, Matrix, Ownership, query builder, metrics** | | | | | |
| GG4a | Boards, read-only tables | built (away) | M | | (given) |
| GG4b ✱ | **A drawn item's source document and the board's ceiling withheld from a reader who may not read them** (a Conduit part, security; GG4a's questions 1 (b) and 4 (a)). **Amendment** to decision 11 (a diff file) | the owner's ruling on GG4a's questions 1 and 4 | S | every page slice (it touches only the Conduit) | none: a security part |
| GG4c ✱ | **Making, sharing and deleting a board**, as scripts-off forms on GG4a's pages, with the anti-forgery token | GG4a merged | S | GR1b, GR1d, GG3b, GA1b | before GG3 (as GG4a) |
| GG4d ✱ | **Drawing on a board without a mouse**: add a drawn item, add a link between two items (the keyboard route *Draw a link*), change an item, withdraw an item, as scripts-off forms (ADR-143 C7, decision 5) | GG4c; GG4b (a drawn item's source document is chosen on the form) | M | GG3b, GA1b | before GG3 |
| GG4e ✱ | **The board module**: the board drawn as positioned SVG from `layout` (classes only, the CSSOM helper of decision 3), with moving by drag and by keyboard, and the link handle, each drag with its keyboard route (I7, rule 13) | GG4d | L (split: GG4e1 drawn and read-only, GG4e2 move and link by pointer with the keyboard routes) | GG3c | before GG3: the board draws without Sigma |
| GG4f | **Pictures, matches, drawn watches and promotion** (pictures by upload; a match to a loaded item; the board's drawn watches; *Promote* into the case) | GG4d; GG3e's upload pattern for pictures | L (split: GG4f1 drawn watches and matches, GG4f2 pictures, GG4f3 promotion) | GG2g | |
| GG4g | **Graph extras**: the Explore panel and find connections | GG2e and GG3 | M | GG4h | none |
| GG4h | **The Ownership view** (and the Matrix, if the owner rules it GG4's rather than GG2d's) | GG2e | M | GG4g | |
| GG4i | **The query builder, metrics, match strictness and explain, cross-filter** (A3, A7, A8, A12, B9, B10, B19) | GG2f and GG3 | L (split by function: query builder; metrics; match strictness; cross-filter) | GG4g, GG4h | |
| **GG5: map and site plans on MapLibre 6** | | | | | |
| GG5a | The strict-policy run of MapLibre 6.19, test-only | none (the word of 21 November) | S | everything | (given on 21 November) |
| GG5b ✱ | **The map module and the tiles path**: `apps/pages/modules/map` on MapLibre 6.19 (one version with the workspace, I20), its worker served same-origin, tiles, glyphs and sprite reached through the page service, I2's every-page policy spec for map pages; first on a test page, then on a case map that draws the places of a saved view | GG5a's report (no `blob:`, no `eval`); GG2b's saved view for the data | M | GG2c, GG2d, GG3b, GG4 forms | before GG2b, on a test page only |
| GG5c | **The heat layer and the hotspot histogram** (A1, A2) | GG5b | M | GG5d | |
| GG5d | **The boundary filter and the gazetteers** | GG5b | M | GG5c | |
| GG5e | **Site plans**: the plans of a case, calibration, and rotation and pitch (N19-07, D48) | GG5b | L (split: GG5e1 view and calibration, GG5e2 rotation and pitch) | GG5c, GG5d | |
| GG5f | **The graph layer on the map** (`@sigma/layer-maplibre` 4.0.1, decision 9) | GG5b, WS4b | M | | none: it draws with Sigma 4 |
| **GA1: Ask & Chat** | | | | | |
| GA1a | The case's conversation, read-only | GG2b (the plan's row: the conversation's visibility reads the working set) | M | GG3b, GG4c | start after GR1a (the route's filter holds; fewer answers shown) |
| GA1b ✱ | **Asking a question**: a scripts-off form with the anti-forgery token; *What will be read* first (`will-read`), the route's deadline said in words; the answer shown on the conversation page | GA1a; the owner on `ASK_MODEL`'s right (GA1a question 6) | M | GG3b, GG4c, GR1b | with GA1a |
| GA1c | **Accepting and rejecting a proposal** (`EXTRACT_FILES`, editor), each a form; accepted is `inferred`, never confirmed (rule 5) | GA1a | S | GA1b | with GA1a |
| GA1d | **A view's conversation** (`?view_id=`) | GA1a, GR1d | S | GA1c | |
| GA1e | **"Show all on graph" and "Save as a view"** from an answer | GA1a, GG2e, GR1d | S | GG2f | none |
| **Release** | | | | | |
| RL2 | The release (brief exists). Refuses while `VERSION_WINDOW.yaml` lists anything | every slice above that 0.7.0 keeps, WS4b merged | | | |

## Which order unblocks most

Counting, for each open question or slice, the slices that wait on it:

1. **GG2a's question 1 and the Mac's figures** (the owner's): WS4b, and through decision 9 the merge of every GG2
   slice (decision 9's "the rest of R4 … waits to merge"), GG3d, GG4g to GG4i and GG5f. **About 15 slices.** Nothing a draft can do moves it.
2. **GR1a's question 1, the path form** (the owner's): every later case page names its address. GR1c exists only for
   answer (b). **About 20 slices** name an address. Drafted early, so the owner can rule it with a slice in hand.
3. **GG4a's questions 1 and 4, the source document** (the owner's, security): GG4b, then GG4d and everything that draws an
   item.
4. **PL8b, the panel frame on a page** (not in this plan's streams; **no draft exists**): GG3a and every GG3 slice by the
   plan's row. **Named for the conductor.**
5. **GG2c** (the delta client's move): GG2e and everything after it. It waits on nothing: a live page needs the client on
   Sigma 4 or on Sigma 3 alike (corrected in GG2c's draft).
6. **WS4a, then WS4b**: the merge of every Sigma page.

**The drafting order of this session** (the owner's instruction: GG4's later parts and GG3b first, then by the count
above): GG4b, GG4c, GG4d, GG4e, GG3b, GR1c, GG2c, WS4b, GR1b, GR1d, GA1b, GG2d, GG2e, GG5b. The drafts that exist when
the session stops are listed in `INDEX.md`.

## Side by side: the lanes a conductor could run at once

Five seats can work without colliding, once their slice is ruled (each in its own worktree, rule 14):

| Lane | Slices in order | Shares only |
| --- | --- | --- |
| Boards | GG4b (Conduit) ∥ GG4c → GG4d → GG4e → GG4f | the append-only lists |
| Cases | GR1c (if (b)) → GR1b → GR1d → GR1e → GR1f | the append-only lists; GR1c first, because it changes `pages.ts` |
| Graph | GG2c → GG2b → GG2d → GG2e → GG2f → GG2g | `apps/pages/modules/graph`; GG2c and GG2d also re-point imports in `apps/workspace` |
| Workspace | WS4a → WS4b (→ WS4c only if needed) | `apps/workspace`, which GG2c and GG2d also touch (imports only): run them before WS4b or rebase them after it |
| Documents and Ask | GG3b → GG3c → GG3e; GA1a → GA1b → GA1c | the append-only lists |
| Map | GG5a → GG5b → (GG5c ∥ GG5d) → GG5e; GG5f after WS4b | `apps/pages/modules/map`, `server/headers.ts` (GG5b only) |

**Two collisions to plan for.** (1) **GR1c changes `pages.ts`, which every page slice registers through.** If the owner
answers GR1a question 1 with (b), GR1c merges before any other new page, or each page slice is written in the query form
and moved by GR1c. (2) **GG5b may change `server/headers.ts`** (a map page's policy). No other slice here touches it. (3) **The case pages share files**: GR1b, GR1d and GR1e (and GA1's pages among themselves) edit the same `server/cases.ts`, `casesWords.ts`, `cases.njk`, `casesConduit.ts` and keyboard and scripts-off specs, so within the Cases lane (and the Ask lane) they run one after another, not side by side; across lanes only the append-only lists are shared.

## Not in this plan

PL8b (named, not drafted: outside these streams); AD4 (Themes); the reports and dashboards rows; the Studio's graph
preview (IS5g, held by decision 9 as well); the Default tree's twins of each GOV.UK page (`PARITY_EXCEPTIONS.yaml` is the
owner's).
