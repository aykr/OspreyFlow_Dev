# Slice GG3b · GG3 · One document of a case in the reader, as a GOV.UK page, read-only: its text with the words marked from it, and its picture or film where it has one (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** The plan's row "GG3: Inspector, search, timeline, documents (R5)", which needs GG2 and PL8.
`FUNCTIONS.yaml` row `documents` (`OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:245-251`: "Documents: reader, a node's
Messages, adding files", scenarios A6 and B6, no route). **Of GG3's four functions, the reader is the one whose subject
is addressed without the canvas**: the inspector takes the canvas's selection (`apps/workspace/src/inspector/Inspector.tsx:50`,
:149), the timeline filters on the cross-filter store's selected nodes (`timeline/Timeline.tsx:170-187`, :248-254) and a
node's Messages take working-set ids (`dossier/Dossier.tsx:58`), while the reader takes a case and a document
(`reader/DocumentReader.tsx:70`). It is also the page that **two drafted pages need to link to**: GA1a's citations
("its document citations by title") and GG3a's search results. (A brief's attachments are not among them: their kinds
are `trend`, `pattern`, `assessment` and `view`, `services/api/case_brief.py:62`; none is a document.)

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`):
  - `GET /v1/investigations/{id}/documents/{document_id}/reader` (`read_document_route`, :7813-7836):
    `require_right(INVESTIGATE)` and the case **viewer** gate. "Only to someone who can see the Document in the case;
    one that cannot be seen answers as one that does not exist." **Audited** `read_document`, with the count of spans.
  - `GET .../documents/{document_id}/file` (`document_file_route`, :7938-7959): the same gate; the held file's bytes with
    its content type; **audited** `read_document_file`; missing or unseen is `DocumentNotFoundError` → **404
    `{"error": "document_not_found"}`** (handler :3748-3752).
  - Writes, for later slices: designations (`POST .../designations`, :7838-7863, `EXTRACT_FILES`, Editor), extraction
    (:8109), candidates (:8140, :8166, :8201), the upload (`POST .../documents`, :7866-7935, `EXTRACT_FILES`, Editor).
  - **No route lists a case's documents.** The routes above take a document's id; nothing in `app.py` answers "the
    case's documents".
- **The answer** (`DocumentReaderView`, `services/api/document_reader.py:55-71`): `document_id`, `title` (optional),
  `text`, **`truncated`** ("the email's excerpt was cut at the loader's limit", ADR-089 decision 1), `spans`
  (`MessageSpan`, `services/api/dossier.py:37-44`: `start`, `end`, `node_id`, `entity_type`, `provenance_state`),
  `sent_at`, `sender_id`, `recipient_id`, `edge_id`, `event_id`, `media_kind` (`text`, `image` or `video`) and
  `has_file`. **`sender_id`, `recipient_id`, `edge_id`, `event_id` and each span's `node_id` are graph ids, not words.**
  The shared client is `packages/glass-shared/src/reader/readerApi.ts` (a hand-written interface at :7, the reader GET
  at :173-184, the file at :39).
- **What a held file may be** (`services/api/document_content.py:126-139`): png, jpeg, gif, webp, tiff, heic, mp4,
  quicktime, webm and plain text. **No type a browser runs as a page** (HTML, SVG) is in that list. Whether a document
  loaded another way (an ingested email's attachment) can have a file of another type was not read.
- **Through the page service.** `apps/pages/server/forward.ts` carries every `/v1` path but three (:97-101), copies back
  `Content-Type`, `Content-Disposition` and `X-Guide-Version` only (:89), and never `X-Content-Type-Options`. An `<img>` or `<video>`
  whose `src` is the forwarder's path is same-origin, so decision 8's `img-src 'self'` and `default-src 'self'` admit it.
- **The keyboard.** `READER_ACTIONS` (`actionRegistry.ts:820-833`, 8 ids), mostly designation and extraction.
- **Scenarios.** A6 (`spec/08` :387, "open the reports for the filtered selection") and B6 (:557, "inspect the shared
  endpoint's messages; spans highlighted in place") both start from the canvas. **No scenario reads one document by its
  address**, so a scenario is written first (the owner's rule).

## Acceptance (red before, green after)

A new `spec/08` scenario **DR**, written first, and `apps/pages/test/govuk/document.test.ts`, red (no page), green
after; `test_govuk_document_scenario.py`'s census of `DocumentReaderView` green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **One document, read-only:** its title, its text with each span marked (the words, their type, and
   "marked by a person" or "proposed by a model, not yet confirmed" for its provenance: rule 5), the sent time where it
   is an email, and its picture or film where `has_file`. No designation, no extraction, no list. (b) With a list of the
   case's documents, which needs a new Conduit route (decision 11: an amendment). Not proposed now; question 7.
2. **When it starts.** (a) **After GR1a merges, by the owner's exception, as for GG4a**: it draws nothing, needs no
   selection and no panel frame, and three pages wait to link to it. (b) As the plan's row says, after GG2 and PL8's
   mount slice.
3. **The address.** (a) **`/cases/document?case=…&document=…`**, GR1a's query form, until GR1a's question 1 is ruled;
   with GR1c, `/cases/{case_id}/documents/{document_id}`. (b) Your words.
4. **The graph ids in the answer.** (a) **None is shown or used**: a span is its words and its type; the sender and
   recipient are not named (the route sends ids, not names), and are named as left out in the census, with GG3d (the
   inspector) the slice that may name them. (b) Show them as the React reader does, by looking each up: a second read
   per id, and it is not this page's to filter.
5. **A cut text.** (a) **When `truncated` is true, the page says above the text "This is the start of the message: the
   rest was not loaded"** (rule 2: never a silent cut). (b) Nothing.
6. **The file.** (a) **An image is an `<img>` and a film a `<video controls>`, each with its `src` the forwarder's path,
   and the text "a picture from the document" or "a film from the document" as its name, chosen by the answer's
   `media_kind` (`image` or `video`, `document_reader.py:68-71`; the answer carries no content type, which is known
   only from the file's own answer); any other `media_kind` with `has_file` is a link to the file, not shown.** The
   builder reads every way a document gains a file and the content types each can have; **a content type a browser
   would run as a page is a stop, the owner's (security).** (b) Every file as a link only.
6b. **`X-Content-Type-Options: nosniff` on the file.** The forwarder copies back no such header from the Conduit
   (`forward.ts:89`), but the page service sets it itself on every answer: `securityHeaders()` has
   `xContentTypeOptions: true` (`server/headers.ts:53`) and is applied to the whole app (`app.ts:223`) before the
   forwarder is mounted (:603). (a) **Nothing to change; case 15 pins it on the file's answer**, so a later change to
   the order of the middleware turns a test red. (b) No test.
7. **How a reader reaches the page.** (a) **By links from other pages only** (GA1a's citations and GG3a's results), each added in this slice where the linking page is merged, and a later Conduit
   amendment for a list if the owner wants one. (b) A list now (question 1 (b)).
8. **Refusals.** (a) **`document_not_found`, the case gate's 404 and a 403 (no `INVESTIGATE`, or a level the gate
   refuses) are the same GOV.UK 404 page**, words and status (the owner's no-oracle rule). (b) The 403 said in words.
9. **The audit.** (a) **One `GET .../reader` per render, pinned by a test**; the browser's load of the picture is a
   second, separate read the Conduit audits as `read_document_file`, which the scenario says. (b) No test.
10. **The scenario and the fixture.** (a) **Scenario DR first; the strict reader and the field census (GR3a's)** over
    `DocumentReaderView` and `MessageSpan`; the fixture refuses as the route does (404 for a document the reader may not
    see, exactly as for one that does not exist) and its answers come from the real route when GR3b lands (rule 15).
    (b) Your words.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A text document with three spans, two marked by people and one proposed | the title; the text with three marked passages, each with its type and its provenance in words | a proposed span drawn as confirmed (rule 5) |
| 2 | Spans that touch or overlap | each span's words marked once, in order, no text lost or doubled | spans applied by index after an earlier insert shifted the text |
| 3 | An email with `sent_at` | "Sent on 3 March 2026 at 14:05" (synthetic); no sender or recipient named | a sender id printed |
| 4 | `truncated` true | the sentence of question 5 above the text | the text alone |
| 5 | An image document with `has_file` | an `<img>` whose `src` is the forwarder's path, with its name; the tables of spans unchanged | the bytes inlined as `data:` |
| 6 | A film | `<video controls>` with its name | an `<img>` for a film |
| 7 | `has_file` with a `media_kind` neither `image` nor `video` | a link to the file, not shown | the file embedded whatever its type |
| 8 | No title | "A document with no title" | the document id printed |
| 9 | A document the reader may not see, one in another case, one that does not exist, a reader without `INVESTIGATE` | the same 404 page, words and status, for all four | "You cannot see this document" for the first |
| 10 | One render | exactly one `GET .../reader` | the page reading twice (title and body) |
| 11 | The Conduit gives no answer, or 401 | the 502 "could not be read" page; an ended session says to sign in again | an empty text |
| 12 | A body missing a field `DocumentReaderView` requires | "could not be read" | each required field removed in turn |
| 13 | No graph id on the page | no `node_id`, `edge_id`, `event_id`, sender or recipient id in the HTML | a span's `data-node` attribute |
| 14 | Text that looks like markup | drawn as text | the text written unescaped |
| 15 | `nosniff` (question 6b (a)) | the forwarder's answer for the file carries `X-Content-Type-Options: nosniff` | `securityHeaders()` mounted after the forwarder |
| 16 | Keyboard and scripts off | the page whole and every link working (rule 13, I4) | a link out of the tab order |

## Files touched

`spec/08` (scenario DR); `FUNCTIONS.yaml` (`documents`: DR's ids, route empty until the row is whole);
`apps/pages/server/document.ts` (new), `server/views/documentWords.ts`, `server/pageList.ts`; `tree-govuk/document.njk`,
`tree-govuk/routes.yaml`; `test/govuk/document.test.ts`, `documentConduit.ts`,
`keyboard/document.spec.ts`, `scripts-off/document.spec.ts`; `OspreyFlow_Build/tests/glass_trees/test_govuk_document_scenario.py`;
`tests/harness/test_pages_setting.py` (the route list); the linking pages' templates (question 7), each only once merged.

## Checks (frozen when cut)

GR3a's list, adapted: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; the scenario's test;
`test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`, `test_doc_citations_check.py`,
`test_pages_setting.py`; the GOV.UK CSP spec over the page (an `<img>` and a `<video>` from the forwarder); the
forwarder's own tests (question 6b); `ruff check .`; `make -C OspreyFlow_Build design-check`; the cheap checks of 20
November.

## Out of scope

Designation, extraction and candidates (later GG3 slices, Editor and `EXTRACT_FILES`); a node's Messages (needs the
working set: after GG2e); adding files (GG3e); a list of the case's documents (a Conduit amendment, question 7);
`apps/workspace`; the Default tree's twin.
