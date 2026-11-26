# Slice GG2e · GG2 · The case's live working set on a GOV.UK page: the graph module fed by the delta stream through the page service, read-only actions only (a draft; size L, proposed as GG2e1 and GG2e2)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **It draws with Sigma (4, or 3 on
the fall-back), so by decision 9 it may be written meanwhile but merges only after WS4b** (`spec/06_DECISIONS.md` about
lines 41101 to 41102).

**Where it comes from.** The `graph-canvas` and `working-set` rows of `FUNCTIONS.yaml` (:190-201). The scouts' GG2b
("working set and delta client"), which yesterday's GG2b draft moved later. It needs **GG2a's module**
(`mountGraph(container, { nodes, edges }, { channels, settings })`, `away/GG2a`'s report), **GG2c's client** in
`glass-shared`, **GG2b's page pattern** (a case's graph on the GOV.UK tree) and **GG2d's Matrix** (its textual
alternative).

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The stream.** `@app.websocket("/v1/investigations/{investigation_id}/stream")` (`services/api/app.py:22128`): on
  connect, and on any later `{"last_acknowledged_seq": …}`, "exactly what `WorkingSetService.sync` decides — the missed
  deltas, or a full snapshot … both already filtered for this connection's own principal"; live deltas from Valkey.
  Its own gates: an unresolvable principal 1008, a principal store down 1013, a principal admitted to named routes
  alone 1008 (ADR-148 Amendment 10), a ticket no longer in standing (Amendment 8) (:22140-22160).
- **The page service's proxy** (CO3, `apps/pages/server/stream.ts`): the browser's upgrade carries only the session
  cookie; the proxy opens the Conduit's socket with the person's bearer, renewed by `accessTokenFor` (PL9b). Refused
  before any upgrade: another path (404), an `Origin` not the deployment's own or none (403), no session (401), a store
  that cannot be read (503) (header :1-30). The path pattern is `STREAM_PATH` (:85); a browser frame is at most 1 MiB
  (:88) and at most 1 MiB may queue before the Conduit's socket opens (:90). The forwarder refuses to carry the stream
  over HTTP (`forward.ts:97-101`).
- **The store.** `packages/glass-shared/src/workingset/store.ts` (`applyDelta` over a graphology graph,
  `zustand/vanilla`) and `models.ts` (the typed deltas, `DeltaViewOverCap`, `LimitExceeded`).
- **The working set is the case's, kept once on the server, shared by the case's members and projected for each reader
  through their own access** (`services/api/working_set/service.py:1-30`). The React workspace and a page would show
  **the same set**, each reader's own projection of it, and a change made in either reaches the other by the same
  stream.
- **No HTTP read of the working set exists** (yesterday's GG2b draft: it is read only through the stream), so **with
  scripts off this page has nothing to show**, and decision 11 admits no new route without an amendment.
- **The canvas's read-only actions** in `CANVAS_ACTIONS` (`actionRegistry.ts:87-203`): zoom (:88), fit (:89), focus
  ring (:97-99), walking every node (:106-108), the focused node announced (:110), `l` stepping through (:171), `t`
  hiding the toolbar (:201), and the legend (:90-92). Pan, zoom and lasso are exempt from the registry (:80-85).

## Acceptance (red before, green after)

Scenario **GW** (new), written first; `apps/pages/test/govuk/live-graph.spec.ts` (Playwright, both browsers) red on GG2b's
page, green after: a seed made through the Conduit appears on the page without a reload, and a second reader's page over
the leak test's worlds shows only what the stream sent them.

## Questions for the owner (the proposal first)

1. **The split.** (a) **GG2e1: the subscription and the drawing** (the module connects through the proxy, applies the
   snapshot and the deltas to GG2c's store, and draws the store's graph); **GG2e2: the read-only actions** of question 4,
   each with its keyboard case. (b) One slice.
2. **Scripts off.** (a) **A parity line for the owner: "the live working set needs scripts"; the page says so in words
   and links to the case's saved views (GR1d) and their Matrix (GG2d)**, which hold the same kind of content as a
   snapshot. `PARITY_EXCEPTIONS.yaml` is the owner's to write. **The existing line `scripts-off-drawn-canvas`
   (`apps/pages/PARITY_EXCEPTIONS.yaml:45-48`) does not cover it**: its condition is "With scripts off a table takes the
   place of the graph", which a sentence and links do not meet; (a) would be a new line or a change to that one. (b) A new Conduit read of the working set as it stands
   (`GET .../working-set`), an amendment to decision 11, so the page can draw the Matrix with scripts off. (c) Your
   words. **The owner's: I4 says every page does its job with scripts off.**
3. **The address.** (a) **`/cases/graph?case=…`**, the query form, until GR1c; then `/cases/{case_id}/graph`. (b) Your
   words.
4. **The read-only actions (GG2e2).** (a) **Zoom, fit, the focus ring, walking every node, the focused node announced,
   `l` stepping through, the legend**, by id from `CANVAS_ACTIONS`, each with its case in the GOV.UK keyboard folder and
   `assertAllCovered` listing the rest as GG2f's and GG2g's. Selecting a node shows its label and type in a plain panel
   (the inspector is GG3d). (b) Your list.
5. **The cap on the stream** (`DeltaViewOverCap`, `LimitExceeded`). (a) **Said with its three options in the canvas
   prompt's words** (NEXT_BATCH question 9's proposal), the graph left as it was before the refused delta (never a part
   drawn), and the Matrix with it. (b) A sentence only.
6. **A socket that ends.** The proxy's refusals (403 `Origin`, 401 no session, 503) are handshake answers, which
   browser code cannot read: the socket simply fails to open (`stream.ts:15-20`). Every Conduit refusal before accept,
   a store outage included, reaches the browser as 1008 "the Conduit refused the connection" (`stream.ts:26-36`). So the
   page cannot tell an ended session from an outage by the socket alone. (a) **On any failure to open, or a 1008, the
   module asks the page service whether the session stands (a plain same-origin `GET` the page already serves, which
   redirects to sign-in when it has ended), and says "Sign in again" only when it has; otherwise "The live graph could
   not be reached. Try again", with one retry, never a loop.** (b) One sentence for every failure.
7. **The figures.** (a) **GG2a's perf spec over this page at 50k / 250k, with a snapshot of that size from a fixture
   stream**, under the CI gate GG2a set; recorded with the machine. (b) None: the page draws what GG2a measured.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Connect, a snapshot of 40 nodes | drawn, the ready mark set (GG2a's) | the readiness selector pointed at a mark never set |
| 2 | A seed made through the Conduit while the page is open | its nodes appear without a reload | the module reading only the first frame |
| 3 | A delta whose `seq` skips one | the resync asked; the graph equal to the server's after | GG2c's gap check bypassed |
| 4 | Two readers of different clearance | each page holds only what its stream sent; the Matrix counts only its rows | the fixture stream sending the higher reader's frame to both (the proxy must open each Conduit socket with its own person's bearer: the planted fault is a shared upstream socket) |
| 5 | An upgrade from another origin | refused by the proxy (403) before any upgrade; the page's own same-origin socket unaffected | the proxy's `Origin` check removed |
| 6 | The session ends while connected, and separately the Conduit's store is down (1008 for both) | "Sign in again" only for the first (question 6 (a)); "could not be reached" for the second; no retry loop | "Sign in again" on every 1008 |
| 7 | `DeltaViewOverCap` (sent in place of a snapshot, with no graph content: `glass-shared/src/workingset/models.ts:91-99`) | the three options in words; the graph and Matrix left as they were | the frame treated as an empty snapshot (the graph cleared) |
| 8 | Scripts off (question 2 (a)) | the sentence and the links | an empty canvas |
| 9 | The read-only actions (GG2e2) | each reachable and working, one case per id; `assertAllCovered` red with one removed | an offered id with no case |
| 10 | No internal id in the HTML or the live region | none | a node id announced |
| 11 | The policy | no `securitypolicyviolation`; no request to another origin (I2, I3); the socket same-origin | a socket opened to the Conduit's own address |
| 12 | The budget | under GG2a's CI gate, three runs, recorded | none: a measurement |

## Files touched

`spec/08` (GW); `apps/pages/modules/graph/` (a live entry beside GG2a's), the module's socket factory;
`apps/pages/server/` (the page), `tree-govuk/` (its template); `PARITY_EXCEPTIONS.yaml` **only by the owner** (question
2 (a)); `test/govuk/live-graph.spec.ts`, `keyboard/`, `scripts-off/`, `csp/`; `test_pages_setting.py` (the route list).

## Checks (frozen when cut)

GG2b's list, plus the stream proxy's own tests (`apps/pages/test/server/stream*.test.ts`) and the X2 tests of decision
11 (`test_the_stream_through_pages_carries_only_what_the_person_may_read` and its two siblings).

## Out of scope

Seeding, expanding and the cap's batch job (GG2f); editing actions (GG2g); the inspector (GG3d); any Conduit change
unless question 2 (b); `apps/workspace`.
