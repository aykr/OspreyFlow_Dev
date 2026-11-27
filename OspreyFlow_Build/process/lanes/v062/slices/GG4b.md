# Slice GG4b · GG4 · A drawn item's source document is never told to a reader who may not read it, on any read path (a security part, built in the line; the owner, 26 November 2026)


- **Build id:** GG4 (rule 3: no field, count or inference tells a reader of an item they may not see)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GG4a
- **A security part, SE7c's shape, built in the line (not away). Never accepted narrower. Judged by the verifier, the server and the full gate** (the owner's words, 26 November 2026, about 10:35 and 13:40 UTC, `RULINGS.md`: every proposal (a) but questions 2 and 4, which are (b); the ceiling, question 5, is its own slice, GG4j).
- **The away round stopped at the owner's own stop** (`away/GG4b`, its report `process/lanes/v062/away/GG4b_AWAY_REPORT.md` on that branch, the only commit; nothing to merge): no reconciliation re-reads drawn items' markings, in the code or the spec. Read that report whole; its findings are why questions 2 and 4 are now (b).
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
**The ceiling (now GG4j's):** `open()` sends `ceiling = await self.ceiling(board.case_id)`, the strictest marking of the case's datasets
with no reader filter (about lines 179 to 193, 437, 449), so a reader below it is told a marking above their clearance.

## The rulings (every proposal (a), except questions 2 and 4: (b))

1. **A reader who may not read the document is sent the drawn item without it:** `drawn.source_document` and the
   source's `document_id` blanked (the source kept as `drawn:<item_id>`, as for an item drawn from a note alone), **in
   one place that every read path calls** (beside `_board_as_known` in `withhold_sources`). The author keeps it only while
   the author may still read it. **Rule 3 and this choice:** it withholds a field of an element the reader may already
   see, changing no traversal, degree or count; your report says in one paragraph why it satisfies rule 3, and the leak
   test proves no shape differs (case 12).
2. **(b) "May read" is decided at read, with the reader's principal, every time** (the owner, 13:40): on every read path
   that sends a drawn item (the board route, the working set's snapshot and deltas, link changes, the search index's hits,
   the adapter's serialisation), the cited document is re-read with the reader's principal, and the id is kept only if
   that read finds it. **No handling is recorded on the drawn assertion, and no sweep.** Design it so the read is one
   batched read per answer (per frame, per delta, per page of hits) over the documents the answer's drawn items cite,
   never one read per element, and so `withhold_sources` stays a pure function: the batch's result (the set of cited
   documents this reader may read) is passed in, and the call sites that cannot reach the read are named in your report
   as a stop, not worked around. Say in your report which function does the read, where each path calls it, and what a
   failed read does (it withholds: an unreadable document is never kept).
3. **From this slice on, a drawn item needs a source note** (a document is an addition, never in place of it). An item
   already drawn with a document and no note is shown to a reader who may not read the document as "No source note was
   given", byte for byte the words of an item whose note is empty. **This changes ADR-143 decision 4: in the diff file.**
4. **(b) A document re-marked after drawing is caught by the read itself** (ruling 2): no reconciliation is built or
   needed by this slice. (C040, a drawn item re-marked by a path other than the edit route, is its own security row,
   `BACKLOG.md` row 45, before RL2: not this slice.)
5. **The ceiling is not this slice's:** it is GG4j (`slices/GG4j.md`). Leave `open()`'s `ceiling` as it is; row 11 of the
   draft's table moves there.
6. **The decision record:** an ADR-143 amendment (questions 1 to 4 as ruled: the read at read time, the note rule) and an
   ADR-152 decision 11 row (X9), as **one diff file**, `OspreyFlow_Build/process/lanes/v062/GG4b_ADR143_AMENDMENT.diff`,
   applying cleanly to main's `spec/06_DECISIONS.md` (`git apply --check`, said in your report).
7. **A security part:** the conformance suite's case first (rule 1).

## Round 1: the diff file first, then stop

**Write the diff file and nothing else this round,** commit it, and run `git apply --check` against main. Write no
test and no code. End the round with the first line of your report: **"STOP: GG4b's ADR-143 amendment waits for the
owner's approval."** Your checks will be red (the acceptance test does not exist yet), so the line stops the slice: that
is the intended stop. The conductor carries the diff to the owner; the owner's approval line and a clear-stop line start
round 2, which builds the table below.

## Round 2 (after the owner approves the diff)

Build the draft's table of cases (rows 1 to 10 and 12 to 14; row 11, the ceiling, is GG4j's), with row 2's planted
fault now "the document's read skipped for C, the id kept from the author's check" and **one more row, 15: a budget case
for the working set with drawn items** (the owner, 13:40): a working set holding drawn items that cite documents opens and
takes deltas within the working set's existing budget (name the budget and its source: `spec/03` or the working set's own
perf test; if none exists, stop and say so), and the case is red with one document read per element planted in place of
the batch. Every row is **red first on main as it is, with the planted fault at the real call
site the draft names** (rule 15; restore from a saved copy, never by `git checkout`). The worlds: **A** drew an item
citing document **D** (marked above **B**'s clearance); **B** reads the case but may not read **D**; **C** reads the case
and may read **D**. Rows 4 to 7 are each red with the rule put in `open_board` alone, not in `withhold_sources`. Row 13:
`sources_in_full()` (a read written back) keeps D. Row 14: the adapter's conformance case of rows 1 and 7, written before
the change.

**The acceptance test,** `OspreyFlow_Build/tests/ontology/test_drawn_source_document_withheld.py` (new, pure, beside
`test_withhold_sources.py`): `withhold_sources` over drawn nodes and links for A, B and C (rows 1 to 3, 7, 8, 10, 13), and
rows 1 to 3 again through the boards service with `tests/services/api/board_fakes.py` (its fake document store
answering the reader's read). Red on main, green after.
The store-backed rows (the working set's snapshot and delta, search, the leak test, the adapter's conformance suite) go in
their own files beside the existing ones; name each in your report, with the store it needs: they are judged by the
server's early warning and the merge's live step (D225 item 6: an adapter change; the conductor tells the owner before the
merge).

The generated TypeScript follows the schema (`make -C ../OspreyFlow_Build schemas-check` green). **Not touched:**
`apps/pages` (GG4a's page draws no source until a later page part), `apps/workspace` beyond what the generated types
change, any key or address; the ceiling (GG4j).

## The owner's approval (27 November 2026, 03:21 UTC): round 2 starts

**The owner approves the ADR-143 amendment as committed at `92605bf`
(`OspreyFlow_Build/process/lanes/v062/GG4b_ADR143_AMENDMENT.diff`), with (a) on all five of round 1's questions.**
Apply that diff exactly, with no hunk changed, added or dropped, as its own commit before any test or code. Then build
round 2 above, with these answers:

1. **Q1 (a):** a reader who may not read the document gets neither the note nor the document. **The three small
   front-end changes are in this slice's scope**, and they lift "Not touched: `apps/pages`, `apps/workspace`" above for
   these three alone:
   - the GOV.UK board page accepts an item with neither;
   - the React inspector's "No source note was given" sentence;
   - the React drawing form's required note.
   Each change gets its own test, red first.
2. **Q2 (a):** editing an old item must add a note.
3. **Q3 (a):** promotion requires a note, whoever asks.
4. **Q4 (a):** at most one batched document read for each answer that needs several graph reads.
5. **Q5 (a), row 15's budget:** document reads do not grow with the number of items (the planted fault: one read per
   element, in place of the batch), and the server's live step meets `spec/02` §5 (an expansion of up to 500 nodes
   under 800 ms).

Your own reading from round 1 stands: changing a drawn item's document leaves the old id in its stored sources. The
amendment covers that; the edit and the working set keep stored ids. Name the test that shows it.

## Acceptance test

`OspreyFlow_Build/tests/ontology/test_drawn_source_document_withheld.py` (new; red on main, green after).

## Checks (pure; store ports pinned to 9)

The acceptance test; `tests/ontology/test_withhold_sources.py`, `test_sources_in_full.py`,
`test_gazetteer_identifiers_withheld.py`; `tests/services/api/test_boards.py`, `test_grading_boards.py`,
`test_written_back_reads_in_full.py`, `test_batch_expansion.py`; `tests/services/api/working_set/test_delta_projection.py`;
`tests/services/search_index/test_document.py`; `tests/adapters/graph_arcadedb/test_every_read_withholds_by_its_principal.py`;
`test_route_rights.py` is a store test (the full gate runs it); `make -C ../OspreyFlow_Build schemas-check`; `ruff check .`;
`mypy packages services harness`. Round 1's checks are red by design (the diff alone).

## Out of scope

Any page (the board page's source column returns in a later page part, after this merges); a document list route; the
pictures' own handling (ADR-143 C17); a re-marking sweep (none is needed: ruling 4 (b)); C040 (backlog row 45); the ceiling (GG4j).
