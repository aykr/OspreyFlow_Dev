# v0.6.0 #6: the confirming pass's list, before any fix (for the orchestrator's triage)

**What ran.** `keyboard/govuk-type-pass.spec.ts` ran at the branch's head on main 97dc544, with the mono-words fix in.
It covers every keyboard harness page that applies the brand, in each of every-harness's extra states, under
`brand=govuk`, at 1280×900. Every visible text element was measured by computed style.
- **Face:** mono is flagged unless the element is a value to copy (`.value`, `.identifier`, `td.numeric`, `code`,
  `kbd`, `samp`, `pre`).
- **Size:** off the scale where the element sits, read from the element's own `--fs-*` tokens.
- **Not read:** GOV.UK's header, footer, phase banner and skip link.

**Result:** 415 findings, 143 distinct. Below they are grouped by cause, with a recommendation for each. The counts
are raw findings, so one element seen in several states counts several times.

## A. A heading with no size of its own: 256 (real, in both looks)

An `h1`, `h2` or `h3` that its CSS sizes nowhere sits at the browser's own em sizes: h3 1.17em is 15.21px, h2 1.5em
is 19.5px, and h1 2em is 26px. Neither tokens.css nor primitives.css sizes a bare heading. `:is(h1…h6).value` sets
only the face (tokens.css:245).
- `h3.value` card and panel titles, 110: `reports/figureParts.tsx:73` (`style={{ margin: 0 }}` alone), and the
  same shape in AlertMonitoringBoard, ReportsView, RulesPanel, ListsPanel, AlertSourcesPanel, SentenceBuilder,
  RuleEditor and AlertQueue.
- `h2.value` section headings, 98: Admin › Models and Maps (`admin/sections/Models.tsx`, `Maps.tsx`),
  `App.tsx:2115` "Connection strength", History, HomePage's "Rules and Monitoring".
- Plain `h2`/`h3`, 31: HomePage "Figures", OperationsFigures, RolesHelpPage, IngestStudio; and
  `.strength-panel__heading`, 11 more (`primitives.css:592`, with no size).
- `h1` at 26px: "The graph" (search results) and `h1.value` "Home" (`home/AnswersForSection.tsx`), 6 of the
  product's (the raw 17 counted the map-view harness's own title, group E, 12 times; corrected 15 November).
- The same elements are off the scale in the standard look too, so this is not GOV.UK's alone.
- In Admin, home and welcome, where tokens.css remaps the scale, the em sizes multiply the remapped base, so they
  are off there as well.

**Recommended fix:** one rule in `primitives.css`, not tokens.css, at zero specificity so that every explicit size
still wins: `:where(h1) { font-size: var(--fs-23) }`, `:where(h2) { var(--fs-19) }`,
`:where(h3, h4) { var(--fs-16) }`, each with its line height. These follow tokens.css's own comments ("screen title",
"section heading", "panel title"). It changes the standard look's sizes too, which is wider than GOV.UK's pass:
**your call: both looks (recommended, since the scale is one rule in DESIGN.md), or scoped to
`[data-brand="govuk"]`.**

## B. The Ingest Studio's em sizes: 36 (real)

`fontSize: "0.85em"` (11.05px) on sample values and notes (`ingest/ProfileScreen.tsx:148`,
`ingest/publish/PublishScreen.tsx:361,423,437`, the "Draft" span), and `h1` at 1.1em (14.3px) on the studio's stage
titles ("Load rules", "Map — …", "Test — …"). **Fix:** `var(--fs-11)`/`var(--fs-12)` and `var(--fs-14)` or `var(--fs-16)`
from the tokens.

## C. A control at the browser's size: 36 (real, mostly)

Buttons and their spans at 13.333px, the user agent's control font: `button.icon-btn` "⬚", metrics-panel's
"Person · n1" and "1.000", the studio's "✓"/"!", "Saved views (4)". A `button` with no `font: inherit` keeps the
UA's size. **Fix:** `:where(button, input, select, textarea) { font: inherit }` in primitives.css. Same scope
question as A.

## D. Mono where the pass reads words: 38

- **D1, words in mono, 7 (real):** `span.home-glyph` "△" and "·" (alert-figures, start), a decorative glyph set in
  mono, and `span.selection-bar__reading` "direct" (`canvas/SelectionBar.tsx:129`, styled in `primitives.css`). **Fix:** the page's face.
- **D2, values the pass does not class, 31 (not faults: mark them):** the Ingest Studio's sample cells ("SYN-0441",
  "07700 900001", "2026-01-01T09:00:00Z", "HMP Fenwick Moor"), a row's JSON in a check's `li` ("row 4 : {…}"), and
  the SQL/JSON editors' `textarea`. These are values or code, so mono is right. **Fix:** class the cells and the
  `li` `.value`, and the pass counts a code editor's `textarea` as a value. No visual change.

## E. Harness-only: 35 (not the product; nothing to fix)

These are the harness's own chrome: `h1` "Map view harness", "Needs you harness", "Account unread harness",
"Weekly monitoring review", and buttons "After canvas" (`keyboard/harness.tsx`), "Shrink the map"
(`map-view-harness.tsx`) and "Hand over: Add a note" (`inspector-harness.tsx`). The pass will leave out
`[data-harness-chrome]` or the harness's own elements.

## F. GOV.UK Frontend's own components at GOV.UK's sizes: 14 (recommend: not a fault)

`h2.govuk-heading-m` 24px (Drawing boards), `h2.govuk-heading-l` 36px ("Search results for …") and
`h4.govuk-error-summary__title` 24px. These are GOV.UK Frontend classes at GOV.UK's own scale, as the header and
footer are. **Recommended:** the pass reads `govuk-*` elements as GOV.UK's, so nothing changes. The alternative is to
replace them with our classes on our scale. **Your call.**

## The pass itself

- Its scale list lacked `--fs-40`, now added; no finding was at 40px.
- It is skipped unless `GOVUK_PASS_OUT` or `GOVUK_PASS_STRICT=1` is set. It becomes a gate (strict, in the keyboard
  suite) only once the fixes are in and it has been shown red with one planted back (rule 15).

**Asked of you:** for A and C, both looks or GOV.UK only; for F, keep or replace; and that B, D1 and the D2 marks are
in scope. Everything else is recommended as above.

## The orchestrator's rulings (15 November 2026), as built

- **A and C:** fixed in both looks (`src/design/scale.css`).
- **F:** kept. The pass leaves out `govuk-*`.
- **B, D1 and D2:** in scope and fixed.
- **E:** left out of the pass (`data-harness-only`).
- **The pass:** a strict gate, red then green. `README.md` has the record.
