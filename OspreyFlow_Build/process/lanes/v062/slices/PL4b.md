# Slice PL4b · PL4 · The design tokens move to `packages/design` (nothing else moves, no behaviour changes)

- **Build id:** PL4 (ADR-152 R2); the second of five slices A to E (RULINGS.md, "PL4 goes ahead of AD1"). **B** is this: the one file
  `OspreyFlow_Core/apps/workspace/src/design/tokens.css` becomes `OspreyFlow_Core/packages/design/tokens.css`, and everything that names it follows.
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4a merged (it is on main with the shared package, `scripts/dist_compare.mjs` and the baseline record). **It may start building the moment PL4a
  merges; it may not merge until GitHub's run on PL4a's merge commit is green for the budget, accessibility and keyboard jobs** (the owner, 20 November, condition (b) as changed).
- **Status of this brief:** written by the conductor on 20 November 2026 from a read-only scout of the same day. **Five points below are marked "owner to confirm":
  **the owner confirmed all five on 20 November (with the two additions in "The words" and "Where the rest of the design folder goes"); the builder starts when PL4a merges.** The scout's counts are its own and are not re-checked; the builder re-reads.
  **While PL4 runs nothing else touches `apps/workspace`.** Every brief of the PL4 slices carries the cheap checks at the end (ruff, eslint, the line-length rule, the scan-map check).

## What

The scout found: `tokens.css` is one `:root` ramp with a header comment and no `@import` and no `@font-face`; beside it are `primitives.css`, `panelType.css`, `scale.css`,
`tokens.css.d.ts` (a `declare module "*.css"` shim) and `fonts.ts`; `packages/design` does not exist; `spec/02_GLASS_FRONTEND.md` (about lines 2063 to 2064) already says the file moves
to `packages/design/tokens.css` under ADR-152; Vite has no alias, so every importer is a relative path. Move that one file and repoint what names it:

1. **The file.** `git mv` `apps/workspace/src/design/tokens.css` to `packages/design/tokens.css`; its contents unchanged (byte for byte). **Owner to confirm (1): `packages/design` is a plain folder
   holding the file, with no `package.json` and no entry in the root `workspaces`; importers use relative paths** (recommended: the smallest change, the built CSS the same; a package with a manifest buys
   nothing while the file is only ever imported by path). `primitives.css`, `panelType.css`, `scale.css` and `fonts.ts` stay where they are.
2. **The importers** (about 80 import sites, counted by the scout as 77 TS/TSX files in `apps/workspace`: `src/main.tsx` and 76 harness and showcase files under `a11y/`, `deck-capture/`, `export-capture/`,
   `keyboard/`, `map-verify/`, `perf/`; and 3 in `apps/harness`: `src/main.tsx`, `keyboard/install-harness.tsx`, `keyboard/setup-harness.tsx`). Repoint each to the new path. The brief's earlier figure of "about 111" was the
   plan's count, which the scout could not reproduce (80 import sites plus a dozen readers): the acceptance below does not depend on any number, it asks that **no tracked file names the old path**.
3. **The readers by name** (not imports): ten Vitest files under `apps/workspace/src` that read the file with `readFileSync` or a URL (`GovukHeader.test.tsx`, `canvasGrid.test.ts`, `designContract.test.ts`, `fonts.test.ts`,
   `headingFace.test.ts`, `undefinedTokens.test.ts`, `color/tokens.test.ts`, `home/homeKey.test.ts`, `map/attributionChip.test.ts`, `theme/themeCookieSnippet.test.ts`); the Python tests
   `tests/harness/test_keycloak_theme.py`, `test_keycloak_theme_govuk.py`, `tests/test_superset_theme.py`, `tests/harness/test_service_inventory.py` (`test_the_glass_dockerfile_can_reach_tokens_css`) and
   `tests/test_dockerignore.py`; `tools/colour_drift_check.py` (it exempts `design/tokens.css` by a relative name under a walk of `apps/workspace/src`: after the move that exemption names a file no longer under the walk; make the
   exemption true for the new place, and show it still flags a colour outside the tokens, red then green, rule 15). Five more tests write a fake tree at the old path (`test_refresh.py`,
   `test_refresh_before_the_gateway.py`, `test_refresh_search_rebuild.py`, `tests/harness/test_install_page_build.py`, `tests/harness/test_store_volumes.py` around line 968): they keep passing without covering the real file;
   **repoint their fake trees to the new place too**, so they model the real layout.
4. **The images.** `harness/Dockerfile` copies `apps/workspace/src/design` by name (about lines 98 to 103) and `apps/harness/scripts/stamp.mjs` lists `apps/workspace/src/design` as a directory (about line 17): both follow the file.
   **Owner to confirm (2): `apps/workspace/Dockerfile` and `harness/Dockerfile` each get a `COPY packages/design` line** (the file must be inside the build context the images already use; today it reaches the workspace
   image through `COPY apps/workspace`; the comment at about lines 29 to 34 of that Dockerfile names the old path and is updated). `apps/pages/Dockerfile` does not reference the tokens and is not touched.
   **Two existing guards are blind to the new folder and must be extended, red first (rule 12), not left passing by accident.** (a) `OspreyFlow_Build/tests/harness/test_harness_frontend_copies.py` follows the harness
   frontend's imports only into `apps/workspace` (`target.is_relative_to(WORKSPACE)`) and reads only `COPY apps/workspace/...` lines of the `frontend-builder` stage: after the move the harness imports
   `packages/design/tokens.css` (through `../../../../packages/design/...`), which the test neither follows nor requires a COPY for. Extend it to follow imports into `packages/design` too and to require a
   `COPY packages/design/...` line in that stage; show it red with the line removed. (b) **The install-page stamp** (`apps/harness/scripts/stamp.mjs`, about line 17, and `harness/install_page_build.py`, about line 34:
   both list `apps/workspace/src/design` as install-page source; the hash includes relative paths, so a move changes the stamp even with identical bytes): add `packages/design` to **both** lists together
   (`tests/harness/test_install_page_build.py` fails if only one changes). The owner accepts the re-stamp **on condition that it is shown to be only the paths**: a case (or a recorded run in your report) that lists the stamped files'
   contents by byte hash before and after the move and shows the two lists identical, with only the relative paths differing.
5. **The shim.** `tokens.css.d.ts` (`declare module "*.css"`) **owner to confirm (3): stays in `apps/workspace/src/design/`** (it is the workspace's TypeScript's business, not the file's); if the type check needs the new folder in the
   workspace `tsconfig`, add only that include.
6. **The JS mirrors of the colours** (`apps/workspace/src/color/tokens.ts`, `color/palette.ts`, `map/style.ts`, `export/reportExport.ts`, `reports/packExport.ts`) restate values and do not import the file.
   **Owner to confirm (4): they stay in `apps/workspace`** (they belong to slices C and D, the pure leaves and plain logic).
7. **The words** (the owner's addition of 20 November: **no code, configuration, test, build or guide file names the old path**). Every guide and specification text that is not a record of the past
   (the guides under `OspreyFlow_Core/docs` and `OspreyFlow_Build/spec`, other than the decision log and the build-plan records) is changed to the new path, and its document-control row follows the guides' rule if the guide has one.
   **Past entries in the decision log are history and are not rewritten.** The citation check (`tools.doc_citations_check`) would flag them once the old path is gone, so give the old path one entry in
   `OspreyFlow_Build/tests/fixtures/citation_allowlist.txt`, under a comment that says why in the file's own style ("Moved by PL4 slice B to `packages/design/tokens.css`: the decision-log entries and other records that
   name the old place are history and stay as written"); remove the `packages/design/tokens.css` line (about line 59), which the allowlist held while the file was absent. The acceptance test's allowance for the old path is **the
   decision log and the records folders only**, the same places the allowlist is for. `OspreyFlow_Build/process/CLAUDE.md` (about line 24, the table row: "until ADR-152's move lands: `apps/workspace/src/design/tokens.css`")
   is a rules file the owner changes: **do not edit it**; say in your report what the row should read, and the conductor gives the owner the one-line diff. Same for any other rules file you find naming the old path.
8. **Protected files.** The scout found no line in the Core Makefile or `ci.yml` that names the tokens path, so nothing is needed there. If you find one, write nothing and give the exact diff in your report
   (it must pass `git apply --check`).

**The proof that nothing changed** (the owner's condition a): `node scripts/dist_compare.mjs verify --build` says SAME against the record slice A committed, and `node scripts/dist_compare.mjs compare
$HOME/dev/osprey-acceptance/PL4a-baseline/dist apps/workspace/dist` (the raw copy A saved, which stays the "before" of every later slice) says SAME. The scout reads the script as tolerating a changed path, a changed hash and
a changed chunk name, and as failing on a changed rule order or a changed import order in `main.tsx`: **do not reorder anything**. If the built CSS differs for a reason you cannot remove (say, a path inlined into a
comment or a source map), say so in your report with the diff the script prints and stop for the conductor; do not edit the script to make it pass. **Owner to confirm (5): the acceptance does not carry the figure 111**
(the new test asks for no tracked reference to the old path, whatever their count).

Binding: process/CLAUDE.md rules 11, 12, 13 and 15; ADR-152 decisions 1, 2 and 6 and invariants I1, I11, I13; `spec/02_GLASS_FRONTEND.md` on the tokens (authoritative: no colour outside the tokens); the owner's secret rules
(no fixed key-shaped string in any file; tests generate their own); the 18 November ruling on the client's name; British English. You do not edit `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`,
`OspreyFlow_Core/.github/workflows/release.yml` or any `CLAUDE.md`.

## Acceptance test

One new pure file, red first on main against the real tree: `OspreyFlow_Build/tests/glass_trees/test_design_tokens_location.py`. It asserts: (1) `OspreyFlow_Core/packages/design/tokens.css` exists and the old
file does not; (2) **no code, configuration, test, build or guide file names the old path** (`apps/workspace/src/design/tokens.css`, or the relative forms of it: `design/tokens.css` under `apps/workspace/src`, the three
`apps/harness` climbs), as a path to open, import, copy or cite; the only places that may are the decision log (`spec/06_DECISIONS.md`) and the records folders (`process/lanes/*/`, the build plan's records), which are history and are not
rewritten, and `process/CLAUDE.md` until the owner applies his one-line diff (the test names that one exception, with its reason, and the exception goes when the diff is applied); (3) every import of a `tokens.css` in the TS/TSX files of `apps/workspace` and `apps/harness`
resolves to the one file; (4) the two Dockerfiles copy `packages/design`. (5) the stamped install-page files hold the same bytes before and after the move (item 4 b); (6) **the colour-drift check's file count does not fall** (`tools/colour_drift_check.py` says how many files it scanned; if it prints no count, make it print one, a one-line change with its own test: the
count after the move is not below the count before; `tokens.css` is exempt by name, so for this slice the count is unchanged, and the case is the guard B2 relies on). It must be shown red on main (the file is where it was) and on a planted regression (the old path put back in one importer, one reader and one Dockerfile
line, each its own case, at the real call-site shape: rule 15). It walks the repository (`git ls-files`): **say in your report which folders it walks**, because the conductor writes its scan-map row from that.

## Checks

The **checks command** runs, pure only: the Python readers named above (`test_keycloak_theme.py`, `test_keycloak_theme_govuk.py`, `test_superset_theme.py`, `test_service_inventory.py`, `test_dockerignore.py`,
`test_harness_frontend_copies.py`, `test_dockerfiles_numeric_user.py`, `test_install_page_build.py`, `test_doc_citations_check.py`); `ruff check .` in `OspreyFlow_Core` (the line-length rule is 100 and
nothing in `OspreyFlow_Build` is linted by ruff); `npm run lint` and `npm run typecheck`; `npm test --workspace apps/workspace`, `apps/harness` and `packages/glass-shared`; the workspace build and
`node scripts/dist_compare.mjs verify --build`. **Before your final report run, by hand, the cheap checks the conductor will run again before the merge:** ruff and eslint on every file you changed, and the scan-map check for
the test you add (`python OspreyFlow_Build/scripts/slice_line/scan_select.py` shows the mapped tests; a new test that walks the repository needs a row, which the conductor commits; say what to write). A merge attempt costs 25 minutes:
a lint error or a missing row found there is your round, not the conductor's.
The browser gates (budget, accessibility, keyboard) are **not** run here: the owner proves them on GitHub on the merge commit.

## Out of scope

Every other file's move (C, D, E); the invite form; the JS colour mirrors; `primitives.css`, `panelType.css`, `scale.css` and `fonts.ts` (see "Where the rest of the design folder goes", below); a package manifest for
`packages/design`; the rules files; the protected files; the budget numbers (slice E, on the owner's Mac, nothing else running).

## Where the rest of the design folder goes (the owner's ruling, 20 November; not this slice)

**Slice B2, straight after B** (same mechanism, same proof: the built CSS identical to the baseline): `scale.css`, `panelType.css` **and `primitives.css`** move to `packages/design` (ADR-152 decision 6 names
"tokens.css, primitives.css, fonts; read by the React workspace and tree-default alike"; `primitives.css` is plain class-based CSS with no React, the `pages` use the same classes so the Default tree looks as it does today,
and the `.tsx` primitives in `apps/workspace/src/design/primitives/` stay in the workspace). **Slice B3, after B2:** the fonts (see `RULINGS.md`: one list in `packages/design` of the families and weights used; `fonts.ts` stays
in the workspace because it is tied to the Vite bundle; both front ends load from the list, each its own way; a test fails if either loads a font the list does not name). B2 and B3 stay inside PL4 (no new build id);
their briefs are written after a scout of the same day. Do not touch any of them in this slice.
