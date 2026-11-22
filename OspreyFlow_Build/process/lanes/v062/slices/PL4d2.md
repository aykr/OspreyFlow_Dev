# Slice PL4d2 · PL4 · The ingest, sources, releases and admin Conduit clients move to `packages/glass-shared` (slice D2; no behaviour changes)

- **Build id:** PL4 (ADR-152 R2, decision 6: "the Conduit client"). The fifth of the PL4 slices (A wiring, B design tokens, B2 the CSS, B3 the font list, C pure leaves and stores, D1 theme, brand, palette, plain layout and inviter, **D2 the ingest, sources, releases and admin clients**, D3 every other client, E canvas and graph logic and structural types).
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4d1 merged (it is: `df4fd84`). **Method: read `OspreyFlow_Build/process/lanes/v062/slices/PL4c.md` and `PL4d1.md` first; this slice does the same thing for other files, with the same proofs and the same traps.** It merges without waiting for GitHub if `node scripts/dist_compare.mjs verify --build` says SAME (the owner's condition (b)).
- **Status of this brief:** written by the conductor on 20 November 2026 (night) from a read-only scout of the same day (read, not measured) and the owner's rulings (D1, D2, D3 in that order; the two sign-in files stay in the workspace; the proofs of addition 1). **While PL4 runs nothing else touches `apps/workspace`.**

## What moves (the scout's reading; re-read every file before moving it, and say what you find)

Plain TypeScript only: each module calls `fetch` against the Conduit and takes the bearer token as an argument; none imports react, react-dom, sigma, maplibre-gl, zustand or graphology (the package's lint block, `scripts/no_react_check.mjs` and `scripts/version_isolation_check.mjs` hold it). Under `OspreyFlow_Core/apps/workspace/src/` unless stated; destination `OspreyFlow_Core/packages/glass-shared/src/`. Keep the folder shape (`ingest/`, `admin/` and so on) so the diff is a rename.

| File | Lines | Note |
|---|---|---|
| `ingest/api.ts` | about 757 | 32 `fetch` calls. **At least 26 files under `ingest/` import it** (`../api` and `ingest/api`): repoint all, count them in your report. |
| `ingest/sources/api.ts` | | The sources client. |
| `ingest/releases/releasesApi.ts` | | The releases client. |
| `admin/api.ts` | about 281 | Imports `../help/roles` (line 4): **`help/roles.ts` moves with it if it is plain** (no React, no DOM), otherwise it stays and the package may not import the workspace: **then stop at this file, leave it, and say so** (the package never imports from the workspace). |
| `admin/sections/MapsApi.ts`, `admin/sections/ModelsApi.ts`, `admin/updateNotice.ts` | | `updateNotice.ts` imports the generated schemas by a relative path (line 4). |

The generated schemas: `analytics/api.ts` (D3) and `updateNotice.ts` import `packages/schemas/generated` by relative path; **after the move the path depth changes: check the import still resolves and use the package's way of reaching the schemas (read how `store.ts` in `workingset/` did it in slice C)**. Nothing else is plain-and-adjacent unless you read it and say so; **anything else under `ingest/` or `admin/` (components, hooks, React) stays.** If a client file uses `window`, `document` or `localStorage`, say so (the package has the DOM lib, but a client that touches the page is not a Conduit client: stop at it).

## What (in this order)

1. **No new dependency** is expected. If you find one, stop at that file and say so.
2. **Move the files** (`git mv`; contents byte for byte except import lines), export them from `packages/glass-shared/src/index.ts`, and **repoint every importer**, including `ingest/` (26+), `admin/sections/*`, tests (tests stay where they are, in `apps/workspace`), the keyboard harnesses and specs under `apps/workspace/keyboard` and `apps/workspace/live`, and `apps/harness` if any file there imports one (grep). The Playwright specs import moved modules by relative path in places: find them all.
3. **The images and their copies:** the workspace and harness images already carry `COPY packages/glass-shared/src` (C). Check that nothing in either image's copy list names a moved path; **`OspreyFlow_Build/tests/harness/test_harness_frontend_copies.py` walks imports: show it still reaches every file the harness needs, and red on a plant that removes a COPY line.**
4. **The gates must not silently lose reach:** the four gates (`colour_drift_check.py`, `design_check.py`, `ui_words_check.py`, `no_branches_check.py`) and `undefinedTokens.test.ts` already read `packages/glass-shared/src` (C): confirm a planted fault in a moved file turns each red; state the number of files each reads before and after (not lower). Update the `no_branches_check.py` allowlist only if an entry names a moved path.
5. **The words:** any guide or specification text outside the decision log and the records folders that names an old path follows it; the decision log is not rewritten (an allowlist entry with the reason where an old path must stay).
6. **Protected files:** the Core Makefile and `ci.yml` need nothing; if you find a line that needs a change, write nothing and give the exact diff in your report (it must pass `git apply --check`).

**The proof that nothing changed (the owner's addition 1, the same as C and D1):** (a) `node scripts/dist_compare.mjs verify --build` says SAME, and `compare $HOME/dev/osprey-acceptance/PL4a-baseline/dist apps/workspace/dist` says SAME; the workspace's test counts equal the baseline's. (b) **The Playwright collection check:** list every spec before and after (`npx playwright test --list` with each project's own configuration under `apps/workspace` and `apps/harness`): the count of tests and files equal, exit 0; a spec that fails to import a moved file fails at collection. (c) the four gates' reach not lower (both numbers). (d) the image COPY lines carry what the imports need (the red plant). If the built output differs, say what differs, with the script's output, and stop for the conductor.

Binding: process/CLAUDE.md rules 11, 12, 13 and 15; ADR-152 decisions 1, 2 and 6 and invariants I1, I11, I13; the owner's secret rules (no key, token or address in any test output); the 18 November ruling on the client's name; British English. You do not edit `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`, `OspreyFlow_Core/.github/workflows/release.yml` or any `CLAUDE.md`.

## Acceptance test

One new pure file, red first on main: `OspreyFlow_Build/tests/glass_trees/test_glass_shared_clients.py`. It asserts: (1) the moved files exist under `packages/glass-shared/src`, are exported from the index, and are not under their old paths; (2) no code, configuration, test, build or guide file outside the decision log and the records names an old path of a moved file; (3) every import in a spec or harness file resolves; (4) **the move changed no line but the imports: compare both sides at the rename commit as `test_design_css_location.py::test_the_move_changed_no_stamped_byte_but_the_paths` does, never the working tree** (slice C's first version froze the files; fixed in its round 4); (5) the package's copies import no React and no workspace path. Planted faults at the real call-site shape, each red then green (an old path in a guide; a moved file importing a workspace path; a spec importing a path that no longer exists; a stale COPY line). **Say in your report which folders the test walks** (the scan-map row is written from that).

## Which stage 4 builds this unblocks (the owner's addition 2; say it in your report, confirmed by reading the code)

The owner's reading: the **Studio pages (IS2, IS3, IS5) and the Admin pages (AD3, AD4)** need D1 and D2 only (their pages call the ingest, sources, releases and admin clients through the shared package); the **reports and rules pages (GR2 to GR4, RM1)** need D3. **Confirm or correct this from the code:** for each of those builds, name the clients it calls (by module) and say whether each is in D2, D3 or E. A builder for each of those pages starts the moment D2 merges, so the file list you fix here is what their briefs are made final from.

## Checks

The **checks command**, pure only (as D1): `ruff check .` in `OspreyFlow_Core`; `npm run lint` and `npm run typecheck`; `node scripts/no_react_check.mjs` and `node scripts/version_isolation_check.mjs`; `npm test --workspace apps/workspace`, `apps/harness` and `packages/glass-shared`; `node scripts/dist_compare.mjs verify --build`; the Python readers. The browser gates are not run here. **Before your final report run by hand what the conductor will run again:** ruff and eslint on every file you changed, the line-length check, the scan-map check for the test you add, and `tests/test_layout.py` if you add any file at the repository root (a merge was refused for that once).

## Out of scope

D3 (every other client: analytics, alerts, boards, home, investigation and the rest; the stray `export/api.ts.bak`); the two sign-in files (`auth/oidcConfig.ts`, `auth/userManager.ts`); components, hooks and React; `color/nodeVisual.ts`, the canvas files and structural types (E); `apps/pages/Dockerfile` (PL7); the rules files; the protected files; the budget numbers.
