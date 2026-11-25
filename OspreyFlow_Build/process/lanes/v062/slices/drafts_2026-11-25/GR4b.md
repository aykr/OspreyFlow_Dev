# Slice GR4b · GR4 · Arranging the trends shown together: a GOV.UK form, scripts off, that posts the pack's new order to the existing order route (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper. **It builds on GR4a**, which is
built on the branch `away/GR4a` (seven commits from `4f77858a5`, unmerged, with four questions open for the owner in
`OspreyFlow_Build/process/lanes/v062/away/GR4a_AWAY_REPORT.md` on that branch). **GR4b waits for GR4a's merge and for
the owner's answers to its questions 1 (the address) and 2 (where a withheld item sits).**

**Question 0, against the plan's row:** "**GR4: A board page: saved trends together (Trends shown together)**". The
owner's GR4a ruling 1 (`RULINGS.md` line 21) is "read-only first ... Arranging is GR4b". **The reading holds.**

## What exists today (read on 25 November 2026; main at `4f77858a5`, GR4a at `away/GR4a`; re-read, lines move)

- **The order route, on main** (`OspreyFlow_Core/services/api/app.py:19912-19964`):
  - `PUT /v1/investigations/{id}/packs/{pack_id}/order`, behind `require_right(RECORD_ASSESSMENT)` and the **editor**
    gate (`InvestigationEditorDep`, :19919).
  - "Only the reader's own items move; each item withheld from them keeps its place." The body is `PackOrder`
    (`packages/schemas/packs.py:145-149`): `item_ids`, at most 200. It must name **every item the reader can see, of
    every kind, exactly once** (:19941-19942), or the route refuses with `PackItemRefused`, which is **422
    `pack_refused`** with its detail (:20327-20329).
  - The store keeps each withheld item in its place "worked out here, so no hidden item's id leaves the store"
    (`PackStore.reorder_visible`, `services/api/packs.py:847-866`). It locks the rows (`FOR UPDATE`) and touches the
    pack's `updated_at` (`_touch`, :644-647).
  - The route audits `reorder_pack` (:19948-19954) and answers the `PackDraft` in the new order.
  - **It takes no expected version.** Two editors reordering at once: the later write wins whole. The set check refuses
    a request made before an item was added or removed, but not one made before another person's reorder (question 4).
- **The read the page already makes.** The working pack, `GET .../packs/{pack_id}` (`app.py` about lines 19720 to
  19725), needs `RECORD_ASSESSMENT` at **viewer** level. So a viewer-level member of the case can see the working pack
  and still be refused by the order route (question 5). A pack item (`PackItem`, `packs.py` about lines 101 to 125) has
  a `kind` (trend, assessment, entity, note or alert) and **no position**: "the order of the list is the order".
  `withheld` is only a yes or no (GR4a's question 2).
- **GR4a's page, on its branch.** `apps/pages/server/packTrends.ts`, served `GET` at
  `/packs/trends?case={case}&pack={pack}`. Its header gives the reason: a page's path is a plain path in `pages.ts`, and
  the pack routes need the case, so both go in the query until the owner rules on `/packs/{pack_id}/trends`. Its words
  and strict reader are in `server/views/packTrendsWords.ts`, the template is `tree-govuk/pack-trends.njk`, and the
  fixture Conduit is `test/govuk/packsConduit.ts`, which answers in the real routes' order and refusals; its successful
  writes are "deliberately unmodelled (500)". "GET is the only method it answers, and it has no form, control or
  script." It reads the working pack first and, on that route's 403, the newest published version (GR4a's question 4).
  The shared withheld sentence appears once, above the trends.
- **How a page posts today.** Anti-forgery is `apps/pages/server/csrf.ts`: every method but GET, HEAD and OPTIONS needs
  the session's token, sent in the `_csrf` field of a url-encoded form (I17, `test/server/csrf.test.ts`). The Model
  step's save and discard (`server/model.ts`, IS2a) are the nearest page that posts to the Conduit from the server with
  the person's token.
- **The React original.** `apps/workspace/src/reports/PacksTab.tsx` reorders at about line 146. Read it; do not copy it.

## Questions for the owner (the proposal first)

1. **The control, with scripts off.** (a) **"Move up" and "Move down" buttons** on each trend, in one form per trend,
   each a submit with the trend's item id and its direction. The first trend has no "Move up" and the last no "Move
   down". After the move the page is sent again (`303`) and returns to the moved trend by its heading's fragment, so a
   keyboard user keeps their place. (b) A number field per trend and one "Save the order" button, which moves several
   at once but needs the person to renumber.
2. **What moves, given that the route takes every visible item.** The page shows only trends; the route needs notes,
   assessments, entities and alerts too. (a) **A move swaps the trend with the next visible trend in that direction.
   Every other item keeps its place among the visible items**, and withheld items keep theirs (the store's own rule). The
   page builds the full list from the working pack it has just read, and sends it. (b) A move swaps with the very next
   visible item of any kind. The trends page would then move a trend past a note the person cannot see on this page.
   Not proposed.
3. **Only the working pack.** (a) **The form is drawn only when the page read the working pack.** A published version
   is frozen (`packages/schemas/packs.py:6`: "Publishing freezes an immutable version"), so it never has a form, and a
   post naming a published pack is refused as the route refuses. (b) Your words.
4. **Another person's change in between (no expected version on the route).** (a) **The form carries the order of
   trends the person saw.** Before it sends anything, the server half reads the working pack again. If the visible
   trends' order differs from what the person saw, **nothing is sent**, and the page answers "This pack's order was
   changed while you had it open. Here it is now." The remaining gap, between that read and the `PUT`, is said in the
   scenario as a known limit, not a guarantee. (b) An expected version on the order route, which is a Conduit change.
   Decision 10 says "no new Conduit route", not "no new field", but it is the owner's to allow.
5. **A viewer-level member who may read the working pack.** (a) **The form is drawn for whoever reads the working pack.**
   When the order route refuses for the case level (403), the page says in words: "Only an editor of this case can
   change the order." The person already sees the pack, so this tells them nothing they did not know. (b) The page
   reads the case's level first and draws no form for a viewer. That is a second read, and a rule in the page (decision
   5 says the page adds no access rule). Not proposed.
6. **The route's 422 (`pack_refused`).** (a) **Treated as question 4's answer** ("the pack changed while you had it
   open"), because the only way the page's own list can fail the set check is a change since its read. The detail is
   never shown, since it is the Conduit's words. (b) The detail shown.
7. **The address.** (a) **The form posts to the page's own address** (whatever the owner rules in GR4a's question 1),
   with `POST`, and the page answers `GET` and `POST` there. (b) A separate address, `/packs/trends/order`.
8. **The scenario.** (a) **Scenario TS grows a section, TS16 onwards**, written first and red first. (b) A new
   scenario.

## The table of cases (each red first; planted faults at the real call site: rule 15)

The fixture Conduit (`packsConduit.ts`) **gains the order route, modelled on the real one**: editor level, the set
check (422 `pack_refused`), withheld items kept in place in its world, and the new order in its answer. Its successful
write stops being "deliberately unmodelled". When GR3b lands, the goldens come from the real route.

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A pack of three trends and two notes; "Move down" on the first trend | one `PUT` naming all five visible items, the first two trends swapped and both notes where they were; `303` to the page, which shows the new order with the moved trend's heading as the fragment | the page sending only the trends (the real route's 422; the fixture models it) |
| 2 | The same with an item withheld from the reader between the two trends | the `PUT` names only visible items; in the fixture's world the withheld item keeps its place | the page sending a guessed id for the withheld item (none can be known: the test proves no id the page was not sent leaves it) |
| 3 | First trend's "Move up", last trend's "Move down" | not drawn | drawn and sent as a no-op `PUT` |
| 4 | Another person reordered after the page was drawn | no `PUT`; the sentence of question 4 and the pack as it is now | the page sending its stale order anyway |
| 5 | An item added or removed in between (the route answers 422) | the same sentence; no Conduit words shown | the 422's detail shown |
| 6 | A viewer-level member presses "Move down" (the route answers 403) | "Only an editor of this case can change the order"; the pack unchanged | the 403 shown as the 404 page (it is a known pack: question 5) |
| 7 | A post with no anti-forgery token, or the wrong one | refused by the page service, nothing sent (I17) | the check removed from the page's route |
| 8 | A post naming a pack, case or item the reader cannot see, or a published pack | the same 404 page, words and status, as GR4a's case 4; nothing sent | a post with an item id from another pack, sent through |
| 9 | A published version read (no working-pack right) | the page as GR4a draws it, with no form | the form drawn |
| 10 | One move | exactly one re-read and one `PUT` (one `reorder_pack` audit row) | two `PUT`s |
| 11 | The Conduit gives no answer, or 401, at the `PUT` | the 502 "could not be read" page, saying the order was not changed; a 401 says to sign in again | a `303` as if it had moved |
| 12 | The form's markup | each button names its trend in words ("Move 'Ferry crossings' down"); no `style`, no script | a button reading only "Down" (the a11y check) |
| 13 | Keyboard | each button reachable, and Enter moves the trend; after the move the focus target is the moved trend's heading. A new action, so a case per button in `keyboard/pack-trends.spec.ts` (rule 13) | a button out of the tab order |
| 14 | Scripts off | the move completes by the form (I4) | none: the spec runs with scripts off |

## Checks (frozen when cut)

GR4a's list: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; `pack-trends.test.ts`, the
GOV.UK keyboard and scripts-off folders (`npm run test:keyboard:govuk`); `test_govuk_pack_trends_scenario.py`;
`test/server/csrf.test.ts`; `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`,
`test_pages_foundation.py`, `test_design_gates_reach.py`; `test_ui_words_check.py`, `test_copy_says_no_client.py`,
`test_doc_citations_check.py`; `tests/harness/test_pages_setting.py`; `ruff check .`;
`make -C OspreyFlow_Build design-check`; `colour_drift_check`; the cheap checks of 20 November.

## Out of scope

Adding, removing, refreshing or publishing items; arranging anything but trends; a drag-and-drop module (a later
enhancement with scripts on, held to the keyboard route this slice builds: I7); an expected version on the route
(question 4 (b)); any Conduit change; `apps/workspace`; the drawing board (ADR-143).
