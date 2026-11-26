# GR1a away report: the reader's cases and one case's page with its brief, read-only (25 November 2026, D246/D247 away round)

Branch `away/GR1a`, from `4a9820ada`. Nothing was pushed or merged, and `main` is untouched. Every test ran through
`REPO=~/away-gr1a ~/osprey-d246/d246_ns.sh` from `OspreyFlow_Core`. All data is synthetic.

These files were not edited: `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`, `spec/06_DECISIONS.md`,
`spec/ADR_RESERVATIONS.md`, `osprey.yaml` and `data/`. No decision record changes, so this round has no diff file.

**State: the table is complete and green. Five questions for the owner follow (below).**
- **Question 1, the address:** built in the only form the accepted decisions allow, following the GR4a precedent. It needs the owner's word before the merge.
- **Questions 2 to 5:** each was built in the conservative reading. Each needs the owner's confirmation.

## The rulings this round worked from

The owner's rulings of 25 November on GR1a's draft are given here, since they are not yet in `RULINGS.md`. That file is the
conductor's to write, and this round did not edit it.

Every proposal (a) was accepted:
- read-only `/cases` and `/cases/{case_id}`;
- New case is GR1b;
- GR1 owns the case list;
- `/` is unchanged;
- no level, a level too low, another unit and a missing case all get the same 404 page;
- closed tabs are listed with "You closed this case's tab";
- one read per render, pinned by a test;
- a new scenario CS, written first and red first;
- the strict reader and the field census;
- attachments are shown by their kind only.

For question 1b, the owner gave the exception: GR1a starts now, before GG2b. One more instruction: if the route sends an
attachment the reader may not open, stop that row and write a question (rule 3); never filter in the page.

**The attachment stop did not arise.** `services/api/case_brief.py` (its module docstring, "Rule 3: an attachment the reader
may not read is left out entirely", and `BriefAttachment`) drops such an attachment in the store's title resolver, on every
read. The fixture models the same thing, and CS4 shows it: an assessment the reader may not read is sent to nobody and drawn
for nobody.

## Commits, in order

| Commit | What |
| --- | --- |
| `762a28da0` | Scenario CS written first in `spec/08`, before Scenario S (the Studio words gate needs S last). The `cases-and-views` row carries A7, B14, B21 and CS1 to CS15; its route stays empty. |
| `30383aaae` | **Red first:** the page test, its fixture Conduit, and the scenario test with the field census. The page test failed to import; the scenario test had 34 failures. |
| `a46fe0788` | The page: `server/cases.ts`, `server/views/casesWords.ts`, `tree-govuk/cases.njk`. Its rows went into `pageList.ts` and `routes.yaml`. The words are bundled with the shared package (`apps/pages/scripts/build.mjs`, `server/types/glassShared.d.ts`). |
| `298ffac0d` | The keyboard and scripts-off specs (CS12, CS13), each shown red with a planted fault in the real template. |
| `ac84046c5` | The route-list pins name the tree's third page in HP7/HP9/HP10, AP10, `test_govuk_{help,admin_people}_scenario.py`, `test_tree_parity.py` and `test_pages_setting.py`. |
| `b3d3b5f6d`, `22c51beb8`, `30f190116` | The census comparison became one function, shown red by planted censuses. CS10 checks every field's shape, a gap found by planting. A presence check that could not fail on its own was removed (rule 15). One cited path was written out in full (`citation-check`). |
| `33480dd3f`, `10685cdf7` | Fixes for an independent read-only review's findings (below). |
| this commit | This report. |

## The table of cases

| # | Case | State | Proof |
| --- | --- | --- | --- |
| 1 | Three cases at different levels | **green** | CS1. A table in the route's order: caption, column headers and a row header. Each name links to `/cases?case=<id>`, followed by the level in the Help page's words, the domains by the Studio's labels and the datasets by name. The made time is the picker's `utcStamp`, and an untitled case gets the picker's name. An other-unit case and an unshared case are never drawn. The fixture's order is one that no sort gives (by raw name, label or time, either way). |
| 2 | No cases | **green** | CS2: "You have no cases to show.", with no table, caption or column header. |
| 3 | A closed tab | **green** | CS3: listed in its place, with "You closed this case's tab". |
| 4 | One case's page | **green** | CS4. The case's name is the one level-1 heading. Then its level, domains, datasets and made time. Then the brief in the route's order: the priority, and each requirement's text, its status ("Open"/"Answered", as the React brief says them), when it was answered, and its attachments by kind ("A saved trend", "A saved pattern", "An assessment", "A canvas view"). No title or identifier is shown. |
| 5 | An empty brief | **green** | CS5: "This case has no brief yet." and no list. A brief with no priority gets "No priority information requirement is set."; one with no requirements gets "No information requirements yet." (both the React brief's words). |
| 6 | No level, another unit, no such case | **green** | CS6: the unknown path's 404 page, byte for byte but for the nonce, with one call and nothing more asked. Any other refusal of the case's read (403, 409, 422) gets the same page. These values give the same page and ask nothing: an empty `case`, a repeated one, `.`, `..` and `%2E%2E`. |
| 7 | A level too low, or no `investigate` for the brief | **green** | CS7: the brief's 403, or any 4xx but a 401, gets the same 404 page, with no Conduit words and no right named. The list is not asked. A level too low can only come from the case's read at Viewer, which is the lowest level, so it is covered by case 6's 403. |
| 8 | One render | **green** | CS8: exactly `GET /v1/investigations/{id}`, then its brief, then the list, once each. That is one audit row. No browser headers go on; an unsigned request asks nothing; a write method is a path nothing serves. |
| 9 | No answer, or a 401 | **green** | CS9. A 5xx, no answer, a closed address or a text body gives the 502 "could not be read" page as an alert, with no table, brief or part of one. A 401 on any of the three reads gives the Studio's sign-in-again words. A case the list does not hold is "could not be read", never drawn without its level. |
| 10 | A missing required field | **green** | CS10. Every one of the 25 fields the five models send is removed in turn, one case a field. Each is also given a wrong shape, one case a field. Eleven more wrong values cover each closed field and times that do not parse. All give "could not be read". |
| 11 | Keyboard | **green** | `keyboard/cases.spec.ts` CK1 to CK3: the tab order of both pages; Enter on a name opens its case, and Enter on each way back works. Shown red by taking the link off a case's name in the real template. |
| 12 | Scripts off | **green** | `scripts-off/cases.spec.ts` CO1 and CO2, and CS13: no script but the data block, no handler and no inline style. Shown red with the same plant. |
| ruling 8 | Field census | **green** | CS11 and `test_govuk_cases_scenario.py`. Every field of `InvestigationListing`, `Investigation`, `CaseBrief`, `BriefRequirement` and `BriefAttachment` (read from the source by `ast`) is either drawn or named in CS's "Left out, by field name" sentence. A drawn field changes the page when changed; a left-out one does not. The page's allowed values are held to the models' own (`AccessLevel`, `DomainPack`, `RequirementStatus`, `AttachmentKind`). |
| rule 15 | Planted faults | **green** | Below. |

### Planted at the real call site (rule 15)

`~/gr1a-tmp/plants.py`, outside the checkout, changed one thing in the real `casesWords.ts`, `cases.ts` or `cases.njk`, ran the
page test and restored the file from git. `git status` was empty afterwards. All 21 plants went red on the case they name:
- **The list:** a case skipped (CS1); the rows sorted five ways: by name, by name reversed, oldest first, newest first (CS1); a closed tab not said (CS3); the link taken off a name (CS1).
- **The case page:** a status in other words (CS4); an attachment's title drawn (CS4); an empty brief drawn as a list (CS5).
- **Refusals:** the brief's 403 passed through in its own words (CS7); a refused case read other than a 404 drawn as could not be read (CS6); a dot segment passed to the Conduit (CS6).
- **The reads:** the case read twice in one render (CS8); a failed list drawn as an empty list (CS9).
- **The reader:** a type check removed for `dataset_ids` and for an attachment's title (CS10); a time not checked (CS10).
- **The census and words:** withheld datasets said as "None" (CS1); a left-out field drawn, the owning unit (CS11).
- **The page:** a script added (CS13).

**Planting found three real gaps, each now fixed:**
1. CS10 had no wrong-shape case for most fields.
2. A raw-name sort passed CS1, because the untitled case's empty name sorts first anyway.
3. The strict reader's separate presence check could not fail on its own, since each field's type check already refuses `undefined`. It was removed.

The scenario test's own plants (30) and the page test's CS15 group plant into in-memory copies and the real HTML. The fixture's refusals
are checked in the real routes' order: router, then bearer, then route-level right, then the case's gate. Each one is checked.

## The independent review and what changed

A read-only lane reviewer read the branch. Its findings were checked against the source and fixed in `33480dd3f` and `10685cdf7`.

**Fixed:**
1. **The fixture sent dataset names the real list withholds.** `datasets.of_case` reads none for a reader holding no right (`reads_dataset_names`, ADR-099 Amendment 11). The fixture now models that. The page says an empty list as "None shown", never "None", because an empty list cannot tell a case reading none from one whose datasets are withheld (see question 3).
2. **`?case=.` and `?case=..` reached other routes.** `new URL` folds dot segments. Both are now the 404 page, and nothing is asked.
3. **The fixture claimed a 404 for routes the real Conduit serves** under a case (`/views`, `/datasets`, `/tab`, `/access`). These are now "not modelled" (500). An unknown bearer now gets the resolver's kind of words, not FastAPI's missing-bearer words.
4. **Two CS15 plants could pass by another path.** They now run CS5's and CS9's own checks (`emptyBriefProblems`, `failedListProblems`).
5. **The strict reader's closed values were hard-coded, and any string passed as a time.** The values are now held to the models' own by the scenario test, each with a planted fault. A time that does not parse is "could not be read".
6. **Smaller points:** the claim about the order was false (fixed as above); a refused case read other than a 404 had no case (added); the count was loose (now exactly 25); an unused variable was removed.

**Not done here:** **no page of the GOV.UK tree has an axe scan.** That is the tree's gap, not this part's: Help and Admin People have
none either. It should be its own part, or a GR3b-like structural one. `isObject`/`isText` repeat `adminPeopleWords.ts`'s two one-line
helpers; I left them rather than make AD3a's file a shared module in an away round.

## Tests run, all through D246

**Page tests (`apps/pages` vitest):**
- Whole suite: **909 passed, 2 failed.** The two failures are the asset route's traversal probes (`assetsTraversal.test.ts`, `foundation.test.ts`). They are the wrapper's: D246's `TMPDIR` sits under a dot-named folder, as GR4a found. With `TMPDIR` set to a plain folder, both files pass, 32 of 32. They touch no file of this part.
- `cases.test.ts`: 22 of 22.

**Playwright, the GOV.UK keyboard and scripts-off folder (`npm run test:keyboard:govuk`):** 14 of 14. Planting the link fault turned 4 of the new cases red.

**Python, 13 files, 837 tests: all passed.** The files:
- `test_govuk_cases_scenario.py` (39)
- `test_functions_yaml.py`
- `test_tree_parity.py`
- `test_no_react_check.py`
- `test_pages_foundation.py`
- `test_design_gates_reach.py`
- `test_pages_image_carries_no_react.py`
- `test_govuk_help_scenario.py`
- `test_govuk_admin_people_scenario.py`
- `test_ui_words_check.py`
- `test_copy_says_no_client.py`
- `test_doc_citations_check.py`
- `tests/harness/test_pages_setting.py`

**Static checks, all exit 0:**
- root `tsc --noEmit`
- the pages build's `tsc -p tsconfig.build.json`
- `eslint apps/pages`
- `no_react_check.mjs`
- `ruff check .` in Core, and with the Build tree's own settings on the new test
- `node apps/pages/scripts/build.mjs --out` to a scratch folder. The built `casesWords.js` holds the shared package's words and imports no workspace package.

**`make` gates, with `make`'s own exit code (pipefail), all 0:**
- `design-check`, `ui-words-check`, `citation-check`, `product-tree-link-check`
- `test-file-coverage-check`, `route-coverage-check`, `schemas-check`, `no-branches-check`
- `authorized-query-check`, `demo-guide-check`, `decision-log-publication-check`, `provenance-annotation-check`
- `domain-model-coverage-check`, `no-langchain-check`, `confinement-check`
- `slice-line-check`: 825 passed, 1 skipped. The wrapper's clean-up then prints `rm` refusals for read-only files a slice-line test leaves in its run folder, as GR4a saw.

**Not run:**
- `client-name-check`: `client_names.local.sha256` is not on this machine, as for GR4a.
- `lanes-check`: GR4a found it fails under D246 for the wrapper's Docker socket.
- `graphify update .`: `graphify` is not installed on this account.

## What is left

- **Merge overlap with GR4a** (`away/GR4a`, whose round 1 merges at 19:30 under D247). Both rounds change the same lines of `apps/pages/scripts/build.mjs` (GR4a adds `packTrendsWords.ts`, GR1a adds `casesWords.ts`; each moves `outfile` to `outdir`), `server/types/glassShared.d.ts`, `routes.yaml`, `pageList.ts` and the route-list pins (HP7/HP9, AP10, the help and AP scenario tests, `test_tree_parity.py`, `test_pages_setting.py`). Whichever merges second takes both entries in each list. Both scenarios go before Scenario S.
- **GR3b:** this page's fixture is hand-written, as GR3a's and GR4a's were. It models the real routes' order and refusals, and it now models withheld datasets. When GR3b lands, its answers should come from the real routes' goldens.
- **The axe gap** of the GOV.UK tree (above).
- **The `RULINGS.md` entry** for these rulings is the conductor's to write.

## Questions for the owner (each is a ruling; none was guessed)

1. **The address.** You ruled `/cases` and `/cases/{case_id}`. Two parts of `apps/pages/server/pages.ts` (ADR-152 decision 6) stand in its way:
   - A page's path is a plain path with no pattern (`PLAIN_PATH`).
   - One page is one `FUNCTIONS.yaml` row in a tree, and a second page with the id `cases-and-views` is refused (`checkTree`).

   **Built: one page at `/cases`, with `/cases?case=<id>` for one case**, as you kept `/packs/trends?case=…&pack=…` for GR4a this
   morning. `process/CLAUDE.md` says to stop rather than build an alternative to an accepted decision; with you away, I followed the
   GR4a precedent and said so in Scenario CS and in `cases.ts`.

   Options:
   - (a) Keep it.
   - (b) Amend ADR-152 decision 6 so a page may own a path pattern such as `/cases/{case_id}`, and so two pages may share a row. This needs a change to `pages.ts`'s registration rule and its tests. GG4a, GA1a and GG3a, which sit under this path, would follow.
   - (c) Your words.
2. **Who made a case.** `created_by` is an account's identifier, not a name, and no route this page may read turns it into one. **Built: the page does not say who made a case** (the draft's table had "who made it"); `created_by` is named as left out in CS. Options:
   - (a) Keep it.
   - (b) Show the identifier.
   - (c) A later part adds a name to the route.
3. **An empty dataset list.** The route sends no dataset to a reader holding no right, deliberately the same empty list whatever the case reads. **Built: "None shown"**, so the page never claims a case reads nothing. Options:
   - (a) Keep it.
   - (b) "None".
   - (c) Your words.
4. **A case's page reads three routes.** The case's own route sends neither the reader's level nor the datasets, so the page reads the case, its brief, then the list. The case is still read once per render, as ruled. Options:
   - (a) Keep it.
   - (b) A later Conduit part adds the level and datasets to the case's read. This part is ruled no Conduit change.
5. **The order.** The page keeps the Conduit's order, newest first, as decision 5 says. The React list puts named cases first. Options:
   - (a) Keep it.
   - (b) The React order, which would need the Conduit to send it.

## Notes for the verifier

- **The fixture** (`test/govuk/casesConduit.ts`) answers in the real order:
  - the router (404/405; any other route of a case is 500, not modelled);
  - then the bearer (401: none is "Not authenticated"; an unknown one gets the resolver's words);
  - then the route-level right (403 `right_required`: `investigate` for the brief; `create_case`/`share_case`/`remove_case` for the writes);
  - then the case's gate (404 `investigation_not_found` for no level, another unit or no such case; 403 for a level too low for a write).

  A successful write is deliberately not modelled (500). It withholds the datasets from a reader holding no right, and leaves out an attachment the reader may not read.
- **The scratch scripts** (`plants.py`, `patch_tests.py`, `patch_py.py`) and the build output are in `~/gr1a-tmp/`, outside the checkout.
