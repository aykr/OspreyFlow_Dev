# BL3, front-end questions answered with evidence (Step 0): the refresh of 21 November 2026

**What this is.** The 14 questions in section 11 of the parallel front-end specification were answered on 18 November 2026 from `main` at `528d475`, read only (`ospreyflow_evidence_2026-11-18/FRONT_END_ANSWERS.md`, git-ignored). This is the refresh against today's main, after ADR-152 and its amendments, the PL4 moves and IS5a0. It was made by a read-only scout that ran nothing (no test, build, browser or sweep), so it is **not a seat**. Line numbers in `spec/06_DECISIONS.md` are the scout's, found by search and approximate ("near N"). Where the scout did not read a thing, the cell says so. Nothing here is a decision; where a choice is the owner's it is marked and goes to him in one numbered list.

Path roots: C = `OspreyFlow_Core/`, B = `OspreyFlow_Build/`.

## A. The 14 questions: is the 18 November answer still true?

| Q | Status | Now (file and line) |
| --- | --- | --- |
| 1 React-free code | Changed | The 191 files / 19,543 lines is a 528d475 measure, not recounted. Modules have moved to `C packages/glass-shared/src` (`ingest/api.ts`, `alerts/api.ts`, `workingset/store.ts`). |
| 2 The Studio's slices | Still true (client gap); counts not rechecked | Conduit model routes at `C services/api/app.py` lines 11776, 11789, 11808, 11852. No Glass client for model, draft or make-live (searched `glass-shared` and `apps/workspace/src`: none). Pages has no Studio page yet (`C apps/pages/server/pageList.ts:4`). |
| 3 Sign-in | Changed for pages | Pages signs in on the server with a session: `C apps/pages/server/expressStore.ts:7-8` (idle hour, eight-hour cap), `sessionPolicy.ts`; ADR-050 Amendment 4 (near line 41324). Browser Glass unchanged: `C apps/workspace/src/auth/userManager.ts:129-147` (in-memory storage at 146). Valkey `noeviction` now `C harness/render.py:875`. |
| 4 Token checking | Changed | Entra `pages_client_id` exists: `C packages/principal_auth/__init__.py:270`, validated 298 to 306, admitted 993 to 994. The Keycloak branch past line 1004 was not read. ADR-152 X1 (near 41143). |
| 5 Live updates | Still true, lines moved | Socket route `C services/api/app.py:21579`; bearer header read first 21317-21321; ticket fallback 21323-21329. Pages' stream checks Origin exactly: `C apps/pages/server/stream.ts:292-293`. |
| 6 Gates | Still true | The four gates are React-only. `C apps/pages/test` holds `server/`, `support/`, `fixtures/` only: no keyboard, accessibility, performance or CSP folder. ADR-152 decision 6 names them; they are not built. |
| 7 The tree | Settled by ADR-152 | Decision 6 (near 41022 to 41050), decision 7 (near 41071), Amendments 3 and 4 (near 41727, 41759). `C packages/design` holds `tokens.css`, `primitives.css`, `scale.css`, `panelType.css`, `fonts.json`; `C apps/workspace/src/design` keeps `fonts.ts` and `tokens.css.d.ts`. `C apps/pages` has `tree-default/` (layout, home, error) and no `tree-govuk`. |
| 8 Licences | Changed | Npm licences now stated: `B spec/00_ARCHITECTURE.md` near 1199-1206 and 1218-1223 (openid-client, oauth4webapi, jose). helmet, express, nunjucks, ioredis, govuk-frontend are in `C node_modules`. PL11's table (`PL11_LICENCE_TABLE_2026-11-21.md`) covers the default install's weights, fonts and images, not npm. |
| 9 Inventory | Changed | `C apps/pages/FUNCTIONS.yaml` (47 rows with status); `C apps/pages/PARITY_EXCEPTIONS.yaml` (the owner's 20 November lines). |
| 10 Security policy | Changed (section C) | MapLibre is no longer 4.7.1: `C apps/workspace/package.json:36` is `^6.4.1`, installed 6.19.0. Pages' policy exists: `C apps/pages/server/headers.ts:33-47`. |
| 11 The panel pattern | Still true; a proposal | Accepted in ADR-152 decision 3 (near 40995). Not yet in `C packages/glass-shared` (no `attach` or `data-action` found). |
| 12 A1 | Settled; cost changed | ADR-152 decision 1 and the row "F3 + A1" (near 40963). Amendment 3 (near 41732 to 41749): the page service is off by default, per deployment. **`pages.enabled` is not yet in `C packages/schemas/deployment.py`** (search: no match). |
| 13 A6 | Settled by ADR-152 | A6 row (near 40968); decision 6, `tree-default` (near 41037). RULINGS of 20 November moves `primitives.css` to `packages/design`. |
| 14 Scenarios | Partly settled | Decision 12 (near 41155): scenario first. `FUNCTIONS.yaml`: 20 of 47 rows name a scenario, 27 have none. `spec/08` not checked for new scenarios. |

## B. The 18 November decisions for the owner (MORNING.md items 6 to 11)

| Item | Decided or open | Where | Options; the scout's lean |
| --- | --- | --- | --- |
| 6 F6 against the tree rule and ADR-132 | **Decided** | Decision 6 (near 41022): "the owner's word on this table is the lifting of the restructuring constraint"; decision 13 "Replaced" (near 41167): "a switch, not a fork" and ruling 4; Amendment 4 item 3 (near 41775) | none |
| 7 A1, the default theme's Studio as pages | **Decided in principle; default-on is open** | F3+A1 (near 40963); Amendment 3 items 1, 2, 5 (near 41732 to 41749): off until the owner turns it on; the default stays off until a later amendment | (a) off until a Studio page exists, as written; (b) on for the default theme when IS5a lands; (c) on for all at the cutover. Files: `C packages/schemas/deployment.py` (the setting), `C harness/render.py:617` (`service_images`). Lean: (a) |
| 8 A6, own components as Nunjucks or restyled GOV.UK Frontend | **Decided** | A6 row (near 40968); decision 6 (near 41037) | none |
| 9 Re-slice | **Partly open** | The working set is GG2 (`FUNCTIONS.yaml`). The IS5 cut is agreed (RULINGS 20 Nov near 329-331). The status bar is still "owner to rule" (`FUNCTIONS.yaml`; `PARITY_EXCEPTIONS.yaml` header near 15-17). `studio-map-step` has no owner named. A3's cross-filter rows are still split (the query builder is R6) | Status bar: (a) its own row in the shell slice; (b) fold into the top-bar row; (c) the owner's line-by-line exception. Lean: (a). Map step: (a) IS3; (b) a new IS slice; (c) fold into IS5. Lean: name an IS slice before IS3's brief |
| 10 `ProposedTypes.tsx` | **Decided** | `C apps/pages/PARITY_EXCEPTIONS.yaml:25-28` (whole function, "agreed: the owner, 20 November 2026"); `FUNCTIONS.yaml` `admin-proposed-types`. Not checked: whether the `.tsx` is deleted, and spec/02's self-contradiction | none |
| 11 Scenarios for I8 | **Decided as a rule; open per row** | Decision 12 (near 41155); 27 of 47 rows have none | (a) per slice, before its page, as written; (b) a batch now for the 27 rows; (c) a narrower I8. Lean: (a), with (b) for the first builds |

## C. The security-policy answer GG5 waits for (question 10)

**What reading establishes**

- The React Glass has **no CSP** (`C apps/workspace/nginx.conf.template` has only Cache-Control headers, lines 124, 135, 140). Still true.
- Pages' policy as built (`C apps/pages/server/headers.ts:33-47`): `default-src 'self'`; script and style with a nonce; `img-src 'self' data:`; `worker-src 'self'`; `connect-src 'self'`; `frame-src 'none'`; no `unsafe-inline`, no `unsafe-eval`. It matches ADR-152 decision 8 (near 41081). **It has no `blob:` in `img-src`.**
- MapLibre: the workspace pins `^6.4.1` (`C apps/workspace/package.json:36`), which is decision 9's `>=6.4.1 <7` (near 41091); installed 6.19.0 (`C node_modules/maplibre-gl/package.json:4`). **The installed package ships no CSP build** (only `maplibre-gl.mjs`, `-worker.mjs`, `-shared.mjs` and the CSS). **The 18 November claim of a CSP build is void.**
- The worker: `C apps/workspace/src/map/maplibreWorker.ts:10-18` imports it with `?url` and calls `setWorkerUrl`, so it is served from the page's own origin. Read from the minified bundle: a same-origin worker takes the direct `new Worker(url, {type:'module'})` path (`maplibre-gl.mjs` line 5), so there is no blob worker on that path.
- A blob remains for images: `maplibre-gl.mjs` line 5 makes a Blob and `URL.createObjectURL` for an `img.src` fallback (PNG decode). If that path is taken, `img-src` needs `blob:`.
- Eval: `maplibre-gl-worker.mjs` line 9 has `globalThis.eval(n)` on a non-module branch. **Not traced to a caller**; if reached in a worker, the policy's no-`unsafe-eval` would block it.
- Tiles and glyphs are same-origin in the design (ADR-152 decision 5), so `connect-src 'self'` should cover them; the pages forwarder is not built.
- Superset: no GOV.UK page frames it (decision 10, near 41116; decision 8 allows no exception). The React Glass has no CSP, so no `frame-src` or COEP change is needed for it. Superset's own policy is `C deploy/superset/superset_config.py:255-265` (SE6), `frame-ancestors` at 264; it is not the host's concern.

**What only a run can establish (none run; each needs a seat)**

1. MapLibre 6.19 under `headers.ts`'s policy in Chromium and WebKit: every `securitypolicyviolation`, and whether `img-src blob:` or the eval branch is needed. Red first: a planted removal of `worker-src 'self'`.
2. Tiles, sprites, glyphs and PMTiles through `connect-src 'self'`, via the pages forwarder (PL10).
3. `wss:` the delta stream through pages (the X2 test).
4. Single sign-on with no prompt and sign-out for pages (PL9a, PL9b), and a new client's token on `/v1/me` (X1).

(The old Superset COEP question is moot: the React nginx sets no COEP.)

**Can GG5 be briefed now? Yes, on this reading, with the run as the brief's first step** (as R4's budget proof is). The policy is fixed by decision 8 and the MapLibre line already matches decision 9. The brief must say: the worker via `setWorkerUrl` as `maplibreWorker.ts` does; no `blob:` unless the run shows it is needed; a planted violation shown red. **Caveat:** if GG5 draws graph layers through Sigma it waits on the Sigma 4 proof (decision 9): `C apps/workspace/package.json:41` still has `sigma ^3.0.0`. Rotation and pitch are not in the policy and were not checked (they are GG5's own decision).

## D. Stale lines a builder would be misled by

- MapLibre is 6.x, not 4.7.1 (`C apps/workspace/package.json:36`; installed 6.19.0).
- `C apps/workspace/src/map/MapView.tsx:31,36` still import `maplibre-gl`, but the worker is set in `maplibreWorker.ts:10-18`.
- The design CSS moved to `C packages/design`; the old paths in the 18 November answers to Q7 and Q13 are stale.
- Superset's policy was rewritten (SE6): `C deploy/superset/superset_config.py:237-265`; the old lines 237-252 and the old `frame-ancestors` wording are stale.
- The brand branch is now `C harness/site.py:103` (was 93); the Conduit socket route `C services/api/app.py:21579` (was 21494); Valkey `noeviction` `C harness/render.py:875` (was 855-864).
- Pages has its own CSP, sessions and sign-in (`C apps/pages/server/headers.ts`, `expressStore.ts`, `oidc.ts`); "ADR-050 does not cover a server-side client" is now ADR-050 Amendment 4 (near 41324).
- ADR-152 decision 1 says every deployment runs the Node service; Amendment 3 says off by default. Read both.

## What the scout could not read

No run and no git history (it had no shell); the Keycloak branch of `principal_auth` past line 1004; `spec/08` and `spec/02` for new scenarios and the self-contradiction; `express-session`, `openid-client` and `esbuild` in `node_modules`; the Studio's line counts; MapLibre's minified `Ol` and `jl` functions beyond the minified line.
