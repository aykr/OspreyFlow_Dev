# Away-round drafts of 27 November 2026 (D246, the server's build account)

**Status: drafts, not ruled.** Written overnight on 26 to 27 November on the branch `drafts/2026-11-27` in
`~/away-drafts-27`, which was cut from `origin/main` at `7f4f9554a`. Every citation was read from that tree, and from
the away branches (`away/GG2a`, `away/GG2c`, `away/GG3b`, `away/GG4a`, `away/GG4b`, `away/GG5a`, `away/GR1d`,
`away/WS4a`, `away/WS4b`). **Re-read every line before cutting.**

Nothing is pushed or merged, and nothing is written outside this folder. No row is in `slices.tsv`. No decision record,
Makefile, CI file, `osprey.yaml` or `data/` was touched. **No test was run and no container was started** (docs only:
another session was measuring speed on this machine). All data named is synthetic and the client is not named.
`make client-name-check` was not run, because it needs the owner's hash list, which is not on this machine.

**What these drafts cover.** Every slice of the 26 November plan that was not yet drafted
(`drafts/2026-11-26:…/drafts_2026-11-26/CHAIN_PLAN.md`), split as the plan says. They are in the order of what unblocks
most. **Release scope A-full (D273): every slice below is in 0.7.0.**

## Rulings these drafts build on (RULINGS.md, 26 November)

- **GR1a question 1 is (a), the query form.** Every case page is `/cases…?case=<id>&…`, so **GR1c is withdrawn**.
  Where a draft needs a page of its own, it proposes a new `FUNCTIONS.yaml` row, as GR4a's board page got.
- **The Matrix is GG2d's.** It is not in GG4h.
- **"Who made it" is left out for 0.7.0**, and this includes the authors of notes (GG3d1) and of promotions (GG4f3).
- **GG4b (b)** (re-read the document with the reader's principal) and **GG4j** (the ceiling) are cut. GG4f's drafts wait
  on both.
- **Decision 9: only GG2c merges before WS4b.**
- **Sigma 4: carry on.**
- **Every non-owner proposal of 26 November is ruled (a).**

**Two conventions this session applied in every draft (the conductor's to confirm):**

1. **Starting early and merging early are marked differently.** Starting a slice earlier than the plan's rows allow is
   a plain question with a proposed (a); it is not one of D274's owner grounds. Each such start is flagged below.
   Merging before WS4b against decision 9 is marked **owner**, because it departs from a decision record.
2. **Ids appear only where the reader cannot see them.** An id may travel in a hidden field or in the address's query
   string (the ruled query form), never in visible text.

## The drafts, their questions, and what each waits on

The proposal for each question is in the draft. A question marked **(owner)** falls under one of D274's grounds:
security, keys or credentials, a decision-record or ADR change, a CI or protected file, widening a permission, or
client-facing scope. Every other question has a proposed (a) that a builder can follow if the owner says "A".

| Draft | What it proposes (size) | Its questions (owner ones in bold) | Waits on |
| --- | --- | --- | --- |
| **GR1: case settings** | | | |
| [GR1f1.md](GR1f1.md) | A case's settings, read-only, at `/cases?case=…&settings=1`. It shows what the case reads (by `datasetLabel`, the name and then the id, as ADR-099 Amendment 6 requires), its domain models, and who can open it (S to M) | 1 the address; 2 the order of the reads; 3 a reader without `share_case` sees only their own level; **4 (b) names without ids would depart from ADR-099 Am. 6 (owner)**; 5 the domain models' sentence moves to `glass-shared`; 6 the grantees are shown by display name; 7 the access history is left out of 0.7.0; **8 two Author-only reads write no audit row (owner, security)** | GR1a (merged); GR1d and GR1b merged first (the same `cases.ts` files) |
| [GR1f2.md](GR1f2.md) | Changing who can open a case, as forms: give, change and take away a level, and the unit-wide level (M) | 1 scope; 2 offered to an Author holding `share_case`; 3 an account id field (**(b) a person picker would widen what a page can list (owner)**); 4 the levels offered; 5 removal confirmed by a `POST`; **6 the last Author grant: as in the React panel, no Remove and no lowering offered; a Conduit guard would be (c), an ADR-052 change (owner, access control)**; 7 refusals in words; 8 a banner after a change; 9 removing an id that holds no grant | GR1f1; GR1d |
| [GR1f3.md](GR1f3.md) | Changing what a case reads, as a form; its domain models are stated, not offered for change. Renaming and removing a case are left out: they are not in the plan's row (S) | 1 scope; 2 radios by `datasetLabel`; 3 one sentence on what a change does; 4 a dataset's home case (409 `home_case_kept`); 5 refusals; 6 a banner | GR1f2 |
| **GG3: documents, timeline, inspector** | | | |
| [GG3c.md](GG3c.md) | The case's timeline at `/cases/timeline?case=…`: a density chart and a weekday-by-hour grid, each a plain SVG chart followed by a table (M) | 1 scope; 2 start after GG3b, without GG2b and PL8b (**an early start, flagged**); 3 the address; 4 a coarser bucket above 400 rows, never a cut; 5 empty periods said, not listed; 6 each day's share; 7 a list-returning "events elsewhere" helper; 8 no panel frame yet; 9 brush and playback later | GG3b merged |
| [GG3e.md](GG3e.md) | Adding one file to a case on GG3b's page, streamed to the Conduit (M) | 1 one file, no holder; 2 on `/cases/document`; **3 the file streamed through the forwarder's translation: this moves the upload's anti-forgery boundary and changes the forwarder's allow-list (owner, security)**; 4 markings up to the reader's clearance; 5 the legal basis is required; **5b where the legal basis is kept: today only the audit log holds it (owner)**; 6 refusals, including 409 `drawn_not_loaded`, in the route's own order; 7 offered from `extract_files` and the Editor level; 8 a `303` to the reader | GG3b merged; the owner on question 3 |
| [GG3d1.md](GG3d1.md) | The inspector's reads on GG2e's live page: a node's properties and shared contacts; a link's details, history, events and notes (M) | 1 scope; 2 on the live page, not a saved view (a link's notes need the working set); 3 one view model in `glass-shared`; **4 (b) a Conduit read of one node or link (owner: an amendment, decision 11)**; 5 shared contacts by link type; 6 events 50 to a page; **7 no author shown on notes (the ruling); (b) showing them would narrow the ruling (owner)**; 8 strength, risk and picture left out; 9 keyboard | GG2e, PL8b, GG3b, GG3c; merges after WS4b |
| [GG3d2.md](GG3d2.md) | The inspector's writes: notes as server forms, and the link change drawn by the module from its store (M) | 1 scope; 2 who draws each write (**(b) needs GG3d1's question 4 (b), the owner's amendment**); 3 offered from the reader's rights; 4 lowering a link's handling needs a confirmation; 5 only the type's own fields; 6 a sentence for each refusal, including `drawn_on_its_board` and `composite_read_only`; 7 removing a note is confirmed; 8 a warning about the note's marking | GG3d1; merges after WS4b |
| **GG2: the working set's writes and the canvas** | | | |
| [GG2f1.md](GG2f1.md) | Seeding the live working set from a search hit, expanding with a preview and the 500 gate, links among, and the cap refusal in `spec/02`'s words (M) | 1 scope; 2 seed through `add-by-ids` (only `spec/03`'s words change); 3 a scripts-off seed form; 4 the module applies only the stream's delta; 5 preview and gate; 6 the cap sentence moves to `glass-shared` and replaces `linksAmong.ts`'s raw copy; 7 the graph is unchanged while the refusal is open; 8 what is offered at each level; 9 no justification asked; 10 `clusters` ignored; 11 merge together with GG2f2, so *Run as a batch job* never shows unusable | GG2e, GG2c, CO3, GG3a, GR1d, GG2f2; merges after WS4b |
| [GG2f2.md](GG2f2.md) | The cap's third choice: a batch expansion started, followed and opened; and adding many by a pasted list (M) | 1 scope; 2 `/cases/graph/batch?case=…&job=…`; 3 starting it by form; 4 following it, one `GET` per render; 5 the result opens GG2b's view; 6 refusals use the route's `words`; 7 NEXT_BATCH's batch-words alignment has no owning slice now: a backlog row; 8 adding by list, at most 5,000 ids, refused in words above that and never cut; **9 (b) merging the add-by-list page before WS4b (owner: decision 9)** | GG2f1, GG2b, GR1d; merges after WS4b |
| [GG2g.md](GG2g.md) | The canvas's editing actions, split into GG2g1 (selection, menu, hiding links, save the selection as a view), GG2g2 (drag, layouts, remove, clear), GG2g3 (groups) and GG2g4 (the suppression mark; drawn items dashed and read-only) (L, 4 parts) | 1 the split; 2 every gesture has its keyboard id; 3 positions kept in the browser; 4 remove and clear; 5 the groups worker moves to `glass-shared`; 6 ids that belong to other rows are left to them; 7 the suppression mark (needs `edit_graph`); **8 *Edit on board* offered only to the drawn item's author (a drawn element's board id reaches no one else): this narrows ADR-143 C15, so it needs a C15 amendment diff (owner)**; 9 save as a view | GG2f1, GG2e, GG4a; the owner on question 8; merges after WS4b |
| **GG4: boards, extras, query builder, metrics** | | | |
| [GG4f1.md](GG4f1.md) | A board's drawn watches, and *Looks like a loaded item* decided by form (M) | 1 scope; 2 parts of GG4a's page; 3 every reader of the board is shown the suggestions; 4 the React sentence; 5 the React sentence when `more` is set; 6 a confirmation before *Same*/*Not the same* (no undo route); 7 a "Watched" column, the alert decided by the watch's `owner`; 8 the alert itself is not in this slice; 9 a creator below Editor level; 10 refusals in words | GG4c, GG4b, GG4j merged; GG4d's words |
| [GG4f2.md](GG4f2.md) | A drawn item's picture, shown, uploaded, or chosen from the board's own image Documents (M) | 1 scope; 2 a page route, then a `PUT` (`conduit.ts` lacks only a raw body); 3 an `<img>` through the forwarder; **3b a "picture" Document with a `.pdf` file behind it would be served inline: `choose_picture` checks only `media_kind`, and `picture_file` serves the file by its extension (owner, security: a Conduit part)**; 4 the file's own type; 5 the markings offered; 6 the size limit in words; 7 choosing from the board's own pictures; 8 refusals | GG4f1; GG4c, GG4b, GG4j; whichever of GG3e or GG4f2 lands the raw body; question 3b |
| [GG4f3.md](GG4f3.md) | *Promote…* from a board, scripts off: the sheet, the ticks, one load, and *Promotions from this board* (M) | 1 scope; 2 the sheet at `&promote=1`; 3 checkboxes; 4 warnings said as they come; 5 the banner; 6 who proposed and who reviewed: not shown (the ruling); 7 the revert command never shown; 8 refusals in the route's words; **8b the deployment ceiling's refusal names the marking (`promotions.py:204`); does the GG4j ruling cover it? (owner, security)**; 9 more than 500 ticked is refused before sending | GG4f2; GG4c, GG4b, GG4j; question 8b |
| [GG4g.md](GG4g.md) | Explore's figures and *Find connections*, read-only, scripts off, on two pages (a new `find-connections` row) (M) | 0 start before GG2e and GG3 (**an early start, flagged**); **0b merging before WS4b: the plan counts GG4g among the pages decision 9 holds (owner: decision 9)**; 1 scope; 2 two pages; 3 paging by the route's offset; 4 a node as text until GG3d; 5 loads said without the recipe id (rule 7); 6 groups past the cap: both figures, no choice that cannot be taken; 7 From and To in two steps; 8 the degrees (the default reach is 6); 9 a route in words; 10 link types later | GR1a, GG3a; question 0b |
| [GG4h.md](GG4h.md) | The Ownership view and due diligence, read-only (a new `ownership` row) (M) | 0 start before GG2e (**an early start, flagged**); **0b merging before WS4b (owner: decision 9)**; 1 scope; 2 the address (the `matrix-ownership` row narrowed to the Matrix); 3 offered only to a reader holding `trace_ownership` (pattern: `studio.ts:207`); 4 which entities are traced; 5 the threshold; 6 the owners table; 7 due diligence; 8 the route's "too complex" refusal in its own words; 9 ids | GR1a; GG2d (the same row); question 0b |
| [GG4i1.md](GG4i1.md) | The query builder at `/cases/patterns?case=…`: a pattern drawn by forms, its count first, the set it found, and adding the set to the graph (M) | 1 the address and the row; 2 a pattern as numbered parts; 3 pinning by a search step; **4 a large run: never sent at or above the cap; (b) a Conduit read of a job's result (owner: an amendment and a security part)**; 5 the second root checked first; 6 one table of items (no links table: `match()` returns no links); 7 add to the graph; 8 Ask to search later (GG4i1b); 9 saved patterns; 10 conditions; 11 the estimate's words | GR1a, GG3a, GG2f1 (so merges after WS4b unless question 7 (b)) |
| [GG4i2.md](GG4i2.md) | Metrics on GG2e's live page: ranking, comparing, and the relay group by the Clique Metric (M) | 1 the `metrics` panel; 2 labels from the store, never an id; 3 every item ranked, 20 to a page (React cuts silently at 20: rule 2); 4 A8's mentions; **5 (b) a Conduit read of a job's result (owner)**; 6 offered with `run_analysis`; 7 communities later; 8 Clique bounds; **9 a parity-line wording, only if GG2e's ruled line does not cover a panel (owner)** | GG2e, GG2e2, GG2c, PL8b, GG2f1; merges after WS4b |
| [GG4i3.md](GG4i3.md) | Match strictness by form, the change stated in figures, and why a group was shown as one (M) | 1 a part of GG2e's page that works scripts off; 2 a setting other than the three; 3 the change in words; 4 the form warns that the change reaches every reader; 5 Editors only; 6 the explanation opens from the selection; 7 the pairs table; 8 a stale group; 9 manual same-as and split stay in GG3d2 | GG2e, GG2e2, PL8b; merges after WS4b |
| [GG4i4.md](GG4i4.md) | The cross-filter, split into GG4i4a (the filter in the address and the facets, scripts off, on GG3c's and GG5c's pages) and GG4i4b (graph dimming and A7's add, after WS4b) (L, 2 parts) | 1 the filter in the address; 2 the split; 3 several cells by checkbox; 4 which facets; **5 a bucket that names a node: waits on GG5c question 2; (b) is an amendment (owner, security)**; 6 the graph's dimming; **7 A7's add reads ends a reader may not read, and `not_shown` would count them: waits on GG5c question 2 (owner, security)**; 8 "Nothing matches this filter"; 9 a refused field | 4a: GG3c, GG5c, GG5c question 2. 4b: GG2e, GG2f1, GG4i2, the same ruling; merges after WS4b |
| **GG5: map and site plans** | | | |
| [GG5c.md](GG5c.md) | The heat layer and the hotspot cells on the case map, with tables for scripts off (M) | 1 counted over the saved view (the fixture view must hold every cell and incident for A2's share); **2 a visible event whose end the reader may not read: no conformance case plants this; it is written first, and the slice stops if it is red (owner, security, rule 3)**; 3 a cell named from the view's nodes, never by id; 4 two tables; 5 one precision constant; 6 "Show only this cell"; 7 colours from the tokens; 8 one read per render | GG5b built; GG2b's saved view; question 2 |
| [GG5d.md](GG5d.md) | The boundary filter (drawn by pointer, keyboard or form) and the gazetteers (M) | 1 place search as a `GET` form; 2 gazetteers added and removed on the map page; 3 the four empty states; 4 the React refusal sentences; 5 the boundary by pointer and keyboard; 6 typed points when scripts are off; 7 the boundary filters the view's places; 8 stored boundaries left out (no route calls `list_boundaries`) | GG5b built; runs after GG5c (they share the page's files) |
| [GG5e1.md](GG5e1.md) | Site plans: uploaded, calibrated by four control points, given a grid, and viewed over the map, at `/cases/sites?case=…&site=…` (M to L) | **1 how the upload is carried: (a) a new path for untrusted file bytes, (b) a wider forwarder allow-list (owner: security and widening)**; **2 no route lists a case's sites (owner: an amendment)**; **3 a site plan carries no marking (owner, security)**; 4 a page of its own and a new row; 5 a point on the image without scripts; 6 a point on the map; 7 four points, one step each (the Conduit stores a crossed plan: a finding); 8 the grid (`GridRequest` has no bounds: a finding); 9 the plan drawn without `blob:` | GG5b; GG5d's key route; the owner on questions 1 to 3 |
| [GG5e2.md](GG5e2.md) | A site plan's rotation and pitch, by buttons and keys, and stated in words when scripts are off (S) | **1 D48's words are not in the repository; the answer goes into `spec/02` first (owner, client-facing scope)**; 2 `planBearing` in `glass-shared`, which detects a mirrored plan; 3 the buttons as the keyboard route; 4 a sentence when scripts are off; 5 the bearing and pitch kept in the address | GG5e1, GG5d; question 1 |
| [GG5f.md](GG5f.md) | The graph over the map: a saved view's located nodes and their links, drawn by Sigma 4 through `@sigma/layer-maplibre` 4.0.1 (M) | 1 the layer replaces GG5b's circles; 2 `MAP_SIGMA_SETTINGS` moves to `glass-shared`; 3 the look, judged by WS4a's comparison; 4 the allow-list reads a scoped package's first two path segments (it now passes every `@sigma/*`); 5 the version pinned exactly; 6 no turning or tilting with the graph layer (the package locks both); **7 (b) a map budget gate (owner, CI)**; 8 tables when scripts are off | GG5b, GG2b; WS4a merged; WS4b merged, and WS4b's questions 1, 2, 3 and 8 |
| **GA1: Ask & Chat** | | | |
| [GA1e.md](GA1e.md) | *Show all on graph* and *Save as a view* under an answer (S) | 1 the form carries only the answer's id; 2 one `add-by-ids`, then the items selected on arrival; 3 offered by the level and `GET /v1/me/rights`; 4 the save form; 5 the merge order; 6 both forms work without scripts | GA1a, GG2e, GG2f1, GR1d, GG2b; merges after WS4b |

## The owner's questions in one list

None of these was guessed. Each draft gives the options.

1. **Security.**
   - GR1f1 Q8: reads with no audit row.
   - GR1f2 Q6: the last Author grant.
   - GG3e Q3: the upload's anti-forgery boundary and the forwarder.
   - GG4f2 Q3b: a "picture" served as a PDF.
   - GG4f3 Q8b: the deployment ceiling's words against GG4j.
   - **GG5c Q2: a visible event whose end the reader may not read. GG4i4 Q5 and Q7 wait on it.**
   - GG5e1 Q1 and Q3: the upload path, and a site plan with no marking.
   - GG4i1 Q4 (b) and GG4i2 Q5 (b): a Conduit read of a job's result.
2. **Decision-record and ADR changes.**
   - GR1f1 Q4 (b): departing from ADR-099 Amendment 6.
   - GR1f2 Q6 (c): ADR-052.
   - GG2g Q8: an ADR-143 C15 amendment.
   - GG3d1 Q7 (b): narrowing the "who made it" ruling.
   - Merges before WS4b against decision 9: GG2f2 Q9 (b), GG4g Q0b, GG4h Q0b.
3. **Amendments under decision 11** (each a diff file):
   - GG3d1 Q4 (b), which GG3d2 Q2 (b) also needs;
   - GG3e Q5b;
   - GG4i4 Q5 (b);
   - GG5e1 Q2.
4. **Widening a permission.** GR1f2 Q3 (b): a person picker.
5. **CI.** GG5f Q7 (b): a map budget gate.
6. **Client-facing scope.** GG5e2 Q1: what D48 asks for.
7. **A parity-line wording.** GG4i2 Q9, only if GG2e's ruled line does not cover a panel.

**Early starts flagged for the conductor** (plain questions, each with a proposal): GG3c after GG3b without GG2b and
PL8b; GG4g before GG2e and GG3; GG4h before GG2e.

## Findings on the way (for the orchestrator; no file outside this folder was changed)

**Spec gaps and contradictions (rule 11):**
- `spec/03:550` and `:593`, `services/api/patterns.py:79` and `supersede.py:47` name `GET /v1/jobs/{id}/events`. No
  Conduit route serves it, so a job-sized pattern run or metric can never be read back.
- `spec/03:403` says no Share panel is built in the Glass; `spec/02:878` says one is.
- `FUNCTIONS.yaml:257` gives B21 to `graph-extras`, but B21 is the pathfinder (`spec/08` :572), not *Find connections*.
- NEXT_BATCH question 9 (`NEXT_BATCH_2026-11-24.md:45`) gave the batch-words alignment to GG2d, which is now the
  Matrix. No slice owns it any more.
- N19-07 was renumbered N22 (`backlog/N16_N22_RENUMBERED_2026-11-21.md:15`).

**Conduit and adapter defects found by reading (none fixed; each is a later part):**
- No length limit on a case's name, either at creation or rename (`services/api/app.py:4216`, :4455;
  `investigations.py:532-545`). This also concerns GR1b.
- Nothing in the Conduit stops removing the last Author grant (`investigations.py:405-427`). Only the React panel hides
  the button.
- Some reads write no audit row:
  - `GET .../access` and `GET .../datasets` (`app.py:4573-4592`, :4324-4329);
  - link history, events and notes (`app.py:7749-7751`, :7768-7769, :8740-8741).
- The upload route records `legal_basis` in the audit log only (`app.py:7907-7934`).
- An unpinned second root raises a bare `ValueError`, which reaches the caller as a 500
  (`graph_arcadedb/builders.py:929-935`).
- `match()` always returns no links (`graph_arcadedb/adapter.py:1318-1324`).
- A hotspot bucket's label is a node id (`analytics_duckdb/adapter.py:461`).
- A 7-day histogram's buckets start on a Thursday, because they count from the Unix epoch
  (`analytics_duckdb/adapter.py:422`).
- `set_site_control_points` accepts a crossed plan (`app.py:10272-10287`), and `GridRequest` has no bounds
  (`app.py:10192-10195`).
- A mirrored site plan passes `formsASimpleQuadrilateral` (`site/bilinear.ts:89`).
- `choose_picture` checks only `media_kind` (`boards.py:1139-1147`), while `picture_file` serves the file by its
  extension (GG4f2 Q3b).
- `may_draw` does not check the Editor level that the drawing routes require (`boards.py:450`, `app.py:5051`, :5263).
- The ownership routes need `TRACE_OWNERSHIP` but not `INVESTIGATE`, and a Data Engineer does not hold it
  (`rights.py:116-123`).
- The pathfinder's audit row has no `investigation_id` (`app.py:9183-9188`).
- No route lists a case's events, a case's sites, or a case's documents. No route calls `list_boundaries`. No route
  reads a node by id.

**The React workspace today:**
- `MetricsPanel.tsx:238-242` cuts its ranking to 20 with no words (**rule 2**). `:102-106` labels a row with a raw id.
- The boundary tool and the site wizard have no keyboard route (`siteLayer.ts:138-150`; none in `MAP_VIEW_ACTIONS`,
  `actionRegistry.ts:992-998`) (**rule 13**).
- The query builder shows a run's count, never its set (`QueryBuilderPanel.tsx:265-271`).
- No Glass client sends `value_filters`, so A7's item-category filter is offered nowhere.
  `test_phase8_exit_over_the_wire.py:462-477` still calls it a "Known gap".
- The access panel has no words for 409 `no_such_team` or `service_account` (`investigation/access.ts:27-32`). The
  shared link-change client says `drawn_on_its_board` and `composite_read_only` as "failed" (`linkChangeApi.ts:89-114`).
- C15's *Edit on board* is not built.

**The page service:**
- `readUploadForm` holds every file in memory (`apps/pages/server/upload.ts:1-10`), which does not fit a 512 MiB file.
- `conduit.ts:28` sends GET, POST, PUT and DELETE with JSON bodies only. GG4d's change route needs `PATCH`, which its
  draft does not say.
- The allow-list check on `away/GG2a` (`assets.mjs:195`) matches only a scoped package's first segment, so allowing one
  `@sigma/*` package allows them all (GG5f Q4).

**`@sigma/layer-maplibre` 4.0.1 locks pitch and rotation** (`away/WS4b`'s `MapView.tsx`), so no map with the graph layer
can turn or tilt.

**Earlier papers:**
- GG3a's out-of-scope note (`slices/GG3a.md:48`) still gives adding to the working set to GG2b. The plan now gives it to
  GG2f1.
- GG5b's draft cites `test/govuk/csp/map.spec.ts`; GG5a built `apps/pages/test/csp/map.spec.ts`.
- **Scenario CS's numbering collides:** GR1b extends CS "from CS16", and `away/GR1d` already uses CS16 to CS32. Whichever
  merges second renumbers.

## How these drafts were checked

Each stream's drafter wrote its drafts. Three read-only reviewers then checked every draft's citations, claims, owner
marks and planted faults against `origin/main` and the away branches. They found about 80 defects. Each drafter
checked every one against the code before fixing it, and all were confirmed and fixed:

- wrong lines;
- refusal codes and statuses the routes do not send;
- a refusal invented by a fixture;
- access-control faults planted in the fixture instead of at the page's call site (rule 15);
- missing dependencies;
- a scope wider than the plan's row;
- a question that departed from ADR-099 Amendment 6 without saying so.

**The drafts have not been read by the owner or a conductor, and nothing in them was run.**

## Not drafted

WS4c (only if the budget misses); PL8b's further parts (PL8b is drafted on `origin/main`); GR1c (withdrawn: GR1a
question 1 is (a)).
