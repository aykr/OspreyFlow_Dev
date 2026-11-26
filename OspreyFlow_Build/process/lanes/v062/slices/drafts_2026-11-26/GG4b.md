# Slice GG4b · GG4 · A drawn item's source document is never told to a reader who may not read it, on any read path; the board's ceiling is told only to a reader cleared for it (security, a Conduit part; a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **A security part: every question
below is the owner's, and nothing in it is accepted narrower.** It changes the Conduit, which ADR-152 decision 11 admits
only by an amendment (`spec/06_DECISIONS.md` about lines 41136 to 41160: "Anything else found needed comes back to the owner
as an amendment"), so **its decision-record text is a diff file, written with the slice, never an edit to `spec/06`.** The
owner may number it as an SE part, as SE7c was for the assessments finding.

**Where it comes from.** GG4a's away report (`away/GG4a`, `OspreyFlow_Build/process/lanes/v062/away/GG4a_AWAY_REPORT.md`,
questions 1 and 4) stopped one row under rule 3: "`open_board` sends each drawn item's `source_document` identifier to
every reader of the board". GG4a built the conservative reading (no document is said, by identifier or by kind) and
named the leak that remains: "a drawn item must have a note or a document, so 'No note given' still implies a document".

**This draft finds the leak wider than the board route** (read on `origin/main` at `042c882f2`):

- The document's id is carried twice in a drawn element's provenance: `DrawnAssertion.source_document`
  (`services/api/boards.py:466`) and the element's first source, `SourceRef(document_id=given.source_document or
  f"drawn:{item_id}")` (:471-479).
- Every read path sends an element through `ontology.handling.withhold_sources`
  (`packages/ontology/handling.py:335-346`): the graph adapter's serialisation
  (`packages/adapters/graph_arcadedb/serialization.py:173`, :202), the working set's snapshot and deltas
  (`services/api/working_set/service.py:437`, :449, :565, :568; `working_set/models.py:128-129`, :238), link changes
  (`services/api/link_changes.py:187`) and the search index (`services/search_index/document.py:97`).
- `withhold_sources` blanks a drawn element's `board_id` for everyone but its author (`_board_as_known`,
  `handling.py:385-397`), and blanks `sources` only "where its sources are not within the case" (:342-345). A drawn
  item lives in the case's own analyst layer, so its sources are within the case, and **its `source_document` and its
  `SourceRef.document_id` reach every reader of the case by every one of those paths**, not only `open_board`.
- The check that the document exists is made **once, at drawing, with the author's principal**
  (`_source_document_check`, `boards.py:498-506`, called at :527, :591 and :706). Nothing checks the reader.
- **The ceiling.** `open()` sends `ceiling = await self.ceiling(board.case_id)` (`boards.py:437`, :449). `_ceiling_of`
  takes the strictest marking of the case's datasets with no reader filter (:179-193). Only `markings` is cut to the
  reader (:330-335, :448). So a reader below the ceiling is told the name of a marking above their clearance.

## Acceptance (red before, green after)

The slice is done when the four tests below were each **seen red on `origin/main` as it is**, and are green after, with
the leak test and every existing board and working-set test still green:

1. `test_a_drawn_items_source_document_is_not_sent_to_a_reader_who_may_not_read_it` (open_board), red today.
2. `test_the_working_set_never_sends_a_drawn_items_source_document_its_reader_may_not_read` (snapshot and delta), red
   today.
3. `test_search_never_returns_a_drawn_items_source_document_its_reader_may_not_read`, red today.
4. `test_the_boards_ceiling_is_not_named_to_a_reader_below_it`, red today.

## Questions for the owner (the proposal first; all four are the owner's, security)

1. **What a reader who may not read the source document is sent.** (a) **The drawn item, without the document**:
   `drawn.source_document` and the source's `document_id` blanked (the source kept as `drawn:<item_id>`, as for an item
   drawn from a note alone), on every read path, **in `withhold_sources` beside `_board_as_known`**, so one place serves
   every path, as for the board's id. The author keeps it only while the author may still read the document (question
   2). (b) **The drawn item hidden in full** from that reader, with its links and from every count, as a judgement whose
   evidence a reader may not read is hidden in full (ADR-046). That closes question 3's inference too, but it is a new
   access rule in the adapter's traversal, not a projection. (c) The board route alone (GG4a's question 1 (b) as asked).
   **Not proposed:** the working set and search would still send it.
   **Rule 3 and (a).** Rule 3 puts access control in the adapter, never in the Conduit after retrieval.
   `withhold_sources` is "the adapter's serialisation and the working set's projection" (`handling.py:385-397`'s
   docstring: "Every read path is sent elements through here"), and (a) withholds a field of an element the reader may
   already see, as `_board_as_known` does for `board_id`; it changes no traversal, degree or count. Whether a field
   withheld there satisfies rule 3, or only (b)'s traversal-level rule does, **is the owner's to say.**
2. **How "may read the document" is decided, since `withhold_sources` is a pure function of the element and the
   principal.** (a) **Recorded at drawing, checked at read:** the drawn assertion stores the document's handling (its
   marking and datasets) beside its id, taken by `_source_document_check`'s own read, and `withhold_sources` keeps the id
   only for a reader who passes `principal_may_view` on that handling and `sources_within_case` on its datasets (the two
   rules `handling.py:300-315` already applies). No new read on any path. A document whose marking is later raised is
   handled by question 4. (b) A read of the document with the reader's principal on every path that sends a drawn item:
   exact, but one more store read per element on the working set's hottest path. (c) Only the author ever sees it: the
   simplest, and it also hides it from a reader who may read the document.
3. **The inference GG4a named** (a drawn item needs a note or a document, `packages/schemas/boards.py:55-59`, so an item
   with no note implies a document). (a) **From this slice on, a drawn item needs a source note** (the document becomes
   an addition to the note, never in place of it); an item already drawn with a document and no note is shown to a
   reader who may not read the document with the words "No source note was given", the same words as any item
   whose note is empty, and the GOV.UK page never says "no note" in a way that differs between the two. **This
   changes ADR-143 decision 4 and is written in the same diff file.** (b) Question 1 (b)'s hiding in full, which closes
   it without a schema change. (c) Accept the inference: the reader learns that some source exists, not which.
4. **A document whose marking is raised after drawing.** (a) **The recorded handling is the document's at drawing; a
   later change is caught by the next reconciliation**, the same sweep that re-reads drawn items' markings today, if one
   exists. The builder reads whether it does; **if none exists, that is a stop**, not a design for this slice. (b) Re-read
   the document on every read (question 2 (b)).
5. **The ceiling.** (a) **Sent only to a reader whose clearance is at or above it; to anyone else the field is the
   highest marking the reader may hold among the case's datasets**, so the drawing form offers the same choices and the
   reader learns nothing above themselves. `markings` is already cut (:448). (b) The field removed from `BoardOpened`
   for everyone but the creator: a generated-type change that GG4a's page reader and census must follow. (c) Leave it:
   a marking's name is not the data (GG4a question 4 (b)).
6. **The decision record.** (a) **An ADR-143 amendment and an ADR-152 decision 11 row (X9), as one diff file**
   (`GG4b_ADR-143_amendment.diff`), written first and approved before the code merges. (b) Your words.
7. **Who builds it, and where it is judged.** (a) **A security part like SE7c**: the conformance suite's case first
   (rule 1), judged by the verifier, the server and the full gate, never accepted narrower. (b) Inside GG4d, the slice
   that first offers a source document on a form. Not proposed: GG4d is a page slice.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

The worlds are the leak test's synthetic worlds with a third reader: **A** drew an item citing document **D** (marked
above **B**'s clearance); **B** reads the case but may not read **D**; **C** reads the case and may read **D**.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | B opens A's shared board | the item, with no `source_document` and no `SourceRef.document_id` naming D (the source is `drawn:<item_id>`) | today's code: red as it stands |
| 2 | C opens the same board | D named, as today | the id blanked for every reader but the author (question 2 (c) planted, to show the case tells the readings apart) |
| 3 | A opens it | D named | `_board_as_known`'s author test inverted |
| 4 | B's working set holds the item (snapshot on connect) | no D in the frame | the new rule put in `open_board` alone (question 1 (c)), not in `withhold_sources` |
| 5 | A delta carrying the item reaches B | no D in the delta | the new rule put in `open_board` alone (question 1 (c)), not in `withhold_sources` |
| 6 | B searches for the item's label | the hit, with no D | the new rule put in `open_board` alone (question 1 (c)), not in `withhold_sources` |
| 7 | B reads a link drawn from the item to a loaded node | no D on the link | the new rule put in `open_board` alone (question 1 (c)), not in `withhold_sources` (a drawn link carries the same provenance) |
| 8 | An item drawn from a note alone | unchanged for every reader | a note blanked as well |
| 9 | Question 3 (a): a new item with a document and no note | a 422 from the body's own validation (FastAPI's default answer, `{"detail": [...]}`, with no error code: `app.py` has no handler for it), said in words by the page; the existing coded refusal for a missing source, `no_source`, is the edit route's (`boards.py:720-727`) | the schema's old rule kept |
| 10 | Question 3 (a): an old item with a document and no note, read by B | "No source note was given", byte for byte the same as an empty note | a different sentence for the two |
| 11 | Question 5 (a): B opens a board whose case's ceiling is above B | `ceiling` is B's own highest; `markings` unchanged | today's code: red as it stands |
| 12 | The leak test over the same worlds | green, and B's every board answer is the same shape whether or not D exists | a field present only when D exists |
| 13 | `sources_in_full()` (a read written back) | D kept, so a writer does not rebuild the provenance without it | the scope ignored by the new rule |
| 14 | The conformance suite (rule 1) | the adapter's own case of 1 and 7, written before the change | the case added after the code |

## Files touched

`packages/ontology/handling.py` (`_board_as_known` beside a new `_drawn_source_as_known`); `packages/schemas/boards.py`
(the recorded handling on `DrawnAssertion`, and the note rule if question 3 (a)); `services/api/boards.py`
(`_provenance`, `_source_document_check`, `open`'s ceiling); the generated TypeScript (`packages/schemas/generated/`);
tests under `OspreyFlow_Build/tests/services/api/` (boards, working set, search), the adapter's conformance suite and
the leak test's worlds; `OspreyFlow_Build/spec/01_DOMAIN_MODEL.md` (provenance) and `spec/03_CONDUIT_MIDDLEWARE.md`
(the boards' answer); **the diff file** for `spec/06`. **Not touched:** `apps/pages` (GG4a's page already draws no
document), `apps/workspace` beyond what the generated types change.

## Checks (frozen when cut)

`pytest` over the board, working-set, search, link-change and leak-test files and the adapter's conformance suite (the
seat's container checks for the live adapter, under the server's runner); `ruff check .`; the generated-types drift
check; `test_route_rights.py`; `test_doc_citations_check.py`; the cheap checks of 20 November. **The merge's live step
is selected** (an adapter change: D225 item 6, tell the owner before the merge).

## Out of scope

Any page (GG4a's page reads whatever the route sends; it then may say "A document of the case" with a link, a GG4d
change); a document list route; the pictures' own handling (ADR-143 C17, already checked at upload); a re-marking sweep
if none exists (question 4: a stop).
