# Slice PL4b2 · PL4 · `primitives.css`, `scale.css` and `panelType.css` move to `packages/design` (slice B2; nothing else moves, no behaviour changes)

- **Build id:** PL4 (ADR-152 R2, decision 6: "tokens.css, primitives.css, fonts; read by the React workspace and tree-default alike"). The owner's ruling of 20 November 2026 (`RULINGS.md`, "The rest of the design folder"): B2 is
  `scale.css`, `panelType.css` **and `primitives.css`**, with the same proof as B. The `.tsx` primitives in `apps/workspace/src/design/primitives/` stay in the workspace. B3 (the fonts) follows.
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4b merged. It may start building the moment PL4b merges; it may not merge until GitHub's run on PL4b's merge commit is green for the budget, accessibility and keyboard jobs (condition (b) as changed).
- **Status of this brief:** written by the conductor on 20 November 2026 from a read-only scout of the same day; the owner confirmed its open points the same day. The scout's counts are its own and are not re-checked;
  the builder re-reads. **While PL4 runs nothing else touches `apps/workspace`.**

## What

`primitives.css` (974 lines) `@import`s `./scale.css` (line 7) and `./panelType.css` (line 9); nothing else imports those two. All three are plain CSS with no `url()` and no `@font-face`; the only relative references are those two
`@import` lines, which stay as they are because the three move together. Move the three files, byte for byte (`git mv`), from `OspreyFlow_Core/apps/workspace/src/design/` to `OspreyFlow_Core/packages/design/` (the folder B made),
and repoint what names them:

1. **The TSX importers of `primitives.css`: 80 files** (the scout's count): 68 under `apps/workspace/keyboard/`; `apps/workspace/src/main.tsx` (line 6; line 5 imports the tokens and must stay before it, and the order of the two
   imports does not change: the built CSS follows it); `apps/harness/src/main.tsx` (line 4); `apps/harness/keyboard/install-harness.tsx` and `setup-harness.tsx` (line 9, which reach it as `../../workspace/src/design/primitives.css`);
   `apps/workspace/a11y/showcase.tsx`; four `deck-capture/` harnesses; `export-capture/harness.tsx`; `map-verify/showcase.tsx`; `perf/harness.tsx`. Repoint each; change nothing else in them.
2. **Nine Vitest suites read the file by path** (ENOENT on a plain move): `src/design/accordionStyle.test.ts`, `brassUse.test.ts`, `canvasGrid.test.ts`, `canvasOverlays.test.ts`, `shellSizes.test.ts`, `topBarStyle.test.ts`,
   `radialMenuStyle.test.ts`, `src/design/primitives/Toast.test.tsx` and `src/shell/topBarWidths.test.ts`. `designContract.test.ts` reads only the tokens and is B's. Repoint their paths; do not weaken any assertion.
3. **The colour-drift check** (`OspreyFlow_Build/tools/colour_drift_check.py`, about lines 26 to 31 and 64) scans only `apps/workspace/src`: after the move it would silently stop scanning these three files (it scans `primitives.css`
   today). **The owner's ruling: extend its root to `packages/design`, shown red then green on a planted colour outside the tokens in a file there (rule 15, at the shape the check really sees), and the check's file count does not fall
   after the move** (it counts the scanned files; if it prints no count, make it print one, a one-line change with its own test; the count after the move is at least the count before, and your report gives both numbers).
4. **The images and the stamp.** B already copies `packages/design` in the two images and lists it in the two install-page lists; the three files are inside it, so nothing more is needed there. **Confirm that in your report, and show
   the install-page stamp's files hold the same bytes before and after (only the relative paths differ), the same case B added, run again on this move.**
5. **The guards.** `OspreyFlow_Build/tests/harness/test_harness_frontend_copies.py` (extended by B to follow imports into `packages/design`) must now reach `packages/design/primitives.css` and see its COPY. Read
   `OspreyFlow_Core/apps/workspace/scripts/sync_govuk_assets.mjs` (it writes the GOV.UK stylesheet into `apps/workspace/public/assets/govuk/` and touches none of these three files: nothing to change; say so).
6. **The words.** Comments naming the old paths (`OspreyFlow_Core/DESIGN.md` about lines 86, 89 and 480; `apps/workspace/src/views/views.css` about line 38; `apps/workspace/keyboard/scale-rules.spec.ts` lines 1 and 2) and any guide or
   specification text outside the decision log and the records folders follow the files. The acceptance of B (no code, configuration, test, build or guide file names the old path) extends to these three files' old paths. Past
   decision-log entries are history and are not rewritten; the citation allowlist gets one entry per old path with the reason, in the style B used.
7. **Protected files.** The scout found no line in the Core Makefile or `ci.yml` naming these files; if you find one, write nothing and give the exact diff in your report. Do not edit any `CLAUDE.md` or rules file.

**The proof that nothing changed:** `node scripts/dist_compare.mjs verify --build` says SAME against the record, and `compare $HOME/dev/osprey-acceptance/PL4a-baseline/dist apps/workspace/dist` says SAME. The comparison reads CSS
rule by rule in order: **do not reorder any import or any rule**. If the built CSS differs, say so in your report with the script's output and stop for the conductor; do not edit the script to make it pass.

Binding: process/CLAUDE.md rules 11, 12, 13 and 15; ADR-152 decisions 1, 2 and 6 and invariants I1, I11; `spec/02_GLASS_FRONTEND.md` section 4 (no colour outside the tokens); the owner's secret rules; the 18 November ruling on the
client's name; British English. You do not edit `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`, `OspreyFlow_Core/.github/workflows/release.yml` or any `CLAUDE.md`.

## Acceptance test

One new pure file, red first on main against the real tree: `OspreyFlow_Build/tests/glass_trees/test_design_css_location.py`. It asserts: (1) the three files exist under `OspreyFlow_Core/packages/design/` and not under
`apps/workspace/src/design/`; (2) no code, configuration, test, build or guide file names the old paths of the three (the same allowances as B: the decision log and the records folders); (3) every import of `primitives.css`
in the TS and TSX files of `apps/workspace` and `apps/harness` resolves to the one file, and `primitives.css` still `@import`s `./scale.css` and `./panelType.css` and both resolve; (4) the colour-drift check's file count after is
not below its count before, and a colour planted outside the tokens in a file of `packages/design` is flagged (red/green at the real call-site shape); (5) the stamped install-page files hold the same bytes before and after.
Each is shown red on main and on a planted regression (an old path put back in one importer, one reader; the `./scale.css` import removed). It walks the repository (`git ls-files`): **say in your report which folders it walks**,
because the conductor writes its scan-map row from that.

## Checks

The **checks command**, pure only: the Python readers (`test_keycloak_theme.py`, `test_keycloak_theme_govuk.py`, `test_superset_theme.py`, `test_service_inventory.py`, `test_dockerignore.py`, `test_harness_frontend_copies.py`,
`test_dockerfiles_numeric_user.py`, `test_install_page_build.py`, `test_doc_citations_check.py`, and the colour-drift check's own test); `ruff check .` in `OspreyFlow_Core`; `npm run lint` and `npm run typecheck`;
`npm test --workspace apps/workspace`, `apps/harness` and `packages/glass-shared`; `node scripts/dist_compare.mjs verify --build`. **Before your final report run by hand the cheap checks the conductor will run again before the
merge:** ruff and eslint on every file you changed, and the scan-map check for the test you add (a new test that walks the repository needs a row, which the conductor commits; say what to write). A merge attempt costs 25 minutes:
a lint error or a missing row found there is your round, not the conductor's. The browser gates (budget, accessibility, keyboard) are **not** run here: the owner proves them on GitHub on the merge commit.

## Out of scope

The fonts (B3); `fonts.ts`; the `.tsx` primitives; the JS colour mirrors; the rules files; the protected files; the budget numbers (slice E).
