# Slice GG3e · GG3 · Adding a file to a case on the GOV.UK tree, scripts off: one file with its marking and legal basis, streamed to the Conduit, then shown in the reader (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.**

**Where it comes from.** The plan's row "GG3e: adding files to a case (upload through the page service's multipart
forwarding) | GG3b" (`slices/drafts_2026-11-26/CHAIN_PLAN.md:77`). `FUNCTIONS.yaml` row `documents`
(`OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:245-251`: "Documents: reader, a node's Messages, adding files"), whose first
page is GG3b's reader at `/cases/document` (built on `away/GG3b`; `slices/GG3b.md`). ADR-094 step 3 and spec 09 §7 (a file
added straight to the case), spec 09 §2 (every source needs a marking and a legal basis). **It draws nothing with Sigma,
so decision 9 does not hold it; it starts after GG3b merges, which is itself the owner's early start.**

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The route.** `POST /v1/investigations/{id}/documents?name=&classification=&legal_basis=&handling_code=&holder=`
  (`upload_document_route`, `services/api/app.py:7865-7935`): `require_right(EXTRACT_FILES)`,
  the case **Editor** gate, then `NoLoadingInACompositeCase` (:7868; `refuse_loading_in_a_composite_case`,
  :2972-2982, which runs after the Editor check it depends on and before the handler's body): a case reading a
  composite, **409 `composite_read_only`**, and a case reading a drawn dataset, **409 `drawn_not_loaded`** (handler
  :10592-10599). **The body is the file's raw bytes** (`request.stream()`, :7900-7906), not a form. Then, in the
  handler, in order: a declared length over the limit, **413** (:7888-7891); a bad
  name or an extension not allowed (`validate_upload_name`, :7892-7897; statuses in `_UPLOAD_REFUSAL_STATUS`, :13190-13197:
  400, 415, 409, 413, 503), **each an `HTTPException` whose body is `{"detail": "<sentence>"}` with no `error` code**; a marking above the deployment's highest, `AboveTheDeploymentCeiling`, "refused before the
  body is read" (:7898-7899, :3429-3435); a stream past the limit, 413; then the service. Audited `upload_document`
  with "the name, size, marking and legal basis, never the contents" (:7922-7934). **The legal basis is audited and
  not stored on the Document**: it is passed to no write (:7907-7920).
- **The service** (`DocumentContentService.upload`, `services/api/document_content.py:270` onward): only the extensions of
  `_UPLOAD_TYPES` (:126-139: png, jpg, jpeg, gif, webp, tif, tiff, heic, mp4, mov, webm, txt), else **422
  `upload_refused`** "not a kind of file the reader can show" (:284-287; handler `app.py:3403`); a marking the uploader
  could not read themselves, 422 `upload_refused` (:289-292); a holder not visible in the working set, **404
  `holder_not_found`** (:294-297; handler `app.py:3390-3392`); a holder of a type that cannot `HOLDS`, 422 (:299-300).
  "Every refusal comes before any write." It answers `DocumentUploadResult` (:120-122: `document_id` and a `DeltaAdd`),
  and the route publishes the delta (:7921), so the new Document joins the case's working set.
- **No type a browser runs as a page** is among the extensions (GG3b's question 6 (a): such a type is a stop). A PDF is
  not among them either, so GG3b's Q8 (i) (a PDF as a download) does not arise for an upload.
- **The size limit.** `max_upload_bytes()`, `OSPREY_INGEST_MAX_UPLOAD_BYTES`, 512 MiB by default
  (`services/api/ingest_sources.py:221-230`); the page service's own `OSPREY_PAGES_UPLOAD_MAX_BYTES`, the same default
  (`apps/pages/server/config.ts:167`, :184).
- **The page service carries this route already.** `forward.ts` lists `POST /v1/investigations/{id}/documents` among the
  four raw upload routes (:107-112), streams the body "never held", and translates a scripts-off multipart post: "the
  form's fields come first and become the route's query fields, the file part's name becomes `?name=`, and the file's
  bytes are sent raw" (:48-53; the reader, :440-470, the token first part and every field before the file). **But a post
  to `/v1/...` answers the Conduit's JSON**, not a page: a scripts-off person would see `{"document_id": …}`.
- **A page that takes a file** (`PageModule.upload`, `apps/pages/server/pages.ts:41`, checked at :124-125;
  `uploadPathsOf`, :149-150, which `csrf.ts` leaves to the page's own reader): the Studio's (`server/studio.ts:734`,
  `readUploadForm` at :546). **`readUploadForm` holds the files in memory** (`server/upload.ts:1-10`), under a cap the
  route gives (the Studio's is 2 MB, `server/staging.ts:33`). A 512 MiB film should not be held.
- **What the form offers.** The deployment's scheme: `GET /v1/handling-scheme` (`app.py:13127-13134`); the reader's
  clearance: `GET /v1/me` (:20604-20614, `clearance`); the reader's rights: `GET /v1/me/rights` (:20664). The React form
  (`apps/workspace/src/content/AddFiles.tsx`) offers every classification of the scheme (:66-73), a legal basis as free
  text, several files sent one request each, and a holder when opened from a node (:14, :28-29); it sends no
  `handling_code` (the route's default `P`).

## Acceptance (red before, green after)

Scenario DR's adding rows (GG3b's scenario), written first, and `apps/pages/test/govuk/document-add.test.ts`, red on
GG3b's page, green after; GG3b's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **One file per post, added to the case, with its marking and legal basis; no holder.** A holder is a
   node in the working set (`visible_node`), which a page reaches only through GG3d1's inspector: "Add a file held by
   this node" is a later step there. (b) Several files in one post: the route takes one, so the page would send several
   and report each; later.
2. **Where the form lives.** (a) **On GG3b's page, the `documents` row's one page: `GET /cases/document?case=…&add=1`
   shows the form, and `POST /cases/document` takes it** (the page gains `upload: true` and `POST`), linked from GR1a's
   case page ("Add a file"). (b) A new `FUNCTIONS.yaml` row and path for adding files. Not needed: the row already
   names "adding files".
3. **How the file reaches the Conduit.** (a) **The page's server half streams the file part straight into the Conduit's
   route, never holding it, using the forwarder's own translation** (the token first, every field before the file, the
   fields as the query, the bytes raw), factored out of `forward.ts` into one function both call, so there is one
   reader and one allow-list. **(owner: security.)** It moves the anti-forgery boundary for this path (`csrf.ts` leaves
   an `upload` page's body to the page's own reader, and this page's reader becomes the forwarder's) and refactors the
   forwarder's upload allow-list (`forward.ts:107-112`); the factoring is behaviour-preserving, proven by
   `forward.test.ts` and the anti-forgery tests unchanged and green, each with a planted fault at the shared function. The answer is read by the server half, not passed through: a `303` to the reader page of
   the new `document_id`, with "The file was added to the case". (b) `readUploadForm`, holding the file in memory under a
   page-side cap: a limit the Conduit does not have, so not proposed. (c) The form posts to `/v1/...` itself: the
   person sees JSON. Not proposed.
4. **The markings offered.** (a) **The scheme's classifications at or below the reader's own clearance (`/v1/me`), in
   the scheme's order, with none chosen**, so nothing is marked by default. A hand-sent higher one is refused by the
   route and said in words; one above the deployment's ceiling the same. `handling_code` is not offered (the route's
   default, as the React form). (b) Every classification, as the React form, refused after.
5. **The legal basis.** (a) **Required, free text, said as "The power or consent the file is held under" (the React
   form's words), kept in the form on any refusal, with no length limit of the page's own** (the route has only
   `min_length=1`, `app.py:7879`; a limit, if wanted, is a Conduit part). The page says nothing about where it is kept.
   (b) Your words.
5b. **Where the legal basis is kept (owner).** The route audits it and stores it on nothing (spec 09 §2: every source
   "needs" one). (a) **Recorded for the owner as a Conduit question; this slice changes nothing**, and sends it as the
   React form does. (b) A Conduit part storing it on the Document first (an amendment, decision 11).
6. **Refusals in words.** (a) **One sentence for each: a file too large (both the declared length and a stream cut,
   413, in the Conduit's own words, as the forwarder already passes), a kind not allowed (415 or 422 `upload_refused`:
   "Add an image, a film or a .txt file"), a name already used (409 with no `error` code: the page tells it from the other two 409s
   because they carry `error` and it does not, and says the route's `detail`), the marking above the reader's clearance
   or the deployment's ceiling, a case reading a combined dataset (409 `composite_read_only`), a case reading a drawn
   dataset (409 `drawn_not_loaded`: "This case reads a drawn dataset: files are not added to it"), the store not writable (503:
   "The file could not be kept. Try again later")**, each above the form with the legal basis and marking kept and the
   file to be chosen again (a browser never keeps a chosen file). (b) The Conduit's detail.
7. **Who is offered it.** (a) **Offered from `GET /v1/me/rights` (`extract_files`) and the case's Editor level**, as GG4c
   and GR1b do; a hand post without them is GR1a's 404 page. (b) Offered to every reader.
8. **After the upload.** (a) **The `303` goes to GG3b's reader for the new document** (`/cases/document?case=…&document=…`),
   which reads it as the uploader may see it. The document also joins the case's working set by the route's delta, which
   no GOV.UK page shows until GG2e. (b) Back to the case page.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A 3 MB PNG (synthetic), marked OFFICIAL, a legal basis given | one `POST .../documents?name=…&classification=OFFICIAL&legal_basis=…` with the raw bytes; `303` to the reader of the new id | the multipart body sent to the Conduit as it came |
| 2 | The file is never held | the server half's memory does not grow with the file (a 200 MB synthetic stream, measured in the test) | `readUploadForm` used |
| 3 | `_csrf` not the first part, or wrong | refused 403 before a byte of the file is read; nothing sent | the token checked after the file |
| 4 | A field after the file | refused in words, nothing sent | the field read and dropped |
| 5 | A declared length over the cap | refused 413 before reading; the Conduit not called | the cap checked after the stream |
| 6 | An `.html`, an `.svg` and a `.pdf` named file | each refused in words by the route (`upload_refused` or 415); nothing kept | the page passing a different name than the file part's |
| 7 | Markings offered | only those at or below the reader's clearance, none chosen | the full scheme offered |
| 8 | A higher marking posted by hand | the route's refusal said in words; the legal basis kept | the 422 shown raw |
| 9 | No legal basis | the error summary; nothing sent | the request sent with `legal_basis=` empty |
| 10 | A case reading a composite; a case reading a drawn dataset; a name already used | "This case reads a combined dataset…"; the drawn sentence; the route's `detail` for the name | the three 409s said by status alone (all one sentence) |
| 11 | A Viewer, no `EXTRACT_FILES`, another unit's case | no link and no form; a hand post is GR1a's 404 page | the 403 said in words |
| 12 | `_csrf`, the session cookie and the browser's headers | none reaches the Conduit (only the forwarder's built headers) | the cookie copied upstream |
| 13 | The Conduit gives no answer, or is silent past the timeout | 502 or 504 page, "Nothing was added" | a `303` to a reader with no id |
| 14 | The fixture | refuses as the route does, in its order: the Editor gate, the composite and drawn checks, then the length, the name and type (plain `detail`, no `error`), the ceiling, the stream, then the service's (kind, marking) | a fixture that accepts an `.html` name |
| 15 | Keyboard and scripts off | the form whole: file, marking, legal basis, send; one case in `keyboard/document.spec.ts` (rule 13; I4) | the send button out of the tab order |

## Waits on

GG3b merged (its page and `document.ts`); the owner's word on question 3 (security). Nothing waits on GG2 or WS4b.
Question 5b (b), if taken, waits on its Conduit part.

## Files touched

`spec/08` (DR's adding rows); `apps/pages/server/forward.ts` (the translation factored out, no change in behaviour,
its own tests unchanged and green), `server/document.ts` (GG3b's page: `POST`, `upload: true`),
`server/views/documentWords.ts`; `tree-govuk/document.njk` and an add-file partial; `server/cases.ts` and
`tree-govuk/cases.njk` (the link); `test/govuk/document-add.test.ts`, `documentConduit.ts`, `keyboard/document.spec.ts`,
`scripts-off/document.spec.ts`; `test/server/forward.test.ts` (unchanged, run as the gate on the factoring).

## Checks (frozen when cut)

GG3b's list, with `apps/pages/test/server/forward.test.ts` and the anti-forgery tests (`csrf*.test.ts`).

## Out of scope

A holder (GG3d1's node, later); several files at once; designations and extraction; a list of the case's documents (no
route: an amendment); where the legal basis is kept (a Conduit question for the owner); any Conduit change;
`apps/workspace`.
