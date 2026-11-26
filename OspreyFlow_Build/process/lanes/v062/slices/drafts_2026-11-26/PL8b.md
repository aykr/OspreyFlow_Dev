# DRAFT · PL8b · The panel frame mounted on a page: markup, module, sizes in the stylesheet, and the ten keyboard cases (the conductor, 26 November 2026)

**Status: a draft, not ruled.** The owner asked for it ("Draft PL8b", 26 November 2026). No row is in `slices.tsv`.
`drafts_2026-11-26/INDEX.md` (item 3) and `CHAIN_PLAN.md` (row 19 and "Named for the conductor", item 4) name it: **GG3's
row needs PL8, and PL8a built the frame's store and its attach point but mounted it on no page.** Read on main at
`68918c0`; re-read every line before cutting.

## What exists on main

- **The store and the attach point (PL8a, merged `1d16bb2`).** `packages/glass-shared/src/layout/panelFrameStore.ts`
  (`createPanelFrameStore` :328, `PANEL_ACTION_STORAGE` :88, `SIZE_WRITERS` :109, `windowViewport` :157, `upperLimits`
  :168, `shownSizes` :288, `fitToWindow` :230, `findInlineStyle` :532) and `panelFrameAttach.ts` (`attachPanelFrame`
  :179; its header, :1-45, names every hook the markup must carry: `data-panel-frame="side|timeline"`,
  `data-panel-slot`, `data-panel-body`, `data-panel-header`, `data-action`, and the sashes'
  `data-sash`/`data-from`/`data-max`). Both are exported from `packages/glass-shared/src/index.ts:105-106`. **The attach
  writes sizes as data attributes and `aria-valuenow` only; "what turns a number into a width is the page's stylesheet"**
  (`panelFrameAttach.ts:5-7`).
- **The ten actions** are `PANEL_FRAME_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:1308-1320`).
  **The spec table** is `spec/02_GLASS_FRONTEND.md:380-405` (each action's *Kept*, *Normal state* and *Scripts off*; the
  owner's rulings of 24 November). Its guard is `tests/glass_trees/test_panel_frame_spec_table.py`.
- **The side panels' ids are the workspace's four** (`panelOrder.ts:14`: `inspector`, `metrics`, `query-builder`,
  `connections`). **The keys are shared:** `ospreyflow.side-panel-order`, `ospreyflow.side-panels-folded`,
  `ospreyflow.layout-sizes`. ADR-152 decision 7 serves `pages` and the workspace on **one origin**
  (`spec/06_DECISIONS.md:41076-41081`), so both read the same browser storage.
- **How a page loads a script:** a `.ts` file directly in `apps/pages/modules/` is bundled to one module
  (`apps/pages/scripts/assets.mjs:13-15`, :219-269). The one module today is `modules/studio-frame.ts`. The policy is
  `script-src 'self' 'nonce-…'` and `style-src 'self' 'nonce-…'` (`apps/pages/server/headers.ts:37-38`).
- **Inline style:** ADR-152 decision 3 (`spec/06_DECISIONS.md:40997-41002`) says no inline `style` attribute, and "a
  CSSOM write is allowed only through a named helper the pattern note lists". **No pattern note exists on main** (none
  under `packages/glass-shared` or `apps/pages`).
- **The keyboard runner:** `apps/pages/keyboard/` (Playwright, the real pages server, a fake Conduit:
  `keyboard/RUN_RECORD.md`). **It is not in CI**: `keyboard/ci-wiring.patch` adds a `pages-keyboard` job, and no such
  job is in `.github/workflows/ci.yml` on main. The workspace's model is `apps/workspace/keyboard/panel-frames.spec.ts`
  (ten cases, `assertAllCovered` at :222) and `frame-scroll.spec.ts`. Both stay green and are not touched.
- **The function row:** `apps/pages/FUNCTIONS.yaml:371-377` (`panel-frames`, slice PL8, `route: ""`, "planned").
- **PL8a's condition is met:** "slices that mount it on a page wait for PL9's second half" (`slices/PL8a.md:10`). PL9b
  merged (`a89d8de`: token renewal and sign-out at the identity provider).
- **No GOV.UK or Default page has a side column yet.** The pages that will fill one are GG3's (inspector, search,
  timeline, documents: `CHAIN_PLAN.md` row 72 onward). GG3a is cut to mount no frame (`slices/GG3a.md:17-18`).

## What it proposes

1. **One frame partial per tree** (`tree-default/` and `tree-govuk/`, the same hooks, each tree's own classes), taking the
   panels a page passes. Scripts off: every panel open, at its default size and in its default order, with **no
   control in the markup** (spec/02's *Scripts off* column; ruling 3 of 24 November). The controls are added by the
   module, not written by the server.
2. **One module**, `apps/pages/modules/panel-frame.ts`: it creates the store, calls `attachPanelFrame` on each
   `[data-panel-frame]` root, inserts the controls, and nothing else (a delegated listener: decision 3).
3. **Sizes reach the stylesheet through one named CSSOM helper** (question 3), listed in a new pattern note, so no
   `style` attribute is ever written and `findInlineStyle` stays green.
4. **The pages' `panel-frames.spec.ts`:** one case per action id, with and without scripts, and
   `assertAllCovered("PANEL_FRAME_ACTIONS", …)` (rule 13). Also a pages `frame-scroll` case (ruling 4 of 24 November).
   Each case is shown red against a planted fault in the module or the partial (rule 15), as IS5a's record does.
5. **The first host is a test-only page** (question 1). The first product page to mount the frame is GG3a's (a step in
   its own later round, or GG3c's), which adds its own keyboard steps.

**Access control:** none of its own. The module reads and writes this browser's storage only and makes no request. Every
page that mounts it keeps its own rule-4 tests.

## Questions (each with a proposed (a))

1. **Where it mounts first.** (a) **A fixture page served only by the keyboard runner's server** (registered in the
   runner's start, never in `pageList.ts` or a tree's `routes.yaml`), carrying all four side panels, the timeline and a
   Details control as stand-ins, so all ten actions are proven end to end before any product page has a column. The
   function row stays "planned" until a served page mounts it. (b) Mount it now on GR1a's case page with an empty
   column (a column with nothing in it, which no reader needs).
2. **The pages' panel ids and the shared keys.** (a) **The pages use the workspace's four ids and the same three keys**
   where a page's panel is the same panel (GG3's inspector is `inspector`), so an analyst's order, folds and sizes are
   the same in both, as "this browser" in spec/02 says. A page panel with no workspace counterpart gets no id until it
   has one (the store's id list stays `panelOrder.ts`'s). **The unknown-id case is pinned by a test:** a page writing an
   order the workspace does not know is ignored by `normaliseFolded` and the order normaliser, never an error. (b)
   Separate keys for the pages (the analyst's choices differ between the two).
3. **How a size becomes a width with no inline style.** (a) **One helper, `setFrameSize(element, axis, px)`, in
   `packages/glass-shared/src/layout/`,** the only CSSOM write. It sets a custom property (`--panel-frame-side-width`
   etc.) through `element.style.setProperty`, which the policy's `style-src` does not refuse (it refuses `style`
   attributes in markup, not CSSOM writes). A new pattern note, `packages/glass-shared/src/PATTERNS.md`, lists it as
   decision 3 requires. A test fails if any other file in `modules/` or `glass-shared/src/layout/` writes to `.style`.
   The stylesheet reads the custom properties. (b) Stepped attribute selectors in the stylesheet (one rule per 16 px
   step). This cannot hold the timeline's seven tenths of the window and grows with every limit.
4. **The timeline and Details.** (a) The partial draws the timeline region and the Details control **only when a page
   passes them**. The fixture page passes both. A product page gets them with GG3's timeline and GG2e's canvas toolbar.
5. **The keyboard runner's CI job (owner: a CI file).** (a) **The runner's record, run by hand before the report, as
   IS5a's is (`keyboard/RUN_RECORD.md`),** and the owner's `ci-wiring.patch` extended by a diff naming the new spec. No
   change to `.github/` from the line. (b) Wait for the owner to apply `ci-wiring.patch` first.
6. **Both trees.** (a) **The same partial in both, by ADR-070 Amendment 1** (the GOV.UK pages stay as close to Default
   as plain TypeScript allows; the light theme only). The GOV.UK one uses `govuk-` classes for its buttons. One
   keyboard run per tree. (b) Default tree only, the GOV.UK tree later.
7. **What the module does on a page with no frame.** (a) Nothing: it finds no `[data-panel-frame]` root and attaches
   none. A case proves it, so one module can be loaded on every page of a family. (b) Loaded only by pages that mount a
   frame.

**No question here is the owner's** except 5 (a CI file). It names no key, credential or security rule. The one
security-adjacent fact is that the module reads only this browser's storage on the one origin, which question 2 pins.

## What it waits on

Nothing to start (PL8a and PL9b are merged). **To be useful,** GG3a's or GG3c's column. **It collides with** GR1a, GG4a
and GR3a's route lists only if question 1 is (b). With (a) it touches no served route.

## Size

M: one partial in two trees, one module, one helper and its pattern note, the stylesheet's rules, and a keyboard spec of
about twenty cases (ten actions, with and without scripts, and the frame-scroll case).
