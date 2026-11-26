# Slice GG2c · GG2 · The working set's delta client moves to `glass-shared`, unchanged in behaviour, so a page module can hold the live working set (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** The scouts' cut of 20 November named "GG2b working set and delta client"
(`slices/STAGE4_SCOUTS_2026-11-20.md:86-88`); yesterday's GG2b draft proposed a saved view instead and moved "the delta
client's move" later. **The id is reassigned**: the scouts' cut gave GG2c to "canvas actions" (:87), which this plan
calls GG2g. **This is that move, on its own, with no page**: the same shape as PL4's moves into `glass-shared`
(ADR-152 decision 6: "a file is moved and re-imported"; invariant I11: "moving code into `glass-shared` changes
nothing", proved by the React workspace's whole suite and its budget before and after). It is the one prerequisite of
GG2e (the live working set on a page) that **draws nothing and touches no Sigma**, so decision 9 does not hold it, and
**it does not depend on GG2a's outcome**: a page module needs the live working set on Sigma 4 or on Sigma 3 alike.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The client.** `OspreyFlow_Core/apps/workspace/src/workingset/deltaClient.ts` (155 lines): `spec/03` §3.2's wire
  protocol, gap detection on every non-snapshot delta with a resync request, the retired `notice` step dropped
  (:28-38). **Its only import is a type from `@ospreyflow/glass-shared`** (`DeltaViewOverCap`, `LimitExceeded`,
  `WorkingSetDelta`, :26): no React, no DOM beyond a socket it is given. It takes a `createSocket` factory (header
  :6-14), and exports `connectDeltaClient`, `SocketLike`, `isWorkingSetDelta` (used by `deltaOps.test.ts:3`),
  `isViewOverCap`, `DeltaClient` (imported by `App.tsx:193`) and `DeltaClientHandlers`; the package must export each.
- **Its header is out of date.** It says "a browser-viable scheme is Checkpoint 2's decision to make" (:12-14). That was
  settled twice since: the workspace's own ticket (`/v1/ws-ticket`, which the page service's forwarder refuses to carry, `apps/pages/server/forward.ts:97-101`), and, for pages, CO3's proxy (`apps/pages/server/stream.ts:1-30`:
  the browser's upgrade carries only the session cookie; the proxy opens the Conduit's socket with the bearer; an
  `Origin` that is not the deployment's own is 403).
- **Who imports it.** `apps/workspace/src/App.tsx:195` (and :293, :1528, :1533) and
  `apps/workspace/keyboard/view-over-cap-harness.tsx:13`.
- **Its tests.** `deltaClient.test.ts` (127 lines), `deltaOps.test.ts` (25) and `deltaClient.integration.test.ts`
  (294), which "drives `deltaClient.ts` against the real `services.api.app` FastAPI app over a real socket" and "needs
  `make dev-up`'s stack". **Its header says it is skipped when the server cannot start (:11-13), but the code does not
  skip**: `startServer` rejects after 20 s (:54-59) inside `beforeAll` (:94-98), which fails the suite. It runs only
  through `test:integration` with its own configuration (`apps/workspace/package.json:11`).
- **The package.** `packages/glass-shared/src/workingset/` holds `store.ts`, `models.ts` and `batchExpansionApi.ts`;
  `src/index.ts` exports them (:90-91, :154) and lists each module in its header (:8, :38).

## Acceptance (red before, green after)

`packages/glass-shared/src/workingset/deltaClient.test.ts` (moved) and a new case that **the package exports
`connectDeltaClient`** (red today: it does not), green after; the React workspace's whole suite and its budget, run
before and after on the same machine, equal (I11).

## Questions for the owner (the proposal first)

1. **What moves.** (a) **`deltaClient.ts` and its two unit tests, by `git mv`, re-imported from `@ospreyflow/glass-shared`
   in the two importers**; the integration test stays in `apps/workspace` (it starts a real Conduit and needs the
   stack), importing the client from the package. (b) The integration test moves too, which brings a live-service test
   into the shared package's suite and its scan rows.
2. **The header.** (a) **Corrected in the move to say how each front end authenticates the socket today** (the
   workspace's ticket, the page service's proxy), with a citation for each, and nothing else in the file changed but its one import, which becomes relative (the package
   cannot import itself from `@ospreyflow/glass-shared`). (b)
   Left as it is.
3. **A browser socket factory for pages.** (a) **Not in GG2c.** GG2e writes the page module's factory (a same-origin
   `WebSocket` to the proxy's path, the cookie carrying the session). (b) Add it here, unused until GG2e.
4. **The I11 proof.** (a) **The workspace's whole suite and `perf.spec.ts`, before and after on one machine, recorded
   with the machine** (rule 14: under the stack lease if the stack is used; the integration test needs it, so it runs in
   the seat's container checks, through `test:integration`, or is reported as not run with the reason; it is never
   described as skipped, since it does not skip). (b) The moved unit tests
   alone.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The package exports the client | `import { connectDeltaClient } from "@ospreyflow/glass-shared"` type-checks and runs | today's package (red as it stands) |
| 2 | The moved unit tests | green in the package's own suite | a test left behind in the workspace that no suite runs (the file-coverage check finds it) |
| 3 | No React and no drawing library in the package | `no_react_check.mjs` and `version_isolation_check.mjs` green | a planted `import "react"` in the moved file |
| 4 | The workspace's importers | `App.tsx` and the harness import from the package; no file under `apps/workspace/src/workingset/deltaClient*` left but the integration test | a stale relative import kept beside the new one (two copies) |
| 5 | Gap detection unchanged | the out-of-order delta dropped and a resync asked, as before | the sequence check removed in the move (the moved test turns red) |
| 6 | The integration test | runs through `test:integration` against the real app where the stack is up, from the package's client; reported as not run, with the reason, where it is not | its import pointing at the deleted path |
| 7 | I11 | the workspace's whole suite and its budget equal before and after, on one machine | none: an equality, run once |

## Files touched

`packages/glass-shared/src/workingset/deltaClient.ts`, `deltaClient.test.ts`, `deltaOps.test.ts` (moved);
`packages/glass-shared/src/index.ts`; `apps/workspace/src/App.tsx`, `apps/workspace/keyboard/view-over-cap-harness.tsx`,
`apps/workspace/src/workingset/deltaClient.integration.test.ts` (imports only); the scan rows the file-coverage check
reads, if a test file moves (`process/lanes/v062/scan_rows/`).

## Checks (frozen when cut)

The workspace's whole suite (vitest, keyboard, a11y, perf) and `glass-shared`'s; `npm run typecheck` and `npm run lint`
in both; `node scripts/no_react_check.mjs`; `node scripts/version_isolation_check.mjs`; `test_file_coverage_check`;
`test_doc_citations_check.py`; the cheap checks of 20 November.

## Out of scope

The page module's socket factory and the live page (GG2e); any change in behaviour; the stream proxy; the Conduit.
