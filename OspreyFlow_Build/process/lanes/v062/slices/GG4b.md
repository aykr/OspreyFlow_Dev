# Slice GG4b · GG4 · A drawn item's source document is never told to a reader who may not read it, on any read path; the board's ceiling is told only to a reader cleared for it (a security part; the owner, 26 November 2026)

> **Built as an away round on the server (the owner, 26 November 2026, about 11:10 UTC).** No line builder starts from this brief. When `away/GG4b`'s report appears, the conductor adds a "Round 1 (D247)" section: round 1 merges `away/GG4b`. The rest of this brief is the standard the merged work is judged by (every proposal (a); the ADR-143 amendment as a diff for the owner's approval before merge; never accepted narrower).

- **Build id:** GG4 (rule 3: no field, count or inference tells a reader of an item they may not see)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GG4a
- **A security part, SE7c's shape. Never accepted narrower. Judged by the verifier, the server and the full gate** (the owner's word, 26 November 2026, about 10:35 UTC, `RULINGS.md`: "every proposal (a)").
- **It changes the Conduit and the ontology, which ADR-152 decision 11 admits only by an amendment, and it changes
  ADR-143 decision 4: the decision-record text is a diff file, `OspreyFlow_Build/process/lanes/v062/GG4b_ADR143_AMENDMENT.diff`,
  written first and approved by the owner before the merge. `spec/06_DECISIONS.md` is never edited by this slice.**
- The draft is `slices/drafts_2026-11-26/GG4b.md`: read it whole. Its citations were read at `042c882`; the conductor
  re-read them on main at `41ed4f1` (no file of `OspreyFlow_Core/` has changed since) and they hold.

## The finding (GG4a's away report, question 1 and 4; widened by the draft)

A drawn item's document id is carried twice in its provenance: `DrawnAssertion.source_document`
(`services/api/boards.py` about line 466) and its first source, `SourceRef(document_id=given.source_document or
f"drawn:{item_id}")` (about lines 471 to 479). Every read path sends an element through
`ontology.handling.withhold_sources` (`packages/ontology/handling.py` about lines 335 to 346), which blanks only a drawn
element's `board_id` for others (`_board_as_known`, about lines 385 to 397) and blanks `sources` only where they are not
within the case. A drawn item's sources are within the case, so **the id reaches every reader of the case** through the
board route, the working set's snapshot and deltas, link changes, the search index and the adapter's serialisation. The
document is checked once, at drawing, with the author's principal (`_source_document_check`, about lines 498 to 506).
**The ceiling:** `open()` sends `ceiling = await self.ceiling(board.case_id)`, the strictest marking of the case's datasets
with no reader filter (about lines 179 to 193, 437, 449), so a reader below it is told a marking above their clearance.

## The rulings (every proposal (a))

1. **A reader who may not read the document is sent the drawn item without it:** `drawn.source_document` and the
   source's `document_id` blanked (the source kept as `drawn:<item_id>`, as for an item drawn from a note alone), **in
   `withhold_sources` beside `_board_as_known`** (a new `_drawn_source_as_known`), so one place serves every read path.
   The author keeps it only while the author may still read it. **Rule 3 and this choice:** it withholds a field of an
   element the reader may already see, changing no traversal, degree or count. The owner ruled (a); your report says in
   one paragraph why it satisfies rule 3, and the leak test proves no shape differs (case 12).
2. **"May read" is recorded at drawing and checked at read:** the drawn assertion stores the document's handling (its
   marking and datasets) beside its id, taken by `_source_document_check`'s own read; `withhold_sources` keeps the id only
   for a reader who passes `principal_may_view` on that handling and `sources_within_case` on its datasets
   (`handling.py` about lines 300 to 315). No new read on any path.
3. **From this slice on, a drawn item needs a source note** (a document is an addition, never in place of it). An item
   already drawn with a document and no note is shown to a reader who may not read the document as "No source note was
   given", byte for byte the words of an item whose note is empty. **This changes ADR-143 decision 4: in the diff file.**
4. **A document re-marked after drawing:** the recorded handling is the document's at drawing; a later change is caught
   by the next reconciliation, the sweep that re-reads drawn items' markings, **if one exists. Read whether it does,
   first. If none exists: STOP, commit nothing more, and say so at the top of your report** (not a design for this slice).
5. **The ceiling** is sent only to a reader cleared at or above it; to anyone else the field is the highest marking the
   reader may hold among the case's datasets, so the drawing form offers the same choices (`markings` is already cut,
   about line 448).
6. **The decision record:** an ADR-143 amendment and an ADR-152 decision 11 row (X9), as **one diff file** (named above),
   written first in the round, applying cleanly to main's `spec/06_DECISIONS.md` (`git apply --check`, said in your
   report). The conductor carries it to the owner; the merge waits for the owner's approval line.
7. **A security part:** the conformance suite's case first (rule 1).

## Round 1

Build the draft's table of cases (14 rows), **each red first on main as it is, with the planted fault at the real call
site the draft names** (rule 15; restore from a saved copy, never by `git checkout`). The worlds: **A** drew an item
citing document **D** (marked above **B**'s clearance); **B** reads the case but may not read **D**; **C** reads the case
and may read **D**. Rows 4 to 7 are each red with the rule put in `open_board` alone, not in `withhold_sources`. Row 13:
`sources_in_full()` (a read written back) keeps D. Row 14: the adapter's conformance case of rows 1 and 7, written before
the change.

**The acceptance test,** `OspreyFlow_Build/tests/ontology/test_drawn_source_document_withheld.py` (new, pure, beside
`test_withhold_sources.py`): `withhold_sources` over drawn nodes and links for A, B and C (rows 1 to 3, 7, 8, 10, 13), and
the ceiling for B (row 11) through the boards service with `tests/services/api/board_fakes.py`. Red on main, green after.
The store-backed rows (the working set's snapshot and delta, search, the leak test, the adapter's conformance suite) go in
their own files beside the existing ones; name each in your report, with the store it needs: they are judged by the
server's early warning and the merge's live step (D225 item 6: an adapter change; the conductor tells the owner before the
merge).

The generated TypeScript follows the schema (`make -C ../OspreyFlow_Build schemas-check` green). **Not touched:**
`apps/pages` (GG4a's page draws no source until a later page part), `apps/workspace` beyond what the generated types
change, any key or address.

## Acceptance test

`OspreyFlow_Build/tests/ontology/test_drawn_source_document_withheld.py` (new; red on main, green after).

## Checks (pure; store ports pinned to 9)

The acceptance test; `tests/ontology/test_withhold_sources.py`, `test_sources_in_full.py`,
`test_gazetteer_identifiers_withheld.py`; `tests/services/api/test_boards.py`, `test_grading_boards.py`,
`test_written_back_reads_in_full.py`, `test_batch_expansion.py`; `tests/services/api/working_set/test_delta_projection.py`;
`tests/services/search_index/test_document.py`; `tests/adapters/graph_arcadedb/test_every_read_withholds_by_its_principal.py`;
`test_route_rights.py` is a store test (the full gate runs it); `make -C ../OspreyFlow_Build schemas-check`; `ruff check .`;
`mypy packages services harness`. (`test_doc_citations_check.py` is left out while main is red on it.)

## Out of scope

Any page (the board page's source column returns in a later page part, after this merges); a document list route; the
pictures' own handling (ADR-143 C17); a re-marking sweep if none exists (ruling 4: a stop).
