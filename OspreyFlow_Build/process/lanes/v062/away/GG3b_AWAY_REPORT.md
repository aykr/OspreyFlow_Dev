# GG3b away report: one document of a case in the reader, read-only (26 November 2026, D246 away round)

Branch `away/GG3b`, from `away/GR1a` at `005dcbfca` (GR1a is built, not merged). Nothing was pushed or merged, and `main` is
untouched. Every test ran through `REPO=~/away-gg3b ~/osprey-d246/d246_ns.sh` (which runs at `nice -n 19`) from `OspreyFlow_Core`.
All data is synthetic.

These files were not edited: `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`, `spec/06_DECISIONS.md`,
`spec/ADR_RESERVATIONS.md`, `OspreyFlow_Core/osprey.yaml` and `OspreyFlow_Core/data/`. No decision record changes.

**State: the table is complete and green.** The scenario was written first and was red first. Every check was shown red by a
planted fault at the real call site (27 plants). An independent read-only review found three things that had to change; all three
are fixed. **No security stop arose:** no file type a browser would run as a page can reach this page (below). **Nine questions for
the owner follow.** Two are worth reading first:
- Question 1: the route sends an email's graph ids without a visibility check.
- Question 2: the picture and the film will not load through today's deployed front door.

## The rulings this round worked from (D268, 26 November)

Every proposal (a) of the draft was accepted:
- one document, read-only;
- GG3b starts after GR1a, by the owner's exception;
- the address is `/cases/document?case=…&document=…` (GR1a's query form);
- no graph id is shown or used;
- a cut text is said above the text;
- a picture is `<img>`, a film `<video controls>`, any other file a link;
- question 6b (a): a nosniff test, and nothing changed;
- links only from other pages;
- every refusal is GR1a's 404 page;
- one read per render, pinned;
- Scenario DR first, the strict reader and the field census.

Two standing instructions:
- A content type a browser would run as a page is a STOP (security), reported, never worked around.
- If the route sends something the reader may not see, stop that row and write a question (rule 3).

`RULINGS.md` is the conductor's to write, and this round did not edit it.

### The security stop: did not arise

I read every way a Document gains a file:
- the Files-tab upload (`services/api/document_content.py`, `_UPLOAD_TYPES`);
- an ingest's held content (`services/ingest/engine.py`, `_FILE_TYPES`, and a Document's own text as `text/plain`);
- a node's picture (`services/api/entity_pictures.py`, `PICTURE_TYPES`);
- a board node's picture (`services/api/boards.py`, `PICTURE_TYPES`).

Each stores only these types:
- png, jpeg, gif, webp, tiff, heic;
- mp4, quicktime, webm;
- plain text.

The file route's content type comes from the reference's extension (`packages/adapters/media_objectstore/__init__.py`,
`content_type_of`). That table also maps `.pdf` to `application/pdf`, and anything else to `application/octet-stream`. No writer
stores a PDF today. **No HTML, SVG or XML type is reachable.**

Every answer, the forwarded file included, carries `X-Content-Type-Options: nosniff` and the page service's content security
policy. DR15 pins nosniff on the file, and it was shown red by mounting the headers after the forwarder.

Two things for the owner's security reading are in question 8: the PDF mapping, and a recipe binding `object_ref`.

### The rule-3 stop: a judgement, put to the owner as question 1

`DocumentReaderView` carries `sender_id`, `recipient_id`, `edge_id` and `event_id` for an email. `DocumentReaderService.read` takes
them from the event record, which is read under the case's scope and the handling filter. **Nothing in the code or the tests checks
that the reader may see the two end nodes or the link.** The only test (`OspreyFlow_Build/tests/services/api/test_document_reader.py`)
asserts their values, not their visibility.

**The page draws none of them** (ruling 4 (a); DR13 checks every page for each id, in any text or attribute). The route sends them
for every email whether or not row DR3 is built. So I built DR3 (the sent time only) and did not stop it, and put the route's
behaviour to you as question 1. If you read your instruction as stopping DR3, the change is to leave `sent_at` undrawn: one line in
`OspreyFlow_Core/apps/pages/server/views/documentWords.ts` and DR3's case.

## Commits, in order

| Commit | What |
| --- | --- |
| `45c267db3` | Scenario DR written first in `spec/08`, before Scenario S. The `documents` row carries A6, B6 and DR1 to DR19; its route stays empty. |
| `9203a2794` | **Red first:** the page test, its fixture Conduit and the scenario test with the field census. The page test failed to import (no page); the scenario test had 37 failures. |
| `6c2231698` | The page: `server/document.ts`, `server/views/documentWords.ts` and `tree-govuk/document.njk`. Its rows went into `server/pageList.ts` and `routes.yaml`. Two of the test's own checks were corrected, and one plant whose anchor was not in the page was re-anchored (below). |
| `1416f519c` | The keyboard and scripts-off specs. |
| `465bb86d1` | The route-list pins name the tree's fourth page: HP7/HP9, AP10, the help, AP and CS scenario tests, `test_tree_parity.py` and `test_pages_setting.py`. |
| `a6e102efe` | Fixes for the independent review's findings (below). |
| `51212290d` | The friction row (`process/friction/2026-11-26-away-gg3b-reader-page.md`). |
| `f94778b3b` | The census cases of both pages get a limit of their own (below, under the tests). |
| this commit and the one before it | This report. |

## The table of cases

| # | Case | State | Proof |
| --- | --- | --- | --- |
| 1 | Three spans: two marked by people, one proposed | **green** | DR1. The title is the one level-1 heading. The text is drawn whole, with each passage in a `<mark>`. The table "Words marked in the document's text" has the columns Words, Type and How it was marked, one row a span in the route's order. Provenance is "Marked by a person", "Proposed by a model, not yet confirmed" or "From a single source, not yet corroborated". A span the route leaves out (its node is above the reader) is drawn nowhere. With no span, the page says "No words are marked in this document." and draws no table. |
| 2 | Spans that touch or overlap | **green** | DR2. Touching spans are two marks and overlapping ones one. The text is drawn as sent, line breaks as `<br>`. **Places are counted in code points, as Python counts them.** JavaScript counts UTF-16 units, so an emoji before a span would move every later mark: planted as `text.split("")`, it went red. |
| 3 | An email with `sent_at` | **green** | DR3: "Sent on 3 March 2026 at 14:05 UTC". No sender or recipient is named. A time with no offset (Pydantic's form for a plain `datetime`, which `EventRecord.occurred_at` is) is read as UTC whatever the server's zone. Shown red under `TZ=Asia/Tokyo`. |
| 4 | `truncated` true | **green** | DR4: "This is the start of the message: the rest was not loaded.", above the text. |
| 5 | A picture | **green** | DR5. An `<img alt="A picture from the document">` whose `src` is `/v1/investigations/{case}/documents/{document}/file`. Fetched through the service, it gives the file's bytes and `image/png`. With `has_file` false, no file is drawn. In Chromium (DK2, DO1) it loads, with `naturalWidth` 1, under the page's policy, with no violation. |
| 6 | A film | **green** | DR6: `<video controls preload="none" aria-label="A film from the document">` from the same path. Nothing loads until it is played, so a view of the page is not a file read. |
| 7 | Any other kind with a file | **green** | DR7: a link "Open the document's file", never an `<object>` or an embed. Followed by Enter in DK4 and DO3, it opens the kept text through the forwarder. |
| 8 | No title | **green** | DR8: "A document with no title", in the heading and the `<title>`. An empty title counts as none. |
| 9 | Hidden, another case, missing, not a Document, no level, another unit, no such case, no right | **green** | DR9: the unknown path's 404 page, byte for byte but for the nonce, after exactly one call. These values give the same page and ask nothing: `case` or `document` missing, empty, repeated, `.`, `..` or `%2E%2E`. |
| 10 | One render | **green** | DR10: exactly `GET .../documents/{document}/reader`, as the person, with no browser header. An unsigned request asks nothing. A write method is a path nothing serves. |
| 11 | No answer, or a 401 | **green** | DR11. These give the 502 "could not be read" page, as an alert, with no text, mark, table or file: a 5xx, any other 4xx (429, 409, 422), no answer, a closed address, a text body. A 401 gives the Studio's sign-in-again words. |
| 12 | A missing or wrong field | **green** | DR12. Each of the 17 fields is removed in turn, and each is given a wrong shape. 17 more wrong values follow. Spans out of the route's order give "could not be read". **A span whose place is not in the text** (see the review) is drawn as a row, "Not in the text as it is now", with a sentence above the text. The fixture sends one. |
| 13 | No graph id | **green** | DR13: no `node_id`, `edge_id`, `event_id`, `sender_id` or `recipient_id` on any page, in text or attribute. |
| 14 | Markup in the text | **green** | DR14: a title, a text and a type that look like markup are drawn escaped. |
| 15 | nosniff | **green** | DR15: the forwarder's answer for each file carries `nosniff` and the file's own content type. |
| 16 | Keyboard and scripts off | **green** | DR16, plus the browser specs `keyboard/document.spec.ts` (DK1 to DK4) and `scripts-off/document.spec.ts` (DO1 to DO3). |
| census | Field census | **green** | DR17 and `test_govuk_document_scenario.py`. Every field of `DocumentReaderView` and `MessageSpan` (read by `ast`) is drawn, or named in DR's "Left out, by field name". A drawn field changes the page; a left-out one does not. The page's provenance states are held to `ProvenanceState`. |
| trees | Trees, lists, words | **green** | DR18: the Default tree answers 404 and asks nothing. The route list and the row hold the page. The code holds no filter, sort or cut, and no American spelling. |
| rule 15 | Planted faults | **green** | DR19's in-test plants, and the 27 below. |

DR16's detail:
- **Tab order.** A note's page: the skip link, sign out, back to the case, back to Home. A film's page has the film's own controls before the ways back. A kept text's page has the file's link before the ways back.
- **Enter.** It follows each way back and the file's link.
- **Structure.** One level-1 heading and no skipped level. The table has a caption and header cells. There is no control of the page's own.
- **A browser finding.** Chromium gives a `<video controls>` several stops of its own, each reported as the video, and the shared `tabOrder` helper ends its walk at the first repeated name. The film's walk (`tabOrderPastControls`, in `test/govuk/documentServer.ts`) counts a run of stops on one element as one stop, and proves the keyboard gets past the film.

### Planted at the real call site (rule 15)

`~/gg3b-tmp/plants.py`, outside the checkout, changed one thing in the real `documentWords.ts`, `document.ts`, `document.njk` or
`server/app.ts`. It ran the page test, or the browser specs, and restored the file from git. `git status` was clean afterwards.
**All 27 went red on the case they name:**

- **Marks:**
  - a proposed span drawn as confirmed (DR1);
  - overlapping spans each marked, which doubles the text (DR2);
  - places in UTF-16 units (DR2, DR12);
  - a span the page removes (DR1, DR18).
- **The email:**
  - a sender's id printed (DR3, DR13);
  - a time with no offset read as local (DR3);
  - a cut text not said (DR4).
- **The file:**
  - a picture inlined as `data:` (DR5);
  - a film drawn as a picture (DR6);
  - any file embedded (DR7).
- **The title:** the id given for a missing title (DR8).
- **Refusals:**
  - a refusal in its own words (DR9);
  - a 429 said as not found (DR11).
- **The reads:**
  - the document read twice (DR10);
  - a failed read drawn as an empty text (DR11).
- **The reader:**
  - the type check of `truncated` removed (DR12);
  - the type check of a span's `node_id` removed (DR12);
  - a span whose place is not in the text marked anyway (DR12);
  - such a span left unsaid (DR12).
- **The page:**
  - a `data-node` attribute (DR13);
  - the text unescaped (DR14);
  - `securityHeaders()` mounted after the forwarder (DR15);
  - the ways back swapped (DR16);
  - a script added (DR16).
- **The browsers:**
  - a way back out of the tab order (DK1, DK3, DO1);
  - the file's link out of the tab order (DK4, DO3).
- **The census:** a left-out field, the document's id, drawn (DR17).

**Planting and building found three faults in the tests themselves, each fixed:**
1. A DR19 plant's anchor was not in the page. The span splits the escaped `<script>`, so the plant changed nothing. It is re-anchored and now asserts that it changes the page.
2. The scripts-off check matched `onerror=` in escaped text. It now looks inside tags only.
3. The never-list held the hidden span's words. They are in the text the reader may read; only the mark is withheld.

The scenario test's own plants (28) plant into in-memory copies.

## The independent review and what changed

A read-only lane reviewer read the branch, and its findings were checked against the source. It confirmed the following:
- the page filters, sorts and counts nothing;
- the fixture's refusals match `services/api/app.py` in order and body;
- span handling and the strict reader match the models as FastAPI sends them;
- no HTML or SVG type is reachable;
- nosniff and the policy apply to the forwarded file.

**Fixed in `a6e102efe`:**
1. **A span outside the text made the whole document unreadable, and the real route can send one.**
   - `POST .../designations` checks `view.text[start:end] != text`. A Python slice accepts an end past the text, so an Editor can store `char span 1-99` against "abc", and every reader of that document would have got "could not be read".
   - A second extraction also replaces the kept text under accepted spans (`services/api/review.py`).
   - The page now keeps such a span as a row that says so, and draws the rest. The fixture models it.
   - The Conduit's missing bound check is question 3.
2. **The file's link was never reached or followed by keyboard** (rule 13). DK4 and DO3 now cover it.
3. **No friction row.** It is added.
4. **Smaller points:**
   - A naive time is now read as UTC.
   - Only 403 and 404 are the not-found page. A 429 had read as "not found"; the route's real refusals are only those two.
   - DR19's mark plants run the marks check alone.
   - The PNG and the case link are defined once each.
   - Scenario DR's rule-7 citation moved out of `process/` (`product-tree-link-check`).

**Not done here:**
- **No axe scan** exists for any GOV.UK page, as GR1a also found. It is the tree's gap.
- **The date's words repeat `whenWords`'s month names** (`OspreyFlow_Core/apps/pages/server/views/modelWords.ts`). That function pads the day ("03 March"), where this page says "3 March" as the draft did, so I did not share it.

## Tests run, all through D246

**Page tests (`apps/pages` vitest):**
- `document.test.ts`: 25 of 25.
- Whole suite, run twice at the end: **934 passed, 2 failed** each time. The two traversal-probe failures (`assetsTraversal.test.ts`, `foundation.test.ts`) are the wrapper's (`TMPDIR` under a dot-named folder), as GR1a and GR4a found. They touch no file of this part. With `TMPDIR` set to a plain folder, both files pass, 32 of 32.
- **A timing interaction this slice caused, fixed.** GR1a's census cases (CS11 and CS15 in `cases.test.ts`) start one service world a field and ran near vitest's 5 s limit. With this slice's file running beside them, CS15 timed out in the whole suite (5,067 ms and 5,083 ms; alone, 22 of 22). Both census cases in each file now carry a limit of their own, 20 s, with a comment saying why (`CENSUS_LIMIT_MS`). This is the one change to a GR1a file.

**Playwright, the GOV.UK keyboard and scripts-off folder (`npm run test:keyboard:govuk`):** 21 of 21, this slice's seven (DK1 to DK4, DO1 to DO3) among them.

**Python, the 14 files below:** 873 passed, 1 failed. The failure is GR1a's report under `test_doc_citations_check.py` (see `citation-check` below); this report's own citation was reworded and passes.
- `test_govuk_document_scenario.py` (37)
- `test_functions_yaml.py`
- `test_tree_parity.py`
- `test_no_react_check.py`
- `test_pages_foundation.py`
- `test_design_gates_reach.py`
- `test_pages_image_carries_no_react.py`
- the help, admin-people and cases scenario tests
- `test_ui_words_check.py`
- `test_copy_says_no_client.py`
- `test_doc_citations_check.py`
- `tests/harness/test_pages_setting.py`

The whole `tests/glass_trees/` folder with `test_pages_setting.py` gave 1,917 passed and 24 skipped. It had **1 failure, which is GR1a's:** `test_glass_shared_case_clients.py::test_no_tracked_file_names_an_old_path`. `OspreyFlow_Core/apps/pages/server/types/glassShared.d.ts` lines 30 and 31 name `investigation/cases.ts` and `time/utcStamp.ts` in their old short form. I did not edit GR1a's file. Writing both out as `packages/glass-shared/src/…` is the likely fix.

**Static checks, all exit 0** (and `node OspreyFlow_Core/apps/pages/scripts/build.mjs --out` to a scratch folder builds the page, whose built words import no workspace package):
- root `tsc --noEmit`
- the pages build's `tsc -p tsconfig.build.json`
- `eslint` in `apps/pages`
- `node scripts/no_react_check.mjs`
- `ruff check .` in Core, and the Build tree's ruff on the new scenario test

**`make` gates, with `make`'s own exit code, all 0:**
- `design-check`, `ui-words-check`, `product-tree-link-check`, `test-file-coverage-check`
- `route-coverage-check`, `schemas-check`, `no-branches-check`, `authorized-query-check`
- `demo-guide-check`, `decision-log-publication-check`, `provenance-annotation-check`, `domain-model-coverage-check`
- `no-langchain-check`, `confinement-check`

**`citation-check` exits 2, for GR1a's report alone.** `OspreyFlow_Build/process/lanes/v062/away/GR1a_AWAY_REPORT.md` lines 44 and 151 cite the pages build script by a path from its own package, which the gate cannot find; its full path is
`OspreyFlow_Core/apps/pages/scripts/build.mjs`. This report writes every path in full.

**Not run:**
- `client-name-check`: the hash file is not on this machine.
- `lanes-check`: it fails under D246 for the wrapper's Docker socket.
- `slice-line-check`: no slice-line file changed.
- `graphify update .`: graphify is not installed on this account.

## What is left

- **The links from other pages** (ruling 7 (a)). GA1a and GG3a are not merged, so no link was added. Each is added in the slice that merges second.
- **Merge overlap with GR1a.** This branch is GR1a plus GG3b. Merged after GR1a, it adds a fourth entry to each route-list pin.
- **Merge overlap with GR4a.** The same lists, as GR1a's report says.
- **GR3b:** this fixture, like GR1a's, is hand-written. Its answers should come from the real routes' goldens when GR3b lands.

## Questions for the owner (each is a ruling; none was guessed)

1. **The email's graph ids (rule 3).** The reader route sends `sender_id`, `recipient_id` and `edge_id`, with no check that the reader may see those nodes or that link. A reader cleared for an email's event could learn the id of an end node above them, which is a node's existence (rule 3). The page draws none of them. Built: DR3 draws the sent time only. Options:
   - (a) A Conduit part checks each id's visibility in `DocumentReaderService.read`, or sends `null` for one the reader may not see, with an access-control test (rule 4).
   - (b) Stop DR3 until that lands.
   - (c) Your words.
2. **The file through the deployed front door.** On the GOV.UK theme, while the workspace serves the rest, the front door sends `/v1/…` to the workspace's nginx (`OspreyFlow_Core/harness/pages_service.py`, `route_paths`). An `<img>` sends no bearer there, so the picture and the film load only where the page service carries `/v1`: the tests, and a deployment past I22. Options:
   - (a) Send the file's path (`/v1/investigations/*/documents/*/file`) to `pages` while the workspace remains: a front-door rule, ADR-152 decision 7's to amend.
   - (b) Leave it until I22, and say on the page meanwhile that the file opens in the workspace.
   - (c) Your words.
3. **The Conduit's designation bound.** `Designation` has no check that `end` is within the text, and a stale span is possible after re-extraction. Built: the page draws such a span as a row, "Not in the text as it is now". Options:
   - (a) A Conduit part refuses a designation past the text (a 422), and keeps or re-places spans when the text is replaced.
   - (b) The page shows "could not be read" for the whole document instead.
   - (c) Your words.
4. **The words for an unresolved span.** "From a single source, not yet corroborated" is this slice's, from `spec/01_DOMAIN_MODEL.md`'s table. The draft named only the other two. Options:
   - (a) Keep it.
   - (b) Your words.
5. **"Marked by a person" for an asserted span.** An asserted span is one a person marked by hand, or a model's finding a person confirmed. It is also a node asserted by its source, where the finding linked to an existing node. Options:
   - (a) Keep the ruled words.
   - (b) "Confirmed or marked by a person".
   - (c) "Stated in a source or by a person".
6. **The time says "UTC".** The draft's example was "Sent on 3 March 2026 at 14:05", and the React reader also shows UTC without saying so. Built: "… at 14:05 UTC". Options:
   - (a) Keep it.
   - (b) Drop "UTC".
7. **TIFF and HEIC pictures** are stored and served, but most browsers cannot draw them in an `<img>`. Such a picture shows its name, "A picture from the document", and nothing else. Options:
   - (a) Keep it.
   - (b) Draw those two types as a link.
   - (c) Your words.
8. **For your security reading (no stop):**
   - The media store maps `.pdf` to `application/pdf`. No writer stores a PDF today, but a link to one would open in the browser's PDF viewer at this origin.
   - A recipe may bind `object_ref` on a Document with no content block. `OspreyFlow_Core/services/ingest/recipe_rules.py` refuses that only for `document_text`. Such a Document can point at a file kept for another dataset, and the file route serves it under the loader's marking.
   - The PID demo pack's references (`pid/pictures/…`) do not match the store's reference shape, so their file route answers 404 and the page would draw a broken picture.

   Options:
   - (a) A Conduit or ingest part closes the recipe binding and drops the PDF mapping until a PDF is admitted.
   - (b) Your words.
9. **Only a 403 or 404 is the not-found page here.** GR1a's page treats any 4xx but a 401 as a refusal. This page says "could not be read" for a 429, 409 or 422, since none is a refusal of the reader, and "not found" for a 429 would be untrue. Options:
   - (a) Keep it, and bring GR1a's page into line in a later part.
   - (b) GR1a's rule for both.

## Notes for the verifier

- **The fixture** (`OspreyFlow_Core/apps/pages/test/govuk/documentConduit.ts`) answers in the real order:
  - the router (404, 405; any other route of an investigation is 500, not modelled);
  - then the bearer (401);
  - then `investigate` (403 `right_required`);
  - then the case's gate (404 `investigation_not_found`);
  - then the Document (404 `document_not_found` for one hidden, not in the case, not a Document, or with no file).

  It leaves out a span whose node the reader may not see, sends every field of the model, and sends one span outside its text.
- **The browser specs** start `documentConduit` and GR1a's `casesConduit` behind one front server (`test/govuk/documentServer.ts`), so the way back to the case is followed to a real case page.
- **The scratch scripts** (`plants.py`, `patch_*.py`) and the environment log are in `~/gg3b-tmp/`, outside the checkout.
