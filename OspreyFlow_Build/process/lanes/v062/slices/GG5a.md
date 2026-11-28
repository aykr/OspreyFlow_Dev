# Slice GG5a · GG5 · The strict-policy run: MapLibre 6.19 under the page service's own content security policy, in a real browser, red first; the standing browser test that no map request leaves the deployment (the first slice of GG5, the map and site plans)

- **Build id:** GG5 (plan: "Map and site plans on MapLibre 6 (R8); whether site plans rotate and pitch is decided here"; after GG2 and BL3). **The owner's word of 21 November 2026 (file 009, answer 10): brief GG5 now, the strict-policy run on MapLibre 6.19 first; record in the brief that the 18 November claim of a CSP build is void; rotation and pitch stay GG5's own.** BL3 is answered (`OspreyFlow_Build/process/lanes/v062/BL3_FRONT_END_ANSWERS_2026-11-21.md`, section C: read it whole first). GG5's later slice (the map and site plans themselves, GG5b) waits for GG2 and is briefed when GG2a has measured Sigma 4; **this slice does not.**
- **Dial setting:** balanced
- **Rounds limit:** the dial's (8)
- **After:** nothing is needed on main for the policy run (the page service, its policy and its headers are merged); **it is a browser run, so it is a seat (Playwright slot) and starts only when the PL4 chain's seat is not waiting and no merge is in its gate.**
- **Status of this brief:** written by the conductor on 21 November 2026 from a read-only scout (BL3 section C). **Every file and line below is the scout's: re-read each, lines move.**

## What is already established by reading (re-check, do not trust)

- The React Glass sends **no CSP** today (`OspreyFlow_Core/apps/workspace/nginx.conf.template` has only Cache-Control headers).
- The page service's policy is built in `OspreyFlow_Core/apps/pages/server/headers.ts` (about lines 33 to 47): `default-src 'self'`; scripts and styles by nonce; `img-src 'self' data:`; `worker-src 'self'`; `connect-src 'self'`; `frame-src 'none'`; **no `unsafe-inline`, no `unsafe-eval`, no `blob:` anywhere**. It matches ADR-152 decision 8; **decision 8 allows no exception: if the run shows the map needs `blob:` or `unsafe-eval`, you stop and bring it to the owner, you do not widen the policy.**
- MapLibre: the workspace pins `^6.4.1` (`OspreyFlow_Core/apps/workspace/package.json` about line 36; decision 9: `>=6.4.1 <7`); installed 6.19.0. **The 18 November claim that the installed package ships a CSP build is void: the installed `dist` has only `maplibre-gl.mjs`, `maplibre-gl-worker.mjs`, `maplibre-gl-shared.mjs` and the CSS.** The worker is set from the page's own origin by `OspreyFlow_Core/apps/workspace/src/map/maplibreWorker.ts` (about lines 10 to 18: `?url` import and `setWorkerUrl`), so a same-origin worker takes the direct `new Worker(url, {type:'module'})` path (read from the minified bundle: confirm).
- **Two places that may still need a relaxed policy (the scout read them and did not trace them): (1)** `maplibre-gl.mjs` about line 5 makes a Blob and `URL.createObjectURL` for an `img.src` fallback (PNG decode): if that path is taken, `img-src` would need `blob:`; **(2)** `maplibre-gl-worker.mjs` about line 9 has `globalThis.eval(n)` on a non-module branch, not traced to a caller: if reached in a worker, the policy's no-`unsafe-eval` blocks it.
- Tiles, glyphs and sprites are same-origin by design (ADR-152 decision 5), so `connect-src 'self'` should cover them; the page service's forwarder for them is **not built** (PL10 forwards `/v1`); this run serves its tiles from the test's own origin.
- The pages gates (keyboard, accessibility, performance, CSP) are **not built** (`OspreyFlow_Core/apps/pages/test` holds `server/`, `support/` and `fixtures/` only); this slice builds the CSP one for the map and no other.

## What (in this order; the failing test first, red, then green)

1. **The page and the spec.** A test-only page (under `apps/pages/test/`, never a product route) that mounts MapLibre 6.19 **served by the page service's own header builder** (call the real function that makes the policy; do not copy its text), with the worker set by `setWorkerUrl` as `maplibreWorker.ts` does, a synthetic style and a synthetic same-origin tile set (no network outside the test's own origin; reuse GG6's `map-tiles.pmtiles` fixture and its test harness if they fit: read `OspreyFlow_Core/apps/workspace/keyboard/map-tiles-harness.tsx` and `map-build/playwright.config.ts`, and say what you reused). A Playwright spec for **Chromium and WebKit** that loads it and records (a) every `securitypolicyviolation` event, (b) every request whose origin is not the test's own, (c) the map reaching `load` and `idle` with at least one tile drawn. **Asserts none of (a) and (b) and (c) true.**
2. **Red first (rule 15, the planted fault takes the shape the page really sends):** plant (i) the policy with `worker-src 'self'` removed (the worker is blocked: the spec fails with a named violation), (ii) a style that asks for a tile from another origin (the spec fails naming the request), (iii) if the PNG fallback or the eval branch can be reached from a style or tile the product could really serve, plant that and show it. **Say which directives the run showed the map needs, directive by directive, in your report, with the violation text for each that failed.**
3. **If the run needs `img-src blob:` or `unsafe-eval`: stop.** Write what needs it (the exact call, with the file and line in the package), and **that is the report**: the owner decides whether the policy gets an exception or the map is configured not to take that path (for example a tile format that avoids the PNG fallback). Do not change `headers.ts` for it.
4. **The standing test.** Wire the spec so the gate runs it (the pages' own test command; if `apps/pages` has no browser runner yet, add the smallest one and say so); the first green is not a result (rule 15): the planted faults above are in the test file as their own cases, red against the policy and green against the page.
5. **Report:** the directive table; the browsers run; the time of the run; what only a deployed run would show (tiles through the page service's forwarder; the wss stream; single sign-on): owed to a later slice. **Rotation and pitch are not in this slice; they are GG5b's own decision.** If GG5b would draw graph layers through Sigma, it waits for the Sigma 4 proof (decision 9; the workspace still pins `sigma ^3.0.0`); say so again in the report.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/csp/map.spec.ts` (the name is the conductor's proposal; say if you chose another), run by Playwright in Chromium and WebKit; red first on main (no such test), the plants red. **Say which folders it reads and which browsers it ran.**

## Checks

The new spec; the pages' own server tests (`apps/pages/test/server`); `tsc` for `apps/pages`; `ruff check .` in `OspreyFlow_Core` if any Python is touched (none expected); `tests/test_doc_citations_check.py`. The conductor writes the row and its browser commands (with a Playwright slot) when the seat is startable; **the builder never takes the stack lease.**

## Out of scope

The map and site plans themselves (GG5b), Sigma, `headers.ts` changes (unless the owner rules after item 3), the tile forwarder, any change under `apps/workspace`, any real tile or style from the internet.

**Added 26 November 2026 (the conductor):** the extension in `slices/drafts_2026-11-25/GG5a.md` is ruled as drafted, every proposal (a), with the 26th's corrections; it is built away and comes in below.

## Round 1 (D247; the conductor, 26 November 2026): merge `away/GG5a` first

**Your first step: merge the local branch `away/GG5a` into your branch.** Its report,
`process/lanes/v062/away/GG5a_AWAY_REPORT.md` on that branch, is the record: read it whole. **Every figure in it was taken
on the server under its namespace (56 of 56, and two stability runs of 50 of 50), not on the Mac or CI.** Then run your
frozen checks here and say what differs.

The owner's answers to its questions:
- **Q1 (a), approved on the owner's standing word (D274, technical):** keep the exact `pmtiles` 4.5.0 pin (the
  workspace's own resolved version, BSD-3-Clause) beside `maplibre-gl`, so the page reads the archive by the real
  `pmtiles://` protocol. `make licence-check` must pass with it.
- **Q2:** the CI patch (`apps/pages/test/csp/ci-wiring.patch`) and `GG5a_ADR152_DECISION8_RUN.diff` **stay diffs for the
  owner** (the morning of 27 November). Apply neither. The slice may merge without them.
- **Q3 (a):** leave the policy as it is (`headers.ts` is the owner's; no change); say so in the report.
- **Q4:** Firefox is not run (no build on this machine). Nothing to do.

## Checks

`npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`; `node scripts/no_react_check.mjs`;
`node scripts/version_isolation_check.mjs`; `make -C ../OspreyFlow_Build licence-check` (with the acceptance environment's Python: a merge tree has no `.venv`).

## Out of scope

`headers.ts`, the Makefile, the CI workflow, any decision record (diffs for the owner only), GG5b's map page.
