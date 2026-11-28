# Slice GG4f2 · GG4 · A drawn item's picture on a board: shown to whoever may see it, and given by upload or chosen from the board's own pictures, scripts off (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GG4a`. No row in `slices.tsv`; no builder
starts from this paper. **Size M.** The second of GG4f's three parts.

**Where it comes from.** ADR-143 C17 (`spec/06_DECISIONS.md` :26596-26597) and decision 7 (:26644-26649): "(a) An
uploaded image becomes an image `Document` in the analyst layer with a `DEPICTS` link to the drawn node, carrying its
own marking and source note (ADR-105 …): **a reader not cleared for the picture sees no picture.** (b) A picture the case
already holds is linked by a `DEPICTS` written into the analyst layer; the image stays in its dataset. (c) An icon is a
display setting, not evidence. **No automatic face matching (rule 5).** Upload size and formats are deployment settings."
ADR-152 decision 5 (the page service's own upload, scripts off). The owner's GG3b ruling (26 November, `RULINGS.md`
:46 and :70): a file type a browser runs as a page is a stop.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`), each writing behind `_DRAWS`, the case's **Editor** gate and
  `own_board`:
  - `PUT .../boards/{board_id}/nodes/{node_id}/picture` (`upload_drawn_picture`, :5279-5326), 201: **the body is the
    file's raw bytes**; `name`, `marking` and `source_note` (1 to 2,000) are **query** fields. A declared length over
    `max_upload_bytes()` (`services/api/ingest_sources.py:224-230`, `OSPREY_INGEST_MAX_UPLOAD_BYTES`) is a 413 before a
    byte is read (:5299-5302), the name is checked against `PICTURE_EXTENSIONS` (:5304-5308; `png`, `jpg`, `jpeg`, `gif`,
    `webp`, `services/api/entity_pictures.py:74-80`), and the stream is cut at the limit (:5310-5316). Audited
    `set_drawn_picture` after every refusal, before anything is kept (:5318-5326).
  - `POST .../boards/{board_id}/nodes/{node_id}/picture` (`choose_drawn_picture`, :5329-5354), 201, body `PictureChoice`
    (`document_id`, `marking`, `extra="forbid"`, `packages/schemas/boards.py:254-261`).
  - `GET .../boards/{board_id}/pictures` (:5357-5369), Viewer gate: `BoardPictures`, node id to Document id, "each drawn
    node's picture on the board that this reader may see".
  - `GET .../boards/{board_id}/nodes/{node_id}/picture` (:5372-5386): the file, with the content type its reference
    names; "one they may not [see] answers as none".
- **What they refuse** (`services/api/boards.py`): `no_source` 422 (:1072-1075), `no_media_store` 503 (:1076-1077),
  `not_a_picture` 422 (:1080-1084, and for a chosen Document that is not an image the case holds, :1139-1147),
  `item_not_found` 404 (a node not on this board, withdrawn, or hidden, :965-975), **`not_your_item` 403** (:976-980),
  `no_picture_for_this_type` 422 (a type `DEPICTS` may not point to, :983-989), `not_a_marking` 422 (:1148-1151), and
  `check_marking`'s 409s (:1086, :1155). A chosen picture's link is marked **at least as the image is**
  (`merge_handling`, :1152-1154). A new picture supersedes the one before, which is kept (:1020-1033).
- **No route lists a case's documents** (GG3b's finding). The React editor chooses a picture "from the Documents on the
  board … these are the ones this reader may already see" (`apps/workspace/src/boards/BoardEditor.tsx:133-136`): the
  opened board's `nodes` of type `Document` with `media_kind` `image`.
- **The page service already carries this upload two ways.** (1) The forwarder (`apps/pages/server/forward.ts:43-52`,
  :107-112) translates a scripts-off `multipart/form-data` **POST** to the board picture route into the Conduit's `PUT`
  (:394, :434), the fields as query fields and the file raw, under `OSPREY_PAGES_UPLOAD_MAX_BYTES`; **but it answers with
  the Conduit's own body**, so a person posting a form there lands on JSON. (2) A page route may take an upload
  (`upload` in `pages.ts:37`, read by `server/upload.ts`: the `_csrf` first, fields before the file, held in memory to a
  cap). **The page's Conduit client sends only JSON bodies** (`apps/pages/server/conduit.ts:26-33`, :58-68).
- **GG3e** (adding files to a case, drafted beside this one) faces the same choice for `POST .../documents`, the fourth
  route in the forwarder's table. **Whichever of the two is built first adds the raw body to `conduit.ts`; the other
  reuses it.**

## Acceptance (red before, green after)

Scenario BD's picture rows (after GG4f1's), written first, and `apps/pages/test/govuk/boards-pictures.test.ts`, red on
GG4f1's page, green after; every earlier BD row unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Pictures shown on the board page; upload (C17 a); choose one of the board's own image Documents
   (C17 b), as the React editor does.** Icons (C17 c) are a display setting and come with GG4e's module. (b) Upload only.
2. **How the upload reaches the Conduit.** (a) **A page route that takes the upload** (the board page answers a
   multipart `POST` as `upload.ts` reads it), whose server half sends the bytes with one `PUT`, then `303` to the board
   with a banner; `conduit.ts` gains a raw body (bytes and a content type); it already sends `PUT` (`conduit.ts:28`), so only the body is new, shared with GG3e. Refusals
   are said in the page's words. (b) The form posts straight to the forwarder's translation: one less part, but the
   person sees the Conduit's JSON after (no banner, no words): **not proposed**.
3. **How the picture is shown.** (a) **An `<img>` whose source is the picture route through the forwarder** (the ids in
   the path only, GG4a's rule), with `alt` "Picture of {label}", only for nodes `BoardPictures` names; the page draws no
   picture, placeholder or "no picture" mark for anything else (rule 3: a reader not cleared for it sees no picture and no
   sign of one). The page writes the `<img>` and reads no content type: what the browser is sent is the Conduit's
   (question 3b). (b) The page reads the file and embeds it: not proposed (the page would hold image bytes).
3b. **What a chosen picture is served as** **(owner: security, a Conduit-side test or fix).** `choose_picture` checks only
   that the Document is an image by `media_kind` (`boards.py:1139-1147`), while `picture_file` serves the bytes as
   `content_type_of(object_ref)` (:1194-1195), which reads the reference's extension
   (`packages/adapters/media_objectstore/__init__.py:53-55`): a Document marked `image` whose `object_ref` ends `.pdf` or
   `.txt` is served on the board's picture path as `application/pdf` or `text/plain`, against the GG3b ruling (a PDF only
   as a download; a browser-runnable type a stop). SE9e and SE9f close the ways a recipe or the extract route set
   `object_ref`; nothing pins the pair at this route. (a) **A Conduit security part: `choose_picture` refuses, and
   `picture_file` answers as none, any Document whose reference is not one of the four image types, red first with such a
   Document planted in the store; this slice waits for it.** (b) Accepted as closed by SE9e and SE9f, with a test only.
4. **The file's own type.** The route checks the name's extension, not the bytes. (a) **The page sends the name the
   person chose, unchanged, and says the route's `not_a_picture` in words**; checking the bytes is not the page's (and a
   file that is not what its name says is served under its declared image type with `nosniff`, so a browser never runs
   it, question 3). (b) The page sniffs the bytes: not proposed (a second check that disagrees with the route's).
5. **The marking on the form.** (a) **The board's `markings` (cut to the reader) as radios, none chosen**, and for a
   chosen picture the sentence "It is marked at least as the picture already is." (b) A default chosen: not proposed (a
   marking is a decision).
6. **The size limit in words.** The page cannot read the Conduit's `OSPREY_INGEST_MAX_UPLOAD_BYTES`. (a) **The page's own
   upload cap is `OSPREY_PAGES_UPLOAD_MAX_BYTES`, the forwarder's; a 413 from either is "That file is larger than the
   upload limit."** (the route's own words, `app.py:5302`), with no figure. (b) A figure in the sentence: needs a read of
   the Conduit's setting (an amendment).
7. **Choosing.** (a) **A list of the board's own image Documents (by title), as radios**, empty when there are none ("No
   pictures on this board to choose from."). A picture of another board or the case's files is reached by GG3e later.
   (b) A document id typed: not proposed (rule 7).
8. **Refusals.** (a) **A sentence each** for `no_source`, `not_a_picture`, `no_picture_for_this_type` ("A {type} cannot have
   a picture of its own"), `not_a_marking`, the two marking 409s (naming no marking but the capped ceiling: the GG4j
   ruling), 413 and 503 `no_media_store` ("Pictures cannot be stored here."); `not_your_item`, `not_the_boards_creator`
   and `item_not_found` the board's 404 page. The person's note and marking are kept on the form. (b) The Conduit's
   detail.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A board whose route says two drawn nodes have pictures | two `<img>` with their alt text, each `src` the picture route of its own node | the `src` made from the Document id (`BoardPictures`' value) rather than the node |
| 2 | A drawn node with no picture, and one whose picture the reader may not see (the fixture leaves it out, as the route does) | no image, no placeholder, no word for either | a "no picture" mark drawn for nodes the map leaves out |
| 3 | The creator uploads `harbour.png` (synthetic) with OFFICIAL and a note | one `PUT` with the file's bytes raw and `name`, `marking`, `source_note` as query fields, nothing else; `303` to the board; "Picture added to {label}." | the multipart envelope sent as the body (the bytes differ from the file's) |
| 4 | `_csrf` not the form's first part | refused before a byte of the file is read; nothing sent (I17, `upload.ts`) | the file read before the token is checked |
| 5 | No note | the error summary's no-source sentence; nothing sent | the form sent, the 422 shown raw |
| 6 | `plan.pdf` | the `not_a_picture` sentence; the note and marking kept | the 422's detail passed through |
| 7 | A file over the page's cap, and one the Conduit refuses as over its own | "That file is larger than the upload limit." for both; nothing kept | the page's cap skipped (the file held whole) |
| 8 | A type that may not have a picture | "A Vehicle cannot have a picture of its own" | the route's detail shown |
| 9 | Choose one of the board's image Documents | one `POST .../picture` with exactly `{"document_id", "marking"}`; `303`; the banner | `_csrf` in the body (`PictureChoice` is `extra="forbid"`) |
| 10 | The board holds no image Document | "No pictures on this board to choose from." and no choose form | an empty radio group |
| 11 | Someone else's board, or a node not on this board (403, 404) posted by hand | the board's 404 page | either said in words |
| 12 | One render of a board with two pictures | the page's server half asks the picture route nothing (the browser's `<img>` does); no `data:` address and no picture bytes in the page | the server half reads each file to inline it as a `data:` address |
| 13 | A body missing a field `BoardPictures` or `DrawnItemMade` requires | "could not be read" | each required field removed in turn |
| 14 | Keyboard | the upload and the choice reachable and working, one case each in `keyboard/boards.spec.ts` (rule 13) | the file input out of the tab order |
| 15 | Scripts off | both forms work by posting; the pictures shown | an upload that needs a script |
| 16 | The fixture | refuses as the route does, in the route's order (size, name, `own_board`, then `upload_picture`'s checks: note, store, type, subject, author, `DEPICTS`, marking) | a fixture that accepts another reader's upload |

## Waits on

GG4f1 (it shares the board page's parts and words); GG4c, GG4b and GG4j merged; GG3e or GG4f2, whichever lands
`conduit.ts`'s raw body first; question 3b's Conduit security part, if the owner rules (a).

## Files touched

`spec/08` (BD's picture rows); `apps/pages/server/boards.ts` (the board page takes an upload), `server/conduit.ts` (a raw
body, unless GG3e lands it first), `server/pageList.ts` (the page's `upload` and `POST`),
`server/views/boardsWords.ts`; `tree-govuk/boards.njk` and the picture forms; `test/govuk/boards-pictures.test.ts`,
`boardsConduit.ts`, `keyboard/boards.spec.ts`, `scripts-off/boards.spec.ts`; `test/server/conduit.test.ts` (the raw body);
`OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (`BoardPictures`, `DrawnItemMade`, `PictureChoice`).

## Checks (frozen when cut)

GG4c's list, and the page service's own `test/server` suite (`conduit.ts` changes).

## Out of scope

Icons (C17 c, with GG4e's module); a picture of a loaded node (ADR-105's own route, `app.py:7970`); face matching (never:
rule 5); any Conduit change; `apps/workspace`.


## The owner's answers (the owner's answers of 27 November 2026, after 09:40 UTC; RULINGS.md)

1. **Q3b (a): this slice waits for SE9g.** That is a Conduit security part, red first: `choose_picture` refuses, and `picture_file` answers as none, any Document whose reference is not one of the four image types. Build on SE9g's merged behaviour. Do not repeat its check in the page.

Every other question in this draft stays (a) on the owner's standing word.
