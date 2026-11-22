# Slice PL4d3a · PL4 · The report, export, alert and pattern Conduit clients move to `packages/glass-shared` (slice D3a; no behaviour changes)

- **Build id:** PL4 (ADR-152 R2, decision 6: "the Conduit client"). **D3 is cut three ways on the scout's finding** (the rest of the clients are about 3,600 lines and 105 importer references, 2.5 times D2): **D3a (this slice): the clients the reports and rules pages call**; D3b: the link, inspector, views, boards and the other clients; D3c: the files that need a split first (`investigation/cases.ts`, `home/guides.ts`, `home/homeData.ts`, `canvas/entityPictures.ts`, `ingest/runs/ExternalOrchestration.tsx`) and the stray `export/api.ts.bak`. Nothing the ADR names is dropped; it is sequenced.
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4d2 merged (it is: `74a983e`). **Method: read `OspreyFlow_Build/process/lanes/v062/slices/PL4d2.md`, `PL4d1.md` and `PL4c.md` first; this slice does the same for other files, with the same proofs and the same traps (and the traps the D2 rounds found, below).** It merges without waiting for GitHub if `node scripts/dist_compare.mjs verify --build` says SAME (the owner's condition (b)).
- **Status of this brief:** written by the conductor on 21 November 2026 (night) from a read-only scout (read, not measured). **While PL4 runs nothing else touches `apps/workspace`.**

## What moves (re-read every file before moving it, and say what you find)

Under `OspreyFlow_Core/apps/workspace/src/` unless stated; destination `OspreyFlow_Core/packages/glass-shared/src/`, keeping the folder shape. Plain TypeScript: each calls `fetch` against the Conduit (or is a helper of one), takes the bearer token as an argument, and imports no react, react-dom, sigma, maplibre-gl, zustand/react, and uses no `window`/`document`/`localStorage`.

| File | Lines | fetch | Note (workspace-relative imports to resolve first) |
|---|---|---|---|
| `reports/api.ts` | 56 | 3 | 13 importers. |
| `reports/caseHttp.ts` | 34 | 1 | imports `./api`. |
| `reports/dashboards.ts` | 26 | 2 | |
| `reports/trendsApi.ts` | 50 | 0 | imports `./api`, `./caseHttp`. |
| `reports/packsApi.ts` | 120 | 1 | type import `../export/api`; imports `./packText`. |
| `reports/packText.ts` | 134 | 0 | imports `../alerts/closingReasons`, `../alerts/names` (both move with this slice). |
| `export/api.ts` | 135 | 2 | **imports `WITHHELD_SENTENCE` from `../statusbar/StatusBar` (a React file; the constant is defined at about line 23).** **The one edit to a React file this slice may make:** move the constant to a plain module in the package (for instance `export/withheldSentence.ts`), byte for byte, and have `StatusBar.tsx` import it from the package; no other change to the React file. Say so in your report, and show a test that the sentence is unchanged (the exact text, compared with the base commit's). |
| `alerts/api.ts` | 306 | 3 | 14 importers (11 under `alerts/`, `ownership/api`, `OwnershipPlace`, `GlassWatchActions`). |
| `alerts/names.ts`, `alerts/closingReasons.ts` | 57, 17 | 0 | 14 and 4 importers; plain helpers that `packText` uses. Move them if they are plain (read them). |
| `patterns/api.ts` | 171 | 6 | imports `../models/modelDeadline`. |
| `models/modelDeadline.ts` | 18 | 0 | plain; used by `patterns/api.ts`, the inspector and reader clients (D3b), so it moves here and D3b imports it from the package. |

Total about 12 files, 1,124 lines, 18 fetch calls, about 75 importer references (the top of the four-round range). **If you find that a file cannot move whole (React, the DOM, a workspace import you cannot resolve), stop at that file, leave it, and say so; the package never imports from the workspace.** Anything else under these folders (components, hooks, React) stays.

## What (in this order)

1. **No new dependency.** If you find one, stop at that file and say so.
2. **Move the files** (`git mv`; contents byte for byte except import lines and the one `StatusBar` constant move), export them from `packages/glass-shared/src/index.ts`, and **repoint every importer**: workspace sources, tests (they stay in `apps/workspace`), the keyboard harnesses under `apps/workspace/keyboard` (grep: some import these by relative path), `apps/workspace/live` and `apps/harness` if any import one.
3. **The traps the D2 rounds found, closed in this slice before the verifier looks:** (a) **every vitest and Python test that walks `apps/workspace/src` for words** (`copyWords.test.ts`, `copyNoClient.test.ts`, `resolvedPrincipal.test.ts`, `copyTextsTestKit.ts`, `tests/test_people_section_words.py`, `tests/test_guide_navigation_words.py`, `tests/test_guide_role_words.py`, and any other walker: grep for `apps/workspace/src` and `rglob` across `OspreyFlow_Build/tests` and `apps/workspace/src`) **reads `packages/glass-shared/src` too**, keyed by root so a path present in both roots is not overwritten (D2's last finding: `inviter.ts` and the layout files exist in both); show each reads the moved files and goes red on a plant in one; (b) the four design gates and `undefinedTokens.test.ts` already read the package: confirm by a plant; (c) `OspreyFlow_Build/tests/harness/test_harness_frontend_copies.py` still reaches every file the harness needs, red on a plant that removes a COPY line; (d) the old-path test finds no old path anywhere outside the decision log and records.
4. **The words:** any guide or specification text outside the decision log and records that names an old path follows it (allowlist entries with a reason where one must stay, as C and D did; the allowlist's stale lines naming files moved by C and D1 are checked and removed if the file now exists at the new path only).
5. **Protected files:** the Core Makefile and `ci.yml` need nothing; if a line needs a change, write nothing and give the exact diff (it must pass `git apply --check`).

**The proof that nothing changed (the owner's addition 1):** (a) `node scripts/dist_compare.mjs verify --build` SAME, and `compare $HOME/dev/osprey-acceptance/PL4a-baseline/dist apps/workspace/dist` SAME; the workspace's test counts equal the baseline's. (b) **The Playwright collection check:** `npx playwright test --list` for each project under `apps/workspace` and `apps/harness`, before and after: equal counts, exit 0. (c) the four gates' reach not lower (both numbers) and each word-walker's reach not lower. (d) the image COPY lines. If the built output differs, say what differs, with the script's output, and stop for the conductor.

Binding: process/CLAUDE.md rules 11, 12, 13 and 15; ADR-152 decisions 1, 2 and 6 and invariants I1, I11, I13; the owner's secret rules (no key, token or address in any test output); the 18 November ruling on the client's name; British English. You do not edit `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`, `OspreyFlow_Core/.github/workflows/release.yml` or any `CLAUDE.md`.

## Acceptance test

One new pure file, red first on main: `OspreyFlow_Build/tests/glass_trees/test_glass_shared_report_clients.py`, built like D2's `test_glass_shared_clients.py` (read it): (1) the moved files exist under the package, are exported from the index, and not under their old paths; (2) no code, configuration, test, build or guide file outside the decision log and records names an old path; (3) every import in a spec or harness file resolves; (4) the move changed no line but the imports (**compare both sides at the rename commit, never the working tree**) and the `WITHHELD_SENTENCE` constant is byte for byte the base's; (5) the package's copies import no React and no workspace path; (6) each word-walker reads the moved files (planted fault in a moved client, red then green, keyed by root). **Say in your report which folders it walks** (the scan-map row is written from that).

## Which stage 4 builds this unblocks (say it in your report, confirmed by the code)

The owner's reading: the reports and rules pages (**GR2 to GR4, RM1**) need D3. The scout's reading: the reports screens call `reports/api`, `packsApi`, `caseHttp`, `trendsApi`, `dashboards` and `export/api` (all in this slice) and `analytics/api` (D3b); the rules page calls `alerts/api`, `patterns/api`, `alerts/names`, `closingReasons` and `modelDeadline` (all in this slice). **Confirm or correct from the React screens these pages replace, and name any client a page calls that is in neither D1, D2 nor this slice.**

## Checks

As D2's: `ruff check .`; `npm run lint`, `npm run typecheck`; `node scripts/no_react_check.mjs`, `node scripts/version_isolation_check.mjs`; `npm test` for `apps/workspace`, `apps/harness`, `packages/glass-shared`; `node scripts/dist_compare.mjs verify --build`; the Python readers (including every word walker, `test_harness_frontend_copies.py`, the four gates' tests, the three glass_trees move tests, `test_layout.py`). The browser gates are not run here. **Before your final report run by hand what the conductor runs again:** ruff and eslint on every file you changed, the line-length check, the scan-map check for the test you add.

## Out of scope

D3b and D3c (everything else); the two sign-in files; `admin/api.ts` (left in the workspace by D2 with `help/roles.ts`); components, hooks and React except the one constant; `color/nodeVisual.ts`, the canvas files and structural types (E); `apps/pages/Dockerfile` (PL7); the rules files; the protected files; the budget numbers.
