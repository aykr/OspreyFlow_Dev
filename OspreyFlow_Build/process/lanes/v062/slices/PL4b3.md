# Slice PL4b3 · PL4 · The fonts are listed once in `packages/design`, and a test fails if either front end loads a font the list does not name (slice B3; no font and no weight in the code changes)

- **Build id:** PL4 (ADR-152 R2, decision 6: "tokens.css, primitives.css, fonts; read by the React workspace and tree-default alike"). The owner's ruling of 20 November 2026 (`RULINGS.md`, "The rest of the design folder", item 3):
  `fonts.ts` may stay in the workspace because it is tied to the Vite bundle; **which families and weights are used is stated once in `packages/design`, and both front ends load from that list, each its own way; a test fails if
  either loads a font the list does not name.** Six points confirmed the same day (below).
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4b2 merged (it may start building the moment PL4b2 merges; it may not merge until GitHub's run on PL4b2's merge commit is green for the budget, accessibility and keyboard jobs).
- **Status of this brief:** written by the conductor on 20 November 2026 from a read-only scout and the owner's rulings of the same day; the conductor read `tests/harness/test_harness_frontend_copies.py` and
  `apps/workspace/scripts/sync_govuk_assets.mjs` itself. **While PL4 runs nothing else touches `apps/workspace`.**

## What the scout found (the builder re-reads)

`apps/workspace/src/design/fonts.ts` (lines 3 to 7) imports Atkinson Hyperlegible Next 400, 600 and 700 and IBM Plex Mono 400 and 600 from `@fontsource/*`; `src/main.tsx` (line 4) and four keyboard harnesses load it; `@fontsource` is declared
in `apps/workspace/package.json` only. The CSS uses only the weights 400, 600 and 700. GDS Transport is named in `tokens.css` (about line 189); its files are copied by `scripts/sync_govuk_assets.mjs` into
`apps/workspace/public/assets/govuk/fonts/` with a stylesheet (`govuk-frontend.css`) that carries its `@font-face` rules; it is not from `@fontsource`, and its licence limits it to services on gov.uk addresses
(`spec/00_ARCHITECTURE.md` about lines 1150 to 1156). `apps/harness` loads tokens and primitives and no font; `harness/keycloak_theme.py` uses `var(--ui)` and `var(--mono)` and loads no font file; `apps/pages` loads no font and no
stylesheet today (no static middleware; `test/server/page.test.ts` forbids an external `<link>`), and its CSP has no `font-src`, so a same-origin font falls under `default-src 'self'`. The existing `fonts.test.ts` checks that `main.tsx`
imports `./design/fonts`, that `fonts.ts` imports exactly its `WANTED` list, and that each family is in `tokens.css` with a `url(./files/…woff2)`.

## What

1. **The list: `OspreyFlow_Core/packages/design/fonts.json`**, one entry per family: `family` (the CSS name), `role` (`ui` or `mono`, or `govuk`), `source` (`@fontsource/<package>` or `govuk-frontend`), `weights`, `licence`. Two entries from the code as it ships,
   and **no weight in the code changes** (the owner: "the list states what the code ships"): Atkinson Hyperlegible Next, `ui`, 400, 600, 700, OFL-1.1; IBM Plex Mono, `mono`, 400, 600, OFL-1.1. **No `subsets` field** (the owner: agreed; narrowing the imports would change the
   built bytes). **GDS Transport has its own entry with both conditions written on it, as fields the test reads:** shown only when the GOV.UK identity switch is on (`appearance.govuk_identity`), and only on a gov.uk address; source
   `govuk-frontend` self-hosted under `/assets/govuk/`; licence: restricted to services on GOV.UK domains (`spec/00_ARCHITECTURE.md`).
2. **The workspace loads from the list, in its own way.** `fonts.ts` stays where it is (it imports the `@fontsource` CSS for the Vite bundle) and is **not changed**. A test (a Python test in `tests/glass_trees/`, and `fonts.test.ts` adapted so its `WANTED` list
   is **derived from `fonts.json`**, not restated: do not weaken it) shows: every `@fontsource` import in `apps/workspace/src` (and the keyboard harnesses, `apps/harness`) is a family and weight the list names, and every listed `@fontsource` weight is imported; a
   family in `@font-face` rules of the generated `public/assets/govuk/govuk-frontend.css` (when that file exists) or the file names in `public/assets/govuk/fonts/` that is not on the list fails; the GDS Transport entry carries both conditions and is the only entry with them.
3. **`apps/pages` loads from the list, in its own way.** It loads no font today, so the test is a scan with nothing to find that must still be shown red (rule 15): it scans `apps/pages` (sources, views, static files, built output) for `@font-face`, font URLs and
   `@fontsource` imports and requires every family it finds to be on the list; **and it fails on `GDS Transport` anywhere in what the default tree serves** (the font half of ADR-152 I9). Planted faults at the real call-site shape: an unlisted `@font-face` in a pages view; an
   unlisted `@fontsource` import in `fonts.ts`; `GDS Transport` in a pages stylesheet; each red, and green on the real tree. Do **not** add `@fontsource` to `apps/pages/package.json` (the lockfile and the image's `npm ci` layout change with it): that waits for the first page build that
   loads a font (PL7), whose brief takes this rule as a prerequisite.
4. **Invariant I9 is named, not touched.** The proof pieces ADR-152 names for I9 are `tests/glass_trees/test_default_tree_carries_no_govuk_assets.py`, `apps/pages/test/govuk/identity.spec.ts`, `test_govuk_identity_is_off_by_default` in `tests/harness/` and a case in
   `apps/workspace/src/brand/brand.test.tsx`. **The conductor searched main on 20 November: none of the four exists yet** (the build that adds the default tree's assets adds them). So nothing here "stays as it is": B3 neither writes nor replaces them, and says in its report
   if it finds any of them. Its own font test carries only the font half (item 3).
5. **Amendment 2 of ADR-152, short** (rule 11), in `OspreyFlow_Build/spec/06_DECISIONS.md`, recording the owner's ruling of 20 November 2026: decision 6's "fonts" is met by one list in `packages/design/fonts.json` that both front ends load from, each its own way; `fonts.ts` stays in the workspace because it
   is tied to the Vite bundle; a test fails if either loads a font the list does not name; GDS Transport is listed with its two conditions. Add the ADR number's reservation row to `OspreyFlow_Build/spec/ADR_RESERVATIONS.md` in your branch (lane `v062 PL4b3`, status `written`).
   If another slice appends to the same tail of the decision log, **the later one merges main in** (no question to the owner); the ledger's order is by landing.
6. **The weights text.** `spec/design/DESIGN.md` (about lines 55 and 56) says Atkinson 200 to 800 and Plex 400, 500 and 600; the code ships 400, 600 and 700 and 400 and 600. The owner applies a diff the conductor gives him
   (`slice-line/proposals/PL4B3_DESIGN_WEIGHTS.diff`); **do not edit `DESIGN.md` and do not change a weight in any code**.
7. **Protected and rules files.** Write nothing in the Core Makefile, `ci.yml`, `release.yml` or any `CLAUDE.md`; if the new test needs a gate line, give the exact diff in your report (it must pass `git apply --check`).

**The proof that nothing changed:** the workspace's dist is untouched by this slice (no source file of the bundle changes), so `node scripts/dist_compare.mjs verify --build` says SAME; run it and say so.

Binding: process/CLAUDE.md rules 11, 12, 15; ADR-152 decision 6 and invariants I1, I9, I11, I13; `spec/00_ARCHITECTURE.md` section 6 (self-host the fonts) and the ADR-132 text on GDS Transport; the owner's secret rules; the 18 November ruling on the client's name;
British English. Fonts are SIL OFL 1.1: the licence check (`tests/licence_check/`) stays green.

## Acceptance test

Pure, red first against the real tree: `OspreyFlow_Build/tests/glass_trees/test_fonts_list.py` (items 1 to 3: the list's shape and both conditions on GDS Transport; the workspace's imports against the list; the pages scan against the list and against GDS Transport; each planted fault red,
at the real call-site shape). It reads `packages/design/fonts.json`, `fonts.ts` and the other workspace sources, the generated GOV.UK stylesheet when present, and `apps/pages`; it walks the repository: **say in your report which folders it walks**, because the conductor writes its
scan-map row from that. `fonts.test.ts` is adapted as item 2 says and stays green.

## Checks

The **checks command**, pure only: the licence checks (`tools.licence_check`, `licence_check.mjs`), `tests/glass_trees/test_fonts_list.py`'s neighbours (`test_no_react_check.py` and the other `glass_trees` tests), `test_doc_citations_check.py`, `ruff check .` in `OspreyFlow_Core`, `npm run lint`, `npm run typecheck`,
`npm test --workspace apps/workspace` and `apps/pages`, and `node scripts/dist_compare.mjs verify --build`. **Before your final report run by hand the cheap checks the conductor will run again before the merge:** ruff and eslint on every file you changed and the scan-map check for the test you add
(a row the conductor commits; say what to write). A merge attempt costs 25 minutes: a lint error or a missing row found there is your round.

## Out of scope

Moving `fonts.ts`; any change of a font, weight or subset in the code; `@fontsource` in `apps/pages`; the I9 tests; `DESIGN.md`; the rules and protected files; the budget numbers.
