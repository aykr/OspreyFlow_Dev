# Slice SE9d · SE9 · The document reader never sends an email's end nodes or link to a reader who may not see them (a security part; the owner, 26 November 2026)

- **Build id:** SE9 (rule 3: no id, count or placeholder reveals an item the reader may not see)
- **Dial setting:** balanced · **Rounds limit:** 8 · **After:** nothing · **Before RL2** (the owner's word)
- **Never accepted narrower. Judged by the verifier, the server and the full gate** (the owner's word, as for SE7c).
- **From GG3b's away report, question 1** (on `away/GG3b`, `process/lanes/v062/away/GG3b_AWAY_REPORT.md`, "The rule-3
  stop"): ruled "yes, a Conduit security part, before RL2" (26 November 2026, 12:15 UTC; `RULINGS.md`).

## What (the finding)

`GET /v1/investigations/{investigation_id}/documents/{document_id}` (`OspreyFlow_Core/services/api/app.py` about lines
7820 to 7830, `document_reader.read`) answers a `DocumentReaderView` (`services/api/document_reader.py` about lines 55 to
66) that carries an email's `sender_id`, `recipient_id`, `edge_id` and `event_id`. `DocumentReaderService.read` (about
lines 115 to 158) takes them from the email's event record (`_event`, about lines 251 to 260: the case's own events under
the handling filter) and copies `event.source_id` and `event.target_id` (by direction) and `event.edge_id` **without
asking whether the reader may see those two nodes or that link.** An event is visible on its own handling; a link's end
may be marked above the reader. So a reader can learn the id of a node, or of a link, they may not see (rule 3).
`OspreyFlow_Build/tests/services/api/test_document_reader.py` asserts the values, never their visibility.

## Round 1

1. **The rule (rule 3, as `WorkingSetService.visible_edge` already reads a link, `services/api/working_set/service.py`
   about lines 1490 to 1500):** `sender_id` and `recipient_id` are sent only when `visible_node` (about line 1479) gives
   that node to the reader in this case; `edge_id` (and `event_id`, if it names the link's event) only when
   `visible_edge` gives the link. **Otherwise each is `None`, and the answer is byte for byte the same shape as for an
   email whose event had no such end** (no flag, no count, no different wording, no different timing path the reader can
   tell apart; say how you held the last). One batched read per answer, not one per field.
2. **Every other read path that sends these ids** (find them: the model, the generated TypeScript, the workspace's
   reader, GG3b's page as a reader of it, any export): list them in your report; each gets the same rule in the same
   change.
3. **The access test first (rules 1 and 4)**, then the code.

## The table of cases (each red first on main, the planted fault at the real call site; rule 15)

| # | Case | Expected | Red with |
| --- | --- | --- | --- |
| 1 | An email whose sender is above the reader | `sender_id` is `None`; the rest as today | today's code |
| 2 | Its recipient above the reader | `recipient_id` is `None` | today's code |
| 3 | The link above the reader, both ends visible | `edge_id` (and the link's `event_id`) `None` | the check on the ends alone |
| 4 | Every end and the link visible | all four sent as today | the ids withheld from everyone |
| 5 | Cases 1 to 3 against an email with no such end | the same JSON shape and field set, byte for byte | a flag or wording that differs |
| 6 | An inbound email (`direction == "inbound"`, the ends reversed) | the rule follows the reversed ends | the check on the unreversed ends |
| 7 | Every other path found in step 2 | the same rule | the rule in `read()` alone |

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_document_reader_withholds_ends.py` (new, pure, through `DocumentReaderService`
with the fakes `test_document_reader.py` uses; red on main).

## Checks

The acceptance test; `test_document_reader.py`; `test_email_extraction.py`; `make -C ../OspreyFlow_Build schemas-check`;
`ruff check .`; `mypy packages services harness`. The store-backed read is judged by the server and the merge's live step.

## Out of scope

GG3b's page (it already draws none of these ids); the file route (GG3b's Q8 (i)); a list of a case's documents.
