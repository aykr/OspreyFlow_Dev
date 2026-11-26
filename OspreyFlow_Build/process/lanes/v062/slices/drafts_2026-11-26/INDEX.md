# Away-round drafts of 26 November 2026 (D246, the server's build account)

**Status: drafts, not ruled.** Written on the branch `drafts/2026-11-26` in `~/away-drafts-26`. Nothing is pushed or
merged, and nothing is written outside this folder. No row is in `slices.tsv`, and no decision record, Makefile, CI file,
`osprey.yaml` or `data/` was touched. **No test was run and no container started** (docs only, as the owner asked). All
data named is synthetic, and the client is not named.

**Read from `origin/main` at `042c882f2`, not from this branch's base.** This branch was cut from local `main`
(`2b2124d69`), which is 169 commits behind. Every citation was read from a read-only snapshot of `origin/main`
(`git archive`, no worktree) and from the away branches `away/GG2a`, `away/GR1a` and `away/GG4a`. Re-read every line
before cutting.

**The plan is [CHAIN_PLAN.md](CHAIN_PLAN.md)**: every slice still needed for GG2, GG3, GG4, GG5, WS4, GA1 and GR1, with
what it depends on, its size, what can be built side by side, and the order that unblocks most.

## Three things to read first

1. **GG2a, GR1a and GG4a are built, on their away branches, not merged.** The owner's open questions in their reports
   decide most of what follows:
   - **GG2a question 1.** Sigma 4 passes the CI gate with about 18% to spare on a quiet machine, and misses it 2 runs in
     3 under another account's load. Go on with Sigma 4, or fall back to Sigma 3? WS4b and the merge of every Sigma page
     wait on this answer (about 15 slices).
   - **GR1a question 1.** Do case pages live at `/cases/{case_id}` (this needs GR1c) or keep the query form? About 20
     slices name an address.
   - **GG4a questions 1 and 4.** The source document and the ceiling are a security question, and GG4b's draft finds the
     leak is wider.
2. **GG4b (security): a drawn item's source document reaches every reader of the case on every read path**, not only the
   board route GG4a stopped on: the working set, search, link changes and the adapter's serialisation all send the
   element through `withhold_sources`, which blanks only `board_id` for non-authors
   (`packages/ontology/handling.py:335-397`). The document's id is in `drawn.source_document` and in the source's
   `document_id` (`services/api/boards.py:466`, :471-479). **Every question in GG4b is the owner's.**
3. **PL8b, the panel frame mounted on a page, has no draft**, and GG3's row needs it. It is outside these streams. Named
   for the conductor.

## The drafts, their questions, and what each waits on

The proposal for each question is in the draft. A question marked **(owner)** is a ruling, a security matter, a key or
a credential, and was not guessed. Every other question has a proposed (a) that a builder could follow if the owner
says "A".

| Draft | What it proposes | Its questions | Waits on |
| --- | --- | --- | --- |
| [GG4b.md](GG4b.md) | **Security, a Conduit part.** A drawn item's source document is withheld on every read path from a reader who may not read it. The board's ceiling goes only to a reader cleared for it | **All owner (security):** 1 what such a reader is sent (proposed: the item without the document, in `withhold_sources`); 2 how "may read" is decided in a pure function (proposed: the document's handling recorded at drawing), **and whether a field withheld in `withhold_sources` satisfies rule 3**; **3 the inference "no note means a document" (proposed: a note required from now on, an ADR-143 decision 4 change)**; 4 a document re-marked later (proposed: a stop if no sweep exists); 5 the ceiling; **6 the decision record as a diff file (ADR-143 amendment, decision 11's X9)**; 7 built as an SE-style security part | the owner's ruling on GG4a's questions 1 and 4 |
| [GG4c.md](GG4c.md) | Making, sharing and deleting a board, as scripts-off forms. The first GOV.UK page that writes, so it sets the write pattern | 1 blank boards only; 2 offered from `GET /v1/me/rights`; 3 refusals in words, a non-creator gets the 404; 4 delete after a confirmation page; **5 sharing cannot be undone (no unshare route)**; 6 post then `303`; 7 BD extended | GG4a merged |
| [GG4d.md](GG4d.md) | Drawing by form: add an item (two steps: the type, then its fields), draw a link, change an item, withdraw one | 1 scope; 2 two steps; 3 the next free place on a grid; **4 no source document until GG4b**; 4b follows GG4b question 3; 5 ids only in hidden fields; 6 a marking never offered lower; 7 the banner after a withdrawal names what the route says went with it (rule 2); 8 a sentence for each refusal code | GG4c; GG4b for the document |
| [GG4e.md](GG4e.md) | The board as a picture: server-rendered SVG from `layout` (no script, geometry as attributes, not styles), then a module that moves items by pointer and arrow keys | 1 the split, GG4e1 and GG4e2; 2 the picture is `role="img"` and the tables carry the content; 3 unplaced items on the grid; 4 not drawn past 500 items; 5 a move is sent after a 400 ms pause; 6 the handle opens GG4d's form; **7 I7's coverage test in the page service, which does not exist yet**; 8 no CSSOM helper needed | GG4d |
| [GG3b.md](GG3b.md) | One document in the reader, read-only: its text with marked words (provenance in words, rule 5), and its picture or film. Linked from Ask and search (a brief's attachments are never documents). **No route lists a case's documents** | 1 scope; **2 start after GR1a by the owner's exception (as for GG4a)**; 3 the address; 4 no graph id shown; 5 a cut email said in words (rule 2); **6 how the file is shown: a content type a browser runs as a page is a stop (owner, security)**; 6b `nosniff` is already sent, pinned by a test; 7 reached by links only; 8 one 404 for every refusal; 9 one read per render; 10 scenario DR | GR1a merged; the plan's GG2 and PL8b, unless the owner gives the exception |
| [GR1c.md](GR1c.md) | Named path parts (`/cases/{case_id}`), and several pages per function row; GR1a's and GG4a's pages moved to them. **Withdrawn if GR1a's question 1 is answered (a)** | **0 GR1a's question 1 itself (owner)**; **1 an ADR-152 amendment as a diff file, or a code rule recorded in `spec/02` (owner)**; 2 `{name}` segments with a plain first segment; 3 the registry refuses a decoded slash before any handler runs (GG4a's finding made a rule); 4 ambiguous paths refused; 5 a page gains `row`; 6 old addresses `303` for one release; 7 I2 and I4 open each pattern with a named id; 8 GR1c merges before new case pages | the owner's ruling on GR1a's question 1 |
| [GG2c.md](GG2c.md) | The working set's delta client moved to `glass-shared`, behaviour unchanged (I11), no page | 1 the client and its unit tests move; the integration test stays; 2 its out-of-date header corrected; 3 no browser socket factory yet; 4 I11's proof on one machine | nothing (it does not depend on GG2a's outcome) |
| [WS4b.md](WS4b.md) | The React workspace's port to Sigma 4, judged by WS4a's three gates, with the version window closed in the same merge | **1 one merge in rounds, not two slices (one npm workspace cannot hold two Sigmas)**; **2 the `@sigma/*` plugins: a 4.x release must exist, or stop (a peer range is not proof)**; 3 Sigma 4's own dashed links, judged by the comparison; 4 `@sigma/layer-maplibre` 4.0.1 replaces the local port; 5 settings read back (GG2a's lesson); **6 judged on CI's runner and the owner's Mac (owner)**; 7 the window emptied; 8 ADR-119 kept, WS4c if red | WS4a merged; **GG2a's question 1 answered "go on" (owner)**; the Mac's figures |
| [GR1b.md](GR1b.md) | New case as a scripts-off form: the name, the data it reads (a new dataset or an existing one), and its domain models | 1 at `/cases?new=1` until GR1c; 2 offered from `create_case`; 3 both choices on one form, exactly one sent; 4 an empty dataset name takes the case's name; 5 domain models, empty included; **6 the route answers all three dataset refusals with one detail-less `422 dataset_refused`: said by the branch the page sent**; 7 `303` to the new case; 8 CS extended | GR1a merged |
| [GR1d.md](GR1d.md) | A case's saved views: the list, saving a **filtered** view (no canvas needed), and sharing and deleting one's own | 1 scope; 2 boards left out of the list, with a link; 3 a row's words use `chosen`, never the creator's count (C045); **4 who made a view (the same ruling as GR1a's and GG4a's question 2: owner)**; 5 the filter form; 6 share and delete offered only on one's own views; 7 a part of the case page until GR1c; 8 converted and merged views said in words | GR1a merged; GG2b for the links |
| [GA1b.md](GA1b.md) | Asking a question, scripts off: *will read* first, one post, and the answer in the conversation. Over **the whole case** only, since a GOV.UK reader has no canvas | 1 the whole case only; 2 two buttons; **3 the post waits up to the Conduit's bounds (the server half's client needs a per-call signal, `conduit.ts:70`); a front-proxy timeout under 16 minutes is a stop (owner)**; 4 the role's default engine; **5 Editor, as the routes are, and `rights.py:38`'s "Viewer" comment corrected (owner: GA1a's question 6)**; 6 the model's refusals in the Conduit's words; 7 "Press once" | GA1a |
| [GG2d.md](GG2d.md) | The Matrix on the GOV.UK pages: server-rendered, paged tables for scripts off, an ARIA grid when scripts run, first on GG2b's saved view | **0 whose the Matrix is, GG2d's or GG4's (owner, as GG4a's question 0)**; 1 `matrixRows.ts` and the label functions move first (I11); 2 the analyst's label choice; 3 paging and sorting by link; 4 the grid's keys; **5 strength and rarity are computed over the case's working set, not a view: left off a saved view (owner, if wanted there)**; **6 `spec/02`'s "no request of its own" is out of date: the React Matrix makes two requests** | GG2b built; question 0 |
| [GG2e.md](GG2e.md) | The live working set on a page: the graph module fed by the delta stream through CO3's proxy, read-only actions only. Merges after WS4b | 1 the split, GG2e1 and GG2e2; **2 scripts off: a parity line (the existing `scripts-off-drawn-canvas` line does not cover a page with no table), or a new Conduit read of the working set (owner: I4, decision 11)**; 3 the address; 4 the read-only actions by id; 5 the cap on the stream; 6 a socket that ends (the browser cannot tell an ended session from an outage by the socket: the page asks); 7 GG2a's perf spec over this page | GG2b, GG2c, GG2d; WS4b to merge |
| [GG5b.md](GG5b.md) | The map module on the page service: MapLibre 6.19, its worker, its basemap and its glyphs; a saved view's places as MapLibre circles, with a table for scripts off | 1 a saved view's places; 2 not the workspace's Sigma look (GG5f's); **3 `Range` through the forwarder: today it sends no `Range` and copies back no `Content-Range`, so the PMTiles basemap cannot be read through it**; **4 glyphs: only the workspace's nginx serves `/fonts/`, and a complete GOV.UK deployment has no workspace; a harness mount into `pages`**; **4b the labels' font (Noto Sans) is not in Amendment 2's list, and its test cannot see a map style: whether map glyphs are a font under Amendment 2 (owner)**; 5 the worker; 6 `DRAWING_MODULES` gains `map`; **7 no change to `headers.ts` without the owner's word**; 8 the cap | GG5a's report; GG2b's saved view |
| [GA1c.md](GA1c.md) | Accepting or rejecting a model's proposal by form; accepted is `inferred`, never confirmed (rule 5) | 1 one at a time, the case's conversation; 2 offered from `extract_files` and the level; 3 the words say "accept as inferred"; 4 reviewed meanwhile (409 `candidate_not_pending`); 5 `303` back to the answer | GA1a |
| [GA1d.md](GA1d.md) | A saved view's own conversation: read, asked in and reviewed in the view, never mixed with the case's | 1 reached from GR1d's list; 2 GA1b and GA1c in a view, each sending `view_id`; 3 a private view said; 4 one 404 | GA1c; GR1d |
| [GR1e.md](GR1e.md) | A case's history, read-only: fixed labels and times, no size (ADR-124 decision 8); restore waits for GG2e | 1 read-only; 2 the route's order; 3 a part of the case page; **4 the route sends every step with no paging: all shown, a page-side cut is not proposed (rule 2)** | GR1a merged |

## The owner's questions in one list (rulings, security, keys)

None of these was guessed. Each draft gives the options.

1. **GG2a question 1** (in its away report): go on with Sigma 4, or fall back. Also its questions 2 and 3: the first
   frame's end event, and an expansion gate in CI.
2. **GR1a question 1** (in its away report): the address form. GR1c is the slice if (b).
3. **GR1a question 2 and GG4a question 2** (in their reports), and GR1d question 4: who made a case, a board or a view
   is an account's id, not a name. **This session found that the Conduit does resolve names for one route already**: the
   questions route sets `author_name` from `principal_names.display_names` (`services/api/app.py:8280-8281`). So a later
   Conduit part could do the same for the board and case routes (an amendment).
4. **GG4b questions 1 to 7** (security, all of them).
5. **GG3b question 6**: what a document's file may be served as.
6. **GA1b question 5 and GA1a question 6**: who may ask (`ASK_MODEL`'s comment says Viewer, while the routes need an
   Editor).
7. **GA1b question 3**: whether any shape's front proxy cuts a request under 16 minutes (a harness change, if so).
8. **GG2e question 2**: the live working set with scripts off (a parity line, or a Conduit amendment).
9. **GG2d question 0 and GG4a question 0**: whether the Matrix is GG2's or GG4's.
10. **GR1c question 1**: whether named paths need an ADR-152 amendment.
11. **WS4b question 6**: where the port's budget is judged.
12. **GG5b question 7**: any change to the page service's security policy. **GG5b question 4b**: whether map glyphs
    are a font under ADR-152 Amendment 2 (the workspace already serves Noto Sans, which the list does not name, and the
    list's test cannot see it).
13. **The exceptions to the plan's "needs"**, each the owner's alone: GG3b, GA1a and GG3a after GR1a; WS4a beside GG2a;
    GG5b on a test page before GG2b (the "Exception" column of the plan).

## Corrections found on the way (for the orchestrator; no file outside this folder was changed)

- **GG2b question 8** (25 November) is answered by the code: `open_case_view` names no `require_right` on purpose.
  "Listing and opening need only the level" (`services/api/app.py:4780-4781`).
- **GG5a's draft** (25 November): the tile route is at `app.py:9478`, not :9408. Scenario A3 has its own row
  (`spec/08` :384). "No forwarder for tiles" is wrong: `forward.ts` carries every `/v1` path but three. What it lacks is
  `Range` (GG5b question 3).
- **GG3a's draft**: "PL8 is not merged" was true at `4f77858a5`. PL8a merged as `1d16bb2f2`, and
  `packages/glass-shared/src/layout/panelFrameStore.ts` is on `origin/main`.
- **WS4a's draft** says "Fifteen source and harness files import `sigma`". It is **15 import lines in 13 files**, and
  `@sigma/export-image` is declared but imported nowhere.
- **`spec/02` about lines 2337 to 2345** says the Matrix has "no request of its own". `MatrixView.tsx:407-425` fetches
  connection strengths and rarity (ADR-139 decision 6). This is a spec correction for GG2d (rule 11).
- **The Ownership and metrics routes need rights beyond `investigate`**: `TRACE_OWNERSHIP` (`app.py:14804`, :14831,
  :14873) and `RUN_ANALYSIS` (`compute/{metric}`, :6085). This is for GG4h and GG4i when they are drafted.
- **`POST /v1/drawings` (the no-case drawing) also needs `CREATE_CASE`** (`app.py:11300-11303`).
- **NEXT_BATCH question 7** (New case: GR1's or GG2's) is answered by the owner's ruling on GR1a's draft: "New case is
  GR1b".
- **`citation_allowlist.txt:55` and :61** already name `VERSION_WINDOW.yaml` and `same_drawing_versions_check.mjs`,
  neither of which exists yet (WS4a's).
- **`sigmaMaplibreLayer.ts:81` hard-codes an outside style address** (`demotiles.maplibre.org`), which `MapView.tsx:377`
  overrides. It is harmless today, but it is an I3 risk for anything that copies it.
- **The away branches' base.** This branch's `main` is stale, so any later away drafting session should be cut from
  `origin/main` (the owner's to fetch), or read from a snapshot as this one did.

- **The delta client's integration test does not skip** when its server cannot start, though its header says it does
  (`apps/workspace/src/workingset/deltaClient.integration.test.ts:11-13` against :54-59 and :94-98).
- **Decision 9 also holds every GG2 slice's merge** ("the rest of R4 may be written meanwhile, but it waits to merge",
  about line 41102), so merging GG2b's tables, GG2c or GG2d before WS4b is the owner's exception (the plan says so).

## How these drafts were checked

Two read-only reviewers checked every draft's citations and claims against the snapshot (about 60 defects, every one
fixed in the drafts: wrong lines, a write pattern that does not exist, refusals the real routes do not make, planted
faults that could not turn red). **The drafts have not been read by the owner or a conductor, and nothing in them was
run.** Claims about files outside the snapshot (`packages/ontology`, `packages/adapters`, `harness/`, the lockfile) are
the drafts' own reading through `git show` and were not independently checked.

## Not drafted in this session (in the plan, with no paper yet)

GR1f; GG2f and GG2g; WS4c (only if the budget misses); GG3c to GG3e; GG4f to GG4i; GG5c to GG5f; GA1e;
and PL8b (outside these streams).
