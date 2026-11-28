# Slice GG2f2 · GG2 · The cap's third choice on the GOV.UK pages: a batch expansion started, followed and opened, and adding many by a pasted list (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GR1d`. No row in `slices.tsv`; no builder
starts from this paper. **Size M** (the second half of the plan's GG2f, L). **The batch page itself draws nothing with
Sigma**, but it is reached from GG2f1's refusal on the live page and belongs to the `working-set` row, which decision 9
holds with the rest of R4 ("the rest of R4 may be written meanwhile, but it waits to merge", `spec/06_DECISIONS.md`
about line 41102). **It merges after WS4b unless the owner makes it a second exception beside GG2c** (question 9).

**Where it comes from.** The plan's row GG2f ("GG2f2 batch expansion"); the `working-set` row of
`apps/pages/FUNCTIONS.yaml` (:197-203, "cap refusal, batch expansion"); ADR-151 (`spec/06_DECISIONS.md` :39711 onward),
the cap's third choice "promote to a batch job whose result is a saved subgraph". It follows GG2f1's refusal (its *Run
as a batch job*) and GR1d's write pattern (a page `POST` with `_csrf`, one Conduit call by the server half, a `303`).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`):
  - `POST .../batch-expansions` (:4834-4858), 202, `require_right(INVESTIGATE)` and the case's **Editor** gate. Body
    `BatchExpansionInput` (`packages/schemas/batch_expansion.py:28-37`, `extra="forbid"`): `request` (`ExpandRequest`),
    `justification`, `name` (1 to 200). "Reads nothing from the graph and adds nothing to the working set". One at a
    time: **409 `{"error": "batch_expansion_running", "detail", "id"}`** (ADR-151 decision 2; words
    `services/api/batch_expansion.py:67-70`).
  - `GET .../batch-expansions/{job_id}` (:4861-4871), the case's **Viewer** gate: "The job as its requester is told it;
    anyone else's is not found" (404). `BatchExpansion` (`batch_expansion.py:51-66`): `id`, `state` (`queued`,
    `running`, `done`, `refused`, `failed`), `words` "always a whole sentence", `view` (a `CaseView` when done),
    `nodes`, `links`, `refusal` (`code`: `too_many_nodes`, `too_many_links`, `found_nothing`, `no_longer_an_editor`,
    `took_too_long`; `cap_kind`, `cap`, `would_be`).
  - ADR-151 decision 4: "The Glass polls every two seconds"; `failed` is said in the ADR's words only, never an
    exception's text; decision 5: never cut; past the view's cap it is refused with figures and nothing is saved; the
    result is a **private** view of the requester.
  - `POST .../working-set/add-by-identifiers` (:5819-5884), Editor: `AddByIdentifiersRequest`
    (`services/api/add_by_identifiers.py:86-95`): `identifiers` (strings, each may hold several), `confirm` (false
    counts, true adds), `with_links`. Answers `counts` (`IdentifierCounts`, :70-83: `read`, `found`, `matched_nothing`,
    `repeated`, `undecided`, `records`) and `added` when confirmed. **"An identifier that does not exist and one the
    analyst may not see are one figure"** (the docstring, :5833-5840). More than 5,000 is **413
    `too_many_identifiers`** with the figure, never cut (`app.py:3138-3152`). The add goes through `seed`, so past the cap
    it is the 409 `limit_exceeded`.
- **Plain TypeScript already in `glass-shared`:** `workingset/batchExpansionApi.ts` (171 lines: `startBatchExpansion`,
  `readBatchExpansion`, every state checked at compile time, the request's three fields picked by name so "a misspelt
  field would run the expansion over every type" cannot happen, :114-123), and `search/addFromListApi.ts`
  (`countSentence`, "40 identifiers read. 38 found. 2 matched nothing you can see. 1 repeated.", :38-52; `listFromFile`;
  `MAX_IDENTIFIERS`). Both take a bearer and call the Conduit directly: on a page the bearer is the server's.
- **The React panel** `apps/workspace/src/workingset/BatchExpansion.tsx` (302 lines): its fallback refusal words (:53-60),
  "Closing this does not stop the job…" (:273-275), and its 403 sentences (:215-228).
- **NEXT_BATCH question 9** (`slices/NEXT_BATCH_2026-11-24.md:45`) proposed that "the batch one is aligned to" the canvas
  prompt's words "by GG2d". GG2d is now the Matrix (the owner, 26 November), so **that alignment has no slice**.

## Acceptance (red before, green after)

Scenario **GW**'s batch and add-by-list rows, written first; `apps/pages/test/govuk/batch-expansion.test.ts` and
`add-by-list.test.ts` (the server pages, scripts off, against the fixture Conduit), and one Playwright case from GG2f1's
refusal to the job page, red before, green after.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **The batch job: started from GG2f1's refusal, followed on a page of its own, its view opened; and
   *Add many from a list* as a pasted-text form, counted first, then added.** Both are server pages whose writes end at
   the cap's choices. (b) The batch job only; the list as its own part.
2. **Where the job is followed.** (a) **`/cases/graph/batch?case=…&job=…`**, the query form (GR1a question 1 (a)),
   with a row of its own in `FUNCTIONS.yaml` (`working-set-batch`), as GR4a's board page got one. (b) A part of GG2e's
   live page: it would then need scripts, and a job outlives the page.
3. **Starting it.** (a) **GG2f1's *Run as a batch job* is a plain form**, posting to the page service with `_csrf` and
   the refused request in hidden fields (the node id, `depth`, the one link type if any), and an optional name; the
   server half sends exactly that `ExpandRequest` (the three fields picked by name, as `batchExpansionApi.ts` does), then
   `303` to the job page. A 409 `batch_expansion_running` is a `303` to the running job's page with the route's own
   `detail` said once. (b) The module calls the route itself: two paths for one write.
4. **Following it.** (a) **Server-rendered from one `GET` per render: `words` as given, and a "Check again" link.** With
   scripts on, the module reads the same route every 2 seconds through the forwarder (ADR-151 decision 4) and replaces
   the status in a polite live region, stopping at `done`, `refused`, `failed` or a 404; **no automatic reload with
   scripts off** (no `meta refresh`: WCAG 2.2.1). (b) A `meta refresh`: not proposed.
5. **Done.** (a) **"Open the view" links to GG2b's `/cases/views?case=…&view=…`** (the form GR1d's links already use);
   `nodes` and `links` said in words. A view since deleted is the route's `words` (`GONE_WORDS`). (b) Your words.
6. **The words of a refusal.** (a) **The route's `words`, always**, since ADR-151 makes them whole sentences; the page
   adds only "Nothing was saved." where the words do not already say it, and never an exception's text. A `failed` job
   offers "Start it again", which posts the same request. (b) The page's own sentence per code.
7. **The NEXT_BATCH alignment** (question 9's, now homeless). (a) **The page's batch words follow the canvas prompt
   (`spec/02` :997-1008) and ADR-151's own sentences; the React panel's fallback words are left as they are, and the
   difference is written as a backlog row for the workspace** (this slice touches no React). (b) This slice also changes
   `BatchExpansion.tsx`.
8. **Add many from a list, scripts off.** (a) **At `/cases/graph/add?case=…` (its own row, `working-set-add`): a
   textarea, then "Count them", one call with `confirm: false`, the counts said with `countSentence` exactly; then "Add
   ‹records› to the graph", the same identifiers re-sent with `confirm: true`** (kept in the session between the two
   steps, never in the page, so nothing typed is echoed into a hidden field). **The session copy is bounded**: the
   page refuses before counting, in words and with the figures, a paste over the forwarder's body cap
   (`OSPREY_PAGES_BODY_MAX_BYTES`) or holding more than 5,000 identifiers once split as `split_identifiers` splits
   them ("You pasted ‹n› identifiers; at most 5,000 can be added at once. Nothing was added."), never cut; the copy is
   dropped after the add, after a refusal, and when the form is left; `with_links` as a checkbox, off by default.
   413 said with its figure; a 409 `limit_exceeded` is GG2f1's refusal page. **A file is not offered in this slice** (the
   forwarder's multipart translation covers four routes only, `forward.ts:47-52`, and this route takes JSON); the
   React's `listFromFile` reading is a later part. (b) Offer a file through the page service's own multipart reader.
9. **Merge order.** (a) **After WS4b, with the rest of R4**, since its only way in is GG2f1's refusal. (b) The add-by-list
   page before WS4b, by the owner's exception (it draws nothing): **owner, a decision 9 exception.**

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | An Editor chooses *Run as a batch job* on a refusal of an expansion by `ASSOCIATE_OF`, depth 2 | one `POST .../batch-expansions` with exactly `{request: {node_ids: [n], depth: 2, edge_types: ["ASSOCIATE_OF"]}}`; `303` to the job page | `edge_types` dropped (the batch would run over every type: the fixture asserts the body) |
| 2 | The same with a name typed | `name` sent; 201 characters refused on the page, nothing sent | the name sent unchecked and the 422 shown raw |
| 3 | The reader already has one running (409) | `303` to the running job's page; the route's `detail` said once | the 409 shown as a failure |
| 4 | Job `queued`, then `running` | the route's `words` each time ("Expanding from 12 nodes"); "Check again" | a sentence of the page's own in place of `words` |
| 5 | Job `done` | "Open the view" to `/cases/views?case=…&view=<id>`; `nodes` and `links` said | the view's id printed as text |
| 6 | Job `refused` `too_many_nodes` (63,412 against 50,000) | the route's words with the figures; "Nothing was saved." once | the refusal said with no figure (rule 2) |
| 7 | Job `failed` | ADR-151's sentence; "Start it again" posts the same request | the fixture's exception text shown |
| 8 | Another person's job id, or a made-up one | GR1a's 404 page | the 404 said as "not yours" |
| 9 | Scripts on | the status changes in place every 2 s; reads stop at a final state | reads that never stop (the fixture counts them) |
| 10 | Scripts off | no automatic reload; the page whole with "Check again" | a `meta refresh` |
| 11 | A Viewer posts the start form by hand | the route's 403 in the page's words; nothing queued | the form offered to a Viewer |
| 12 | Paste 40 identifiers, count | one call with `confirm: false`; `countSentence`'s words exactly | the counts drawn from the page's own split |
| 13 | Then add | one call with `confirm: true` whose `identifiers` equal the session's copy exactly; no identifier anywhere in the HTML, a hidden field included; `303` to the live page | the identifiers written into a hidden field of the add form (the HTML assert) |
| 14 | 5,001 identifiers | refused on the page in words with the figure before any call (and the route's 413 said the same way if it is reached); nothing added; nothing kept in the session | the list cut to 5,000 by the page |
| 15 | The add past the cap | GG2f1's refusal page with the three choices | the 409 said as a failure |
| 16 | No `_csrf` on any form | refused, nothing sent (I17) | a handler outside the check |
| 17 | A body missing a field `BatchExpansion` requires | "could not be read" (502) | each required field removed in turn |
| 18 | Keyboard and scripts off | each form and link reachable; the status region polite (rule 13, I4) | the status out of the live region |

## Waits on

GG2f1 (the refusal and its form); GG2b (`/cases/views?case=…&view=…`, where a done job's view opens); GR1d (the write
pattern); **WS4b to merge** (decision 9, unless question 9 (b)).

## Files touched

`spec/08` (GW's rows); `apps/pages/FUNCTIONS.yaml` (two rows); `apps/pages/server/` (the two pages and their words
files), `pageList.ts`, `tree-govuk/routes.yaml` and two templates; `apps/pages/modules/graph/` (the refusal's form, the
job page's reading); `test/govuk/batch-expansion.test.ts`, `add-by-list.test.ts`, `keyboard/`, `scripts-off/`, the fixture
Conduit's routes; `tests/harness/test_pages_setting.py` (the route list); the backlog row of question 7.

## Checks (frozen when cut)

GG2f1's list.

## Out of scope

A file of identifiers (question 8); the React panel's words (question 7); the SSE job stream (ADR-151 decision 4: not
built); any Conduit change; `apps/workspace`.
