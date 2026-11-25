# GR4a away report: trends shown together (25 November 2026, D246 away round)

Branch `away/GR4a`, from `4f77858a5`. Nothing pushed or merged; `main` untouched. Tests run through `~/osprey-d246/d246_ns.sh`
from `OspreyFlow_Core`. Synthetic data only. Not edited: `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`,
`spec/06_DECISIONS.md`, `spec/ADR_RESERVATIONS.md`, `osprey.yaml`, `data/`.

**State: the table is complete and green, with four questions for the owner (below). Two of them (the address, and case 2's
"place") were built in the only form the accepted decisions allow. Each needs the owner's word before the merge.**

## Commits, in order

| Commit | What |
| --- | --- |
| `388733d65` | Scenario TS written first in `spec/08` (before Scenario S, which must stay last for the Studio words gate). `reports-figures` row carries TS1 to TS15, route empty. `KNOWN_WITHOUT_SCENARIO` shrinks. The decision-10 citation diff. |
| `e9bc629f8` | Red: the page test, its fixture Conduit, the Playwright specs, the scenario test and the route-list pins. |
| `29122f884` | The page: `server/packTrends.ts`, `server/views/packTrendsWords.ts`, `tree-govuk/pack-trends.njk`, its rows in `pageList.ts` and `routes.yaml`. |
| `bbc58b554` | The pages build bundles `packTrendsWords.ts` with the shared package, as it does `helpWords.ts`. The six helpers are declared in `server/types/glassShared.d.ts` and held to the package's own types. HP9 counts `reports-figures` as an incomplete row. |
| `d05131259` | The shim writes `TrendFigures` out instead of importing it. The import made `tsc` emit `packages/schemas/generated/TrendFigures.js` beside the source. I found the stray file and deleted it; it was never committed. |
| `03808d8d1` | The scenario test's spec plants land in Scenario TS's own section. Two of them first hit the same sentences in Scenario AP and found nothing. |
| `f9ffb5725` | Scenario TS cites no `process/` file. `product-tree-link-check` (in `make ci`, not on the frozen list) found four. |
| this commit | This report. |

## The table of cases

| # | Case | State | Proof |
| --- | --- | --- | --- |
| 1 | Three trend items, stored order other than creation order | **green** | TS1: stored order (harbour, ferry, toll; added ferry, toll, harbour). Each shows title, period, "Counted on", marking, `trendSentence`, chart, and a table of the same figures (a bar and a row for every period, empty ones too). Includes a series case. |
| 2 | Middle item the reader can no longer read | **green, but see question 2** | TS2: the shared `WITHHELD_ITEMS_SENTENCE` appears once, above the trends, with no title, figure, count or place. No chart or table for it. All withheld: the sentence plus "This pack has no trends to show you." |
| 3 | No trend items | **green** | TS3: notes, an assessment and an entity (or nothing). The sentence and the link to Home appear; no chart, no table, nothing of the other items. |
| 4 | Reader without the right | **green** | TS4: no right, other rights only, or `read_reports` for a pack never published. All get the unknown path's 404, byte for byte but for the nonce, with no Conduit word and no right named. |
| 5 | Pack in a case the reader cannot see | **green** | TS5: a hidden case, a pack in another case, a pack or case that does not exist, no case, no pack, a repeated query. Each gets the same 404. A missing case or pack asks the Conduit nothing. |
| 6 | No answer or a 401 | **green** | TS6: no answer, 5xx, a text body, a failing published read, or a closed address all give 502 "could not be read" with no chart or table. A 401 gives the Studio's sign-in-again words (as AP4). |
| 7 | Body missing a required field | **green** | TS7: one case per required field of the eight generated interfaces the page reads (more than 25), built from the generated files' own field lists. Plus eleven wrong shapes. All give 502, never a zero. |
| 8 | Keyboard | **green** | `keyboard/pack-trends.spec.ts` TK1 to TK3 (tab order, skip link, Enter on the way back, table headers). Shown red with an extra link planted in the real template. TS11 checks the same order in vitest. |
| 9 | No script | **green** | `scripts-off/pack-trends.spec.ts` TO1 and TO2. Shown red with the table hidden in the real template. TS12: no script but the data block, no handler, no `style`, no `fill`/`stroke`, each chart an `svg` with classes and a `title`, followed by its table. |
| ruling 6 | Field census | **green** | TS8: every field of `PackDraft`, `ReportPack`, `PublishedPack`, `PackItem`, `TrendFigures`, `TrendDefinitionInput`, `TrendResult` and `TrendPoint`. A drawn field must change the page when changed; a field named in TS's "Left out, by field name" sentence must not. The scenario test also checks that each named field exists in the generated types. |
| rule 15 | Planted faults at the call site | **green** | TS15 plants into the real words module: reversed loop, sorted trends, withheld dropped, a note drawn, a missing total read as zero, `added_by` drawn, the version not drawn, a census name removed. Also plants into the real page (style, fill, script, no chart, no `title`, no table, skipped heading, a form, no row scope, a wrong or missing bar), and checks the fixture's refusals in the real routes' order. Scenario test: 26 plants. |

## Tests run (all through D246) and results

- `apps/pages` vitest, whole suite: **874 passed, 2 failed**. The two failures are the asset route's traversal probes (`assetsTraversal.test.ts`, `foundation.test.ts`), and they come from the wrapper, not this change. D246's `TMPDIR` lies under `~/.cache`, a dot-named folder, and Express's static serving refuses dot-named paths, so the planted leaky route cannot leak. With `TMPDIR` set to a plain folder in the same namespace, both files pass (32/32). They touch no file of this part.
- `pack-trends.test.ts` 18/18; `help.test.ts`, `admin-people.test.ts`, `buildLayout.test.ts` green (72 with the page test).
- Playwright GOV.UK folder (`npm run test:keyboard:govuk`): **14/14**. My two specs also shown red, as above.
- Typecheck: root `tsc --noEmit` 0 errors; the pages build's `tsc -p tsconfig.build.json` 0 errors.
  - The shim's conformance check was shown red with five planted stub faults, each failing the root typecheck: `periodsOf` returning `number[]`, `events: 1`, `as_of: "2026"`, `title: "x"`, `total: number | string`.
  - The first version of the reverse check used `Omit`, which keeps only the index signature of these types and so compared nothing. Planting found this; it is now written part by part.
- `eslint apps/pages`, `no_react_check.mjs` (PASS), `ruff check .` (Core): clean.
- Python, 13 files, 799 tests: **all passed** (after the two plant fixes). The files: `test_govuk_pack_trends_scenario.py` (36), `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`, `test_doc_citations_check.py`, `tests/harness/test_pages_setting.py`, `test_govuk_help_scenario.py`, `test_govuk_admin_people_scenario.py`, `test_pages_image_carries_no_react.py`.
- Gates: `design_check`, `colour_drift_check`, `ui_words_check` and `doc_citations_check` green. From `make ci`'s wider list I also ran these, all green: `product-tree-link-check` (after `f9ffb5725`), `test-file-coverage-check`, `route-coverage-check`, `schemas-check`, `no-branches-check`, `provenance-annotation-check`, `domain-model-coverage-check`, `no-langchain-check`, `authorized-query-check`, `demo-guide-check`. `cp-policy-check` was refused by D246: it needs `helm template`, the wrapper's no-container rule. The results of `client-name-check`, `confinement-check`, `slice-line-check` and `lanes-check` are in the last section.
- **Decision 10's citation, with the decision log's own checks** (ruling 5): `git archive HEAD` exported twice outside the checkout, the diff applied to one. `decision_log_publication_check`, `doc_citations_check` and `adr_reservations_check` exit 0 both ways, with identical output. `product_tree_link_check` also gave identical output both ways, so the diff changes nothing it reads.
- `graphify update .` could not be run: `graphify` is not installed on this account.

## What is left

- **Apply `GR4a_ADR152_DECISION10_CITATION.diff`** (this folder) to `spec/06_DECISIONS.md`. `git apply --check` passes against this branch. It replaces `services/api/app.py:19494` with `packages/schemas/packs.py:128`, added through `services/api/app.py:19762`, re-wrapping the one sentence. `packs.py:128` is `AddPackItem.trend_id`, as ruled; `PackItem.trend_id` is line 112.
- **GR3b:** this page's fixture is hand-written, as GR3a's was. It models the real routes' order and refusals, and the census and strict reader are made from the generated types. When GR3b lands, its answers should come from the real routes' goldens.
- **Merge overlap with GR3a**, which is still on its branch: both fill the `reports-figures` row and touch the route-list pins (`routes.yaml`, HP9, `test_tree_parity.py`, `test_pages_setting.py`, the help and AP scenario tests). If GR3a also imports the shared package from a page, both also change `build.mjs` and `glassShared.d.ts`. The chart rule in `spec/02` and the bar classes' stylesheet rule are GR3a's; this page's bars draw in the browser's default fill until then.
- I21's named test does not exist under its name (question 3).

## Questions for the owner (each is a ruling; none was guessed)

1. **The address.** You ruled `/packs/{pack_id}/trends`. Two things stand in its way:
   - A page's path is a plain path with no pattern (`apps/pages/server/pages.ts`, the route-module convention under ADR-152 decision 6). Every page with an identifier takes it in the query, as the dataset map does.
   - The pack routes need the case as well as the pack (`/v1/investigations/{id}/packs/{pack_id}`). No route finds a pack by its id alone, and decision 10 rules out a new one.

   **Built: `/packs/trends?case=…&pack=…`.** Options: (a) keep it; (b) amend the convention to admit path segments, e.g. `/cases/{case}/packs/{pack}/trends` or `/packs/{pack}/trends?case=…` (a change to `pages.ts`'s registration rule and its tests); (c) your words.
2. **Case 2's "that item's place says it is withheld".** The Conduit sends no place for a withheld item. `PackItem` "carries no position: the order of the list is the order, so a withheld item leaves no gap that says where it was", and `withheld` is a yes or no (ADR-124 decision 9; rule 3's existence rule). The page cannot know which items, or how many, were withheld, or whether they were trends at all.

   **Built: the shared sentence once, above the trends; the others in order; never an empty chart** (I21 holds). Options: (a) keep it; (b) placeholders in place, which would need the Conduit to say where withheld items sit. That amends ADR-124 decision 9, and decision 10's "no new Conduit route" rules it out for this part.
3. **I21's named test** (`test_a_board_shows_a_trend_its_viewer_can_no_longer_read_as_withheld_not_as_missing_data`) says "board". Your ruling 4 keeps "board" out of this page's code and words. **Built: the page test carries I21 by its id (TS2), and no file has the named test.** Options: (a) rename I21's test in the decision log (a diff for you to apply, e.g. `..._trends_shown_together_show_a_trend_...`); (b) allow the name for that one test.
4. **A reader with both rights, or an Editor of a published pack, sees the working pack** (the draft read answers first). Only a person without the right to record assessments sees the newest published version. That is my reading of "whoever may read the pack now"; please confirm, or rule that a published pack shows its published version to everyone.

## Notes for the verifier

- The page asks for the published version **only** after the working pack's route refuses for the right (its 403). Any other refusal is the 404 without a second call (TS4, TS9).
- The fixture Conduit (`test/govuk/packsConduit.ts`) answers in the real order: router (404/405) → bearer (401) → right (403 `right_required`) → case (404 `investigation_not_found`; a write as a Viewer is 403) → pack (404 `no such pack in this case`) → publication (404 `this pack has no publication`). It decides `withheld` from its world, as the store's query does. Successful writes are deliberately unmodelled (500).
- The scratch scripts used for the planted runs (`stub_plants.py`, `spec_plants.py`, `run_gates.py`) live in `~/.cache/gr4a-tmp/`, outside the checkout. Each restored the file it planted in; `git status` was clean after each.
