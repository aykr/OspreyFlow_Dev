# Slice GG3d1 · GG3 · The inspector on the live graph page, read-only: a selected node's properties and who shares its contacts; a selected link's details, history, events and notes (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** The first half of the plan's GG3d (L, split: GG3d1 the reads, GG3d2 notes and link change as forms).

**Where it comes from.** The plan's row "GG3d: the inspector for a selected node or link (history, events, notes, shared
contacts), then link change as a form | GG2e (a selection) | … none: it needs the canvas's selection"
(`slices/drafts_2026-11-26/CHAIN_PLAN.md:76`). `FUNCTIONS.yaml` row `inspector`
(`OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:213-219`: "Inspector (link change, notes, events, risk)", scenario B11,
slice "R5", no route). PL8b's frame names `inspector` as a side panel id (`slices/drafts_2026-11-26/PL8b.md`, question
2). **Its host draws with Sigma, so by decision 9 it may be written meanwhile but merges only after WS4b and GG2e**
(`spec/06_DECISIONS.md:41091-41116`).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **Every link read needs the link in the case's working set.** Notes, history and events each ask
  `WorkingSetService.visible_edge`: "the link's own marking and both of its ends must clear the principal's clearance,
  and the link must be in this investigation's working set. A link the principal cannot see answers exactly as a link
  that does not exist (`LinkNotFoundError`)" (`services/api/link_notes.py:7-23`; `link_changes.py:23-24`, :346-348;
  `link_events.py:8-10`). One answer, **404 `link_not_found`** (handler `services/api/app.py:3475-3479`). **So the
  inspector belongs to the live working set, not to a saved view**: a saved view's link that is not in the working set
  answers "not found" on every one of these reads.
- **The routes** (`services/api/app.py`), each `require_right(INVESTIGATE)` and the case **viewer** gate:
  - `GET .../links/{edge_id}/history` (`link_history_route`, :7739-7752): `LinkHistoryResponse`
    (`services/api/link_changes.py:202-205`: `changes`, and `truncated`, "said, never silently shortened"). Each
    `LinkChange` (:138-150) has `changed_by` (**a principal id**), `changed_at`, `reason`, `before`, `after`.
  - `GET .../links/{edge_id}/events?offset=&limit=` (`list_link_events_route`, :7755-7770): newest first, 50 by
    default, at most 200, with `total` (`LinkEventListResponse`, `link_events.py:33-37`). Each `EventRecord`
    (`packages/schemas/analytics.py:31-53`) carries `edge_id`, `source_id`, `target_id` (graph ids) and `load_id`.
  - `GET .../links/{edge_id}/notes` (`list_link_notes_route`, :8730-8745): newest first; **`author_name` resolved by
    the route** from `principal_names.display_names` (:8742-8744), and `mine` per reader (`LinkNote`,
    `packages/schemas/domain.py:2090-2104`).
  - `GET .../nodes/{node_id}/shared-contacts?edge_type=&limit=` (`shared_contacts_route`, :7062-7085): limit 10 by
    default, at most `EXPLORE_MAX_PAGE` (50, :6800); `SharedContacts` (`packages/schemas/explore.py:192-198`:
    `contacts`, `total`, "rule 2"). "A node the reader cannot see shares with nobody."
  - **These three link reads are not audited** ("Not audited, like the other case reads here", :7749-7751, :7768-7769,
    :8740-8741); shared contacts is (:7078-7084). Recorded, not changed.
  - **No HTTP read of one node, or of the working set** (GG2e's draft, and `services/api/working_set/service.py`): a
    node's properties and a link's ends and type reach a page only through the delta stream.
  - Left for later: neighbourhood risk (`GET .../risk/{node_id}`, :14898, behind **`TRACE_OWNERSHIP`**, the Ownership
    view's right: GG4h), strength explained (ADR-139 decision 9), judgements (:7476), the entity's picture (:7971 on).
- **The React inspector** (`apps/workspace/src/inspector/`): `Inspector.tsx` (683 lines; the node's properties from the
  working-set graph with internal references left out, `propertyNames.ts`, :581-586; "Relationships" counted in the
  view, :594-617), `LinkDetails.tsx`, `LinkHistory.tsx` and `describeChange.ts`, `LinkEvents.tsx` (paged; an email
  opened in the reader by `emailDocumentId`, `packages/glass-shared/src/reader/readerApi.ts:169`), `LinkNotes.tsx`,
  `SharedContacts.tsx` (one ask per link type the node can start, `contactTypes`, :33-35). **The clients are already shared**:
  `packages/glass-shared/src/inspector/` holds `linkEventsApi.ts` (`fetchLinkEvents` :25, `EVENTS_PAGE_SIZE` 50 :7,
  `eventsNoun` and `nounWords` :59-76), `linkNotesApi.ts`, `linkChangeApi.ts` and `emailDocuments.ts`. The parts'
  drawing, `describeChange.ts`, `propertyNames.ts` and `contactTypes` are React-side.
- **Keyboard.** `INSPECTOR_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:860-880`) and
  `LINK_EVENTS_ACTIONS` (:426-438). Most entries write (GG3d2's, GG2f's or GG4's); the reads here are
  `a-part-opens-and-folds-by-keyboard` and `events-list-newest-first-and-show-more-by-keyboard`.

## Acceptance (red before, green after)

Scenario **IN** (the inspector on the GOV.UK tree), written first: B11 (`spec/08_ACCEPTANCE_SCENARIOS.md:562`) attributes
by a manual link and is GG3d2's at most; **no scenario reads the inspector by itself**. `apps/pages/test/govuk/inspector.test.ts`
(the server half and the shared view model) and `test/govuk/live-inspector.spec.ts` (Playwright, on GG2e's page), red
before, green after.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Reads only.** A node: its name, type and marking, its properties (internal references left out),
   its links in the working set counted by type, and who shares its contacts, asked per link type. A link: its type,
   ends, marking and properties, its history, its events and its notes. No writes (GG3d2), no expansion or "add the pair
   to the graph" (GG2f), no risk (GG4h), no strength, judgements or picture (question 8). (b) With risk, for a reader who
   holds `TRACE_OWNERSHIP`.
2. **Where it lives.** (a) **A side panel of GG2e's live graph page (`/cases/graph?case=…`), in PL8b's frame as the
   `inspector` panel**, filled by the module's selection. It merges after GG2e, PL8b and WS4b. (b) A part of GG2b's saved
   view: **not proposed**. Every link read answers through `visible_edge`, which needs the link in the working set, so a
   view's link outside it would say "not found" on every read.
3. **Who draws it.** (a) **One pure view model in `packages/glass-shared/src/inspector/` (the parts and their words,
   from the store's node or link and the routes' answers), drawn by the module with `textContent` (decision 3) and by
   the server's template from the same function**, so the two never drift. The module reads through the `/v1`
   forwarder, with decision 3's latest-answer-wins guard (a second selection cancels the first's reads). The server
   draws it for an address with `&link=<id>` or `&node=<id>`, which GG3d2's forms return to after a `303`. (b) The
   module only.
4. **What the server can draw by itself.** A node's properties and a link's ends and type are in the working set, which
   has no HTTP read. (a) **The server draws every part it can read by id** (history, events, notes, shared contacts) **and
   says the rest in words** ("This link's details are on the live graph"); the module fills them in when it has the
   store. With scripts off the page is GG2e's parity line ("the live working set needs scripts", ruled 26 November), and
   the inspector's id-read parts still do their job. (b) A Conduit read of one node or link by id, so the server draws
   everything. **An amendment to decision 11 (owner).**
5. **Who shares contacts.** (a) **One button per link type the node's type can start (`contactTypes`, moved to
   `glass-shared`), each one read when pressed, never at selection.** The answer is said with the route's `total`: "12
   share at least two contacts; the 10 most are shown", and "Show more" asks again with a larger `limit`, up to the
   route's 50, then says "The 50 most are shown of 120" (rule 2: never a silent cut). (b) Asked for every type on
   selection.
6. **A link's events.** (a) **Fifty a page, newest first, "Emails 1 to 50 of 312" (the route's `total`), with "Newer"
   and "Older".** An email's subject and time; "Read" links to GG3b's reader (`/cases/document?case=…&document=…`,
   `emailDocumentId`). No `source_id`, `target_id`, `edge_id` or `load_id` drawn (rule 7). Extraction is GG3d2's or
   later. (b) The route's first page only.
7. **The history and the notes, and who made them.** (a) **A change says when and why, and what changed in words
   (`describeChange.ts`, moved to `glass-shared`), never who: `changed_by` is an account id, and "who made it" is left
   out for 0.7.0** (ruled 26 November). `truncated` is said ("Older changes are not listed"). **A note shows no author
   either**: the same ruling covers it (names later through `display_names`, which the notes route already calls,
   `app.py:8742`, a backlog part). A note says its time, "edited" with its time, and "yours" when `mine` (the reader's
   own, which names no one else). (b) **Show `author_name` as the route sends it, "someone in this case" when empty: a
   narrowing of the 26 November ruling for notes alone, the owner's to give (owner).**
8. **Left out, for later slices.** (a) **Strength explained, judgements, the picture and risk each go to the slice that
   owns them** (strength to GG4i's metrics, risk to GG4h, the picture to GG4f's picture pattern, judgements to a later
   GG3 slice), each named in the panel's census as left out. (b) All in this slice.
9. **Keyboard.** (a) **The panel's parts open and fold by keyboard (`a-part-opens-and-folds-by-keyboard`), events page
   by keyboard (`events-list-newest-first-and-show-more-by-keyboard`), and the shared-contacts ask; one case each in the
   GOV.UK keyboard folder, `assertAllCovered` naming every other `INSPECTOR_ACTIONS` and `LINK_EVENTS_ACTIONS` id as
   GG3d2's, GG2f's or GG4's** (rule 13). (b) Your list.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Select a node (synthetic "Harbour Freight Ltd") | its name, type, marking and properties; no internal reference | a property named by `isInternalReference` shown |
| 2 | Select a link with three recorded changes | three rows, newest first, each its time, reason and change in words; no account id | `changed_by` printed |
| 3 | History with `truncated: true` | "Older changes are not listed" | the flag ignored |
| 4 | A link with 312 events | 50 rows; "Emails 1 to 50 of 312"; "Older" asks `offset=50` | `limit=200` asked and the rest dropped |
| 5 | An email's "Read" | GG3b's address with its document id | a link built from `event_id` without `emailDocumentId` |
| 6 | Notes: one the reader's, two a colleague's (one with `author_name`, one without) | "yours" on the first; no author on any; no account id | `author_name` or `author` drawn |
| 7 | Shared contacts by one type, `total` 12 | one read, `edge_type` named, "the 10 most are shown"; "Show more" asks a larger limit | the list drawn with no `total` (a silent cut) |
| 8 | Two quick selections | only the second's answers drawn | the first's late answer drawing over the second (the guard removed) |
| 9 | A link the reader may not see, or one not in the working set | each read's 404 `link_not_found` said as "This link is not in the case's graph" | the 404 drawn as an empty history |
| 10 | Two readers of different clearance, the leak test's worlds | each panel shows only what that reader's reads sent; no count of the other's | the server half caching one reader's answers by link id and serving them to the next reader (or reading with one fixed bearer, not the person's own) |
| 11 | No level on the case, no `INVESTIGATE` (every read here is Viewer-gated, so no level is "too low") | GR1a's 404 page (server) or "could not be read" (module) | the 403 said in words |
| 12 | The server draws `&link=<id>` | the history, events and notes drawn; the details said as on the live graph | the template drawing details it cannot have read |
| 13 | The view model's two callers | the module's DOM and the server's HTML hold the same words for one answer | a word changed in one caller only |
| 14 | A body missing a field each answer's type requires | "could not be read" | each required field removed in turn |
| 15 | The fixture | refuses as the routes do: 404 `link_not_found` for a link outside its working set, the events' 422 above `limit` 200, shared contacts' above 50 | a fixture that lists events for any edge id |
| 16 | Keyboard | each id in question 9 proven end to end; `assertAllCovered` red with one removed | an offered id with no case |

## Waits on

GG2e (the page and the selection), PL8b (the frame's `inspector` panel), GG3b (the events' "Read" link to the reader) and
GG3c in the lane before it; merges only after WS4b (decision 9). Question 4 (b), if taken, waits on the owner's
amendment.

## Files touched

`spec/08` (IN); `apps/pages/FUNCTIONS.yaml` (`inspector`: scenario, route stays GG2e's page); `packages/glass-shared/src/inspector/`
(the view model; `describeChange.ts`, `propertyNames.ts` and `contactTypes` moved, I11) and their tests, re-imported by
`apps/workspace/src/inspector/`; `apps/pages/modules/graph/` (the panel's attach, on GG2e's entry); `apps/pages/server/`
(GG2e's page: the `&node=`/`&link=` reads), `server/views/inspectorWords.ts`; `tree-govuk/` (the inspector partial in
PL8b's frame); `test/govuk/inspector.test.ts`, `live-inspector.spec.ts`, `inspectorConduit.ts`,
`keyboard/inspector.spec.ts`; `OspreyFlow_Build/tests/glass_trees/test_govuk_inspector_scenario.py` (the census of
`LinkHistoryResponse`, `LinkEventListResponse`, `LinkNoteListResponse`, `SharedContacts`).

## Checks (frozen when cut)

GG2e's list, with the inspector's tests, and the React workspace's whole suite for the moved helpers (I11).

## Out of scope

Every write (notes and link change: GG3d2; the pair to the graph and expand: GG2f); risk (GG4h); strength, judgements and
the picture (question 8); extraction from an email; any Conduit change unless question 4 (b); `apps/workspace` beyond
re-imports.
