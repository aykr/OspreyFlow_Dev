# GG4b red record (rule 15), 27 November 2026

Every pure test below was first red on the code as it stood, or green there because it keeps today's behaviour,
and then red with a fault planted at the real call site in the shape the code writes it. Plants were applied by a
script that saved each file first and wrote the saved bytes back into the same file (never `git checkout`), run
over `ontology/test_drawn_source_document_withheld.py`, `services/api/working_set/test_drawn_source_document_read_paths.py`,
`services/api/test_drawn_source_note.py`, `adapters/graph_arcadedb/test_drawn_documents_batched_read.py` and
`schemas/test_boards.py`.

## Red on the code as it stood

- `test(boards): GG4b acceptance, red`: 27 failed, 6 passed (rows 2, 8 and 13, which keep today's behaviour).
  Each failure for its own reason: D sent to B in both places (rows 1, 7), kept for A once A may not read it
  (row 3), the older item sent with D (row 10), `source_document` sent beside withheld sources, no batched read.
- The adapter's conformance case (`tests/conformance/graph_port/test_drawn_documents.py`, row 14) was committed
  before any change (rule 1). It needs ArcadeDB, which this seat did not run: **not yet seen red or green
  against a store** (the server's run and the merge's live step).
- GOV.UK reader: the new case answered **502** (the whole board unreadable) and BD11's changed expectation failed.
- React: the inspector said "None: a document of the case" for a note left empty or blank; an item and a link
  with a document and no note were sent; an older item with a readable document was saved with no note; the two
  new keyboard cases failed on those words.

## Planted faults (each turned at least the named tests red)

| Row | The fault planted | Where | Red |
| --- | --- | --- | --- |
| 1, 7, 10 | today's code: no rule | `withhold_sources` | 36: the node and link rows, the older item, the boards route, search (index and fallback), the adapter's read |
| 2 | C's read skipped, the id kept from the author's check alone | `withhold_sources` | 18: "a reader who may read it is sent it", the boards route, snapshot, search |
| 3 | the author's case inverted | `withhold_sources` | 3: "the author keeps it only while the author may read it", the boards route |
| 4, 5, 6, 7 | the rule in `open_board` alone, not in `withhold_sources` | `handling.py` and `Boards.open` | every working-set case of its own: snapshot, replayed and pushed (node and link each), view, search by index and fallback; the boards route stays green |
| 8 | the note blanked too | the rule | 5: the note-only item for every reader, C's own copy |
| 9 | the old body rule kept (a document alone accepted) | `schemas.boards._Asserted` | 5: the route's 422 for item and link; the schema's cases |
| 10 | (today's code above) and, in the React inspector, today's two sentences | `BoardEditor.tsx` | the component and keyboard cases, before the fix |
| 12 | an absent cited id sent (read with more clearance to learn it is absent) | `WorkingSetService._readable_documents` | 4: "every answer to B is the same whether or not D exists", the read count, the failed read |
| 13 | `sources_in_full()` ignored by the new rule | `withhold_sources` | 14: "a read written back keeps D", the edit and working-set writes |
| 15 | one read for each element in place of the batch | `readable_cited_documents` | 4: the read counts for B and C, the one-read case, the adapter's own |
| edited item | only the current document judged | the rule | 7: "edited from one document to another sends B neither", "each judged by itself" |
| one placeholder | a `drawn:` source for each withheld one | the rule | 2: "the sources sent do not say how many" |
| failed read | a failed read keeps what was cited | `readable_cited_documents` | 3 |
| only a Document | any element kept | `readable_cited_documents` | 1 |
| Q2 | the edit's old rule | `Boards.edit` | 2 |
| item 5 | the edit's own read withheld | `Boards._own_item` | 1: the author who may no longer read D erased it |
| item 5 | the working set's seed read not keeping documents | `_seed_ids` | 5 |
| item 5 | the restore's read not keeping documents | `restore` | 3 |
| item 5 | a returning link stored as the writer saw it | `_links_returning_with` | 1 |
| writer | the writer answered with the stored add | `_add` | 5 (re-planted after the line moved: the writer's three cases and the two read counts) |
| publish | the writer's view published | `ExpansionOutcome.to_publish` (since moved to `notify.publish_delta`: see *What is published*, below) | 3 |
| no read | the working set makes no read (C loses D) | `_readable_documents` | 6 |
| adapter | asks with more clearance than the reader's | `_cited_for` | 1 |
| adapter | asks every type, not the Document type | `_documents` | 1 |
| adapter | one read for each record | `_cited_for` | 1 |
| Q3 | the old promotion check | `Promotions._problems` | 1 |

## The dataset half of "may read" (the verifier's finding, round 3)

Every world above gave all its readers the same datasets with D inside one of them, so only the handling half of item
2 was exercised. The new cases put D in a dataset of its own, keep the reader cleared for it, and take that dataset
out of what the reader's case reads after drawing. The code was right and is unchanged: green as written, then each
fault below planted at its real call site, as `principal.model_copy(update={"datasets": ...})`, with `None`
("dropped") or the reader's own datasets plus D's ("widened", the author's reach with the reader's clearance). Each
file's saved bytes were written back into it and its hash checked. Run over the adapter's pure test, the working-set
read paths, `services/api/test_drawn_source_document_datasets.py` (the real app, the case's datasets changed in the
dataset store) and the acceptance test: 67 cases; **the 60 there before (`-k "not dataset"`) stayed green under
every one of these faults.**

| The fault planted | Where | Red |
| --- | --- | --- |
| datasets dropped; datasets widened | `GraphArcadeDBAdapter._documents` | 2 and 2: the adapter's own, `get_nodes` and `get_edges` |
| datasets dropped | `GraphArcadeDBAdapter._cited_for` | 2: the same |
| datasets dropped; datasets widened | `WorkingSetService._readable_documents` | 4 and 4: snapshot, replayed, pushed, and the view, search and writer's answer |
| datasets dropped; datasets widened | the `read` call in `readable_cited_documents` | 7 and 7: those six and the board route |

The adapter's pure fake judged classification alone; it now applies the dataset step as the query carries it, to a
link's ends too (rule 15).

The two store cases (`test_no_read_sends_the_document_to_a_reader_whose_case_no_longer_reads_its_dataset`, every
adapter read; `test_the_working_sets_snapshot_follows_the_datasets_the_readers_case_reads`) were smoke-run over
`BoardGraph` and the fake working-set store (the first over `get_nodes` and `get_edges` alone): green as written, red
with the datasets dropped at `readable_cited_documents`' read. **Not yet seen against a store.**

## What is published, route by route (the verifier's finding on the publishing call sites)

No test drove a route and read what it published. `services/api/test_drawn_source_document_published.py` now does:
through the real app, a writer who may not read D puts the drawn item on the canvas by each route (seed, add by ids,
expand, links among, add by identifiers, a starter question, a shared pair, the ownership and alert canvases, a
restore, an upload), and the message on the case's channel is decoded as a socket decodes it.

**Written first, it found a defect:** the upload case was red on the code as it stood. A route that publishes an add
the Conduit wrote itself (`add_written`: an upload, an accepted finding, an email made a Document, a picture)
published `outcome.delta`, the writer's own view. A stored drawn link that came back with its Document was pushed
without D to readers who may read it (a resync showed it again: what was stored was whole). The other ten routes
were green as written. The nine cases over the routes' own result types were red because a `DeltaAdd` could hold no
stored form.

**The fix, in one place:** a writer's `DeltaAdd` holds the stored one privately (`DeltaAdd.holding`), and
`notify.publish_delta` publishes that (`DeltaAdd.to_publish`). The nine `.to_publish()` call sites in `app.py` are
`outcome.delta` again, as they were before this slice: no route chooses, so none can choose wrongly.

Planted at each real call site, over that file and the working-set read paths (46 cases), each file's saved bytes
written back into it and its hash checked:

| The fault planted | Where | Red |
| --- | --- | --- |
| the writer's view published alone (the add rebuilt from its own fields, which holds nothing) | each of the ten add routes' own `publish_delta` line in `app.py`, one at a time | that route's case each time (the seed route's also the push to a reader who may read D: 2) |
| the restorer's response published | `restore_history_step` | 1: the restore case |
| what is given published | `notify.publish_delta` | 20: every route but the restore, the push, and all nine result types |
| the writer's view holds nothing | `WorkingSetService._add` | 15: the same routes and push, and four working-set cases |
| the add rebuilt | `WorkingSetService.links_among`; `add_written` | 1 each: the links-among case; the upload case |

The eight other `add_written` routes are not each driven through the app: they publish through the same
`publish_delta`, and a case over each route's own result type shows the stored add survives being held in it.

## Owed at merge: the two guides (their versions and PDFs are set at merge)

Left unchanged here: a guide's content changes only with a new version row and its PDF printed again
(`tools.docs_pdf`), which the guides' histories record as done at merge. The lines to write:

- **User guide**, the board's **Drawing** passage, in place of "a source note, a document the case holds, or both.
  Without a source it says "Give a source note or choose a document of the case: where this comes from."":
  "where it comes from: a source note, to which you may add a document the case holds. Without a note it says
  "Give a source note: where this comes from. A document of the case may be added to it." An item drawn before a
  note was required gains one at its next edit, and can be promoted only once it has one. The document is shown with
  the item only to someone who may read it; anyone else sees the item without it, and an item with no note says "No
  source note was given"."
- **Developer guide** §7.5, before *For a new writer*: "**A drawn item's cited document** (ADR-143 Amendment 8). A
  drawn element's sources and assertion may cite a Document, sent only to a reader who may read it when it is sent.
  `withhold_sources` takes the result of one batched read for the answer,
  `ontology.handling.readable_cited_documents`, and given none it withholds every cited document. A read that fills
  the working set, or whose result is written back without `sources_in_full()` (a drawn item's own edit), runs
  inside `ontology.handling.cited_documents_kept()`; otherwise a writer who may not read a document would erase it."

## Not run by this seat (a store is needed)

`tests/conformance/graph_port/test_drawn_documents.py` (ArcadeDB) and `test_drawn_documents_read_paths.py`
(ArcadeDB and Valkey: rows 4 to 7, 12 and 15 live, row 15's 800 ms). Six of their cases (all but the budget case
and the two that call every adapter read) were smoke-run here over `BoardGraph` and the fake working-set store,
which caught two faults in the tests themselves (a marking the scheme does not have, and a sort of `None` beside
text), both fixed. A smoke run is not a store run.
