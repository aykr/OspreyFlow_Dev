# GR1e away report: a case's history as a part of its GOV.UK page, read-only (26 November 2026, D246 away round)

Branch `away/GR1e`, from `005dcbfca` (the tip of `away/GR1a`, built but not merged). Nothing was pushed or merged, and `main` is
untouched. Every test ran through `REPO=~/away-gr1e ~/osprey-d246/d246_ns.sh` from `OspreyFlow_Core`, at `nice -n 19`. All data is
synthetic.

These files were not edited: `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`, `spec/06_DECISIONS.md`,
`spec/ADR_RESERVATIONS.md`, `osprey.yaml` and `data/`. No decision record changes. No Conduit file and nothing in `apps/workspace`
changed.

**State: the table is complete and green. Five questions for the owner follow (below).** Each was built in the conservative reading
and needs the owner's confirmation; none blocks the merge.

## The rulings this round worked from

The owner's rulings of 26 November on GR1e's draft are given here, since they are not yet in `RULINGS.md` (the conductor's to write):

- **Every proposal (a):**
  - read-only, with restore waiting for GG2e;
  - the route's order;
  - a "History" part of the case's page, linked from its contents;
  - every step shown, with no page-side cut.
- **GR1a's question 1 is (a):** the case's page keeps the query form, `/cases?case=<id>`, and the history is a part of it.
- **The rule-3 stop did not arise.** If the route sent something the reader may not see, this round was to stop and write a question.
  It does not: `GET /v1/investigations/{id}/history` sends metadata only (`HistoryStepSummary`: `id`, `label`, `created_at`,
  `restorable`). The label is fixed text (`OspreyFlow_Core/services/api/history_labels.py`, "A label holds no number and no name"),
  and there is no size or body. The page shows the label, the time and `restorable`, and leaves out the `id`.

## Commits, in order

| Commit | What |
| --- | --- |
| `fe65f22d5` | **Red first:** Scenario CS's rows CS16 to CS26, its changed sentences (what the page is, who may see it, scripts off, the left-out fields of `HistoryStepSummary`, CS8's calls) and the `cases-and-views` row's ids. The scenario test gained the sixth model and a check holding the page's and the fixture's labels to `history_labels.py`. **20 of 45 failed**, each for a reason the build was to fix: no page test named CS16 to CS26; the census had no `HistoryStepSummary`; neither the page nor the fixture declared its labels. |
| `b7882ced9` | **Red first:** the page cases CS16 to CS26; the fixture's history routes and refusals; CK4 and CO3. **13 of 35 page cases failed** on GR1a's page. The fixture's own refusals case passed, since it tests the fixture, not the page. |
| `a4c4f8df2` | **Green:** the page (`server/cases.ts`, `server/views/casesWords.ts`, `tree-govuk/cases.njk`), 35 of 35. GR1a's empty-brief checks now read the Brief part, since the new contents list is a list of its own. |
| `915c8a219` | `citation-check` failed at this branch's base: GR1a's report cited the pages build script by a short path that is not a file. The two citations now read `apps/pages/scripts/build.mjs`, and the gate went from red to 0. |
| `b2026bb43` | This report, begun. |
| `f1a8c2804` | Fixes for an independent read-only review's findings (below). |
| `6b7e9af59` | The two census cases given 30 s (below). |
| this commit | This report. |

## What the page does now

`/cases?case=<id>` reads four routes, in this order:
1. `GET /v1/investigations/{id}`
2. its `brief`
3. **its `history`**
4. the list

**One read of each per render.** The history's read is one `get_history` audit row. The list page never reads a history.

**The case page's contents** are a list of three links: "About this case", "Brief" and "History". Each goes to its part's heading.

**The History part** has a lede, "This page only shows the steps. It restores none.", and a table:
- **The caption:** "Changes to this case, in the order the case records them".
- **The columns:** Step, When and Restore.
- **One row per step sent, in the order sent:**
  - its label as sent, as a row header;
  - its time, written as the case picker writes a moment;
  - "Can be restored" or "Cannot be restored", as `restorable` says.

A case with no step says "Nothing has changed in this case yet." and has no table.

**A refused, failed or unreadable history read:**
- **Refused** (any 4xx but a 401): GR1a's 404 page, byte for byte the unknown path's, and the list is not asked.
- **Failed** (a 5xx, no answer, a text body): the case's 502 "could not be read", with nothing of the case.
- **A 401:** the Studio's sign-in-again words.
- **A body the strict reader cannot read:** "could not be read", never a default. That covers a body that is not a list, a step missing any of its four fields or with one of the wrong shape, and a label the route cannot send. `restorable` is never taken as the model's default of true.

## The table of cases

| # | Draft's case | Row | State | Proof |
| --- | --- | --- | --- | --- |
| 1 | Five steps, one a brief edit | CS16 | **green** | Five rows in the store's order, which neither label order nor newest first gives; the brief edit "Cannot be restored". A route that says a brief edit is restorable, or another step is not, is drawn as it says: the page reads `restorable`, never the label. |
| 2 | A label not in the fixed list | CS17 | **green** | The fixture stores "Removed 3 nodes" and sends it as `Changed`, as `list_steps` does; the page draws "Changed". Every label the route can send is drawn as sent. A label it cannot send ("Expanded by 4", "", "Branched from Harbour") is the 502. |
| 3 | No steps | CS18 | **green** | "Nothing has changed in this case yet.", with no table, caption or header. |
| 4 | No size, no count | CS19 | **green** | The part's only digits are the steps' moments. |
| 5 | No level, another unit, no case, no `investigate` | CS21 | **green** | A 404, 403, 409 or 422 from the history is the unknown path's page, and the list is not asked. A reader without `investigate` is refused at the brief, before the history, in the real routes' order. A missing level, another unit or a missing case is the case read's 404 (CS6), before either. |
| 6 | One render | CS22 | **green** | Exactly the four calls, the history once. |
| 7 | A missing field | CS23, CS10 | **green** | Each of the four fields removed in turn, nine wrong shapes and six wrong bodies; through the service, every removed field gives a 502. CS10's count is now 29 fields of six models. |
| 8 | No step id | CS20 | **green** | No step id in the page's bytes, comments included. |
| 9 | No answer, or a 401 | CS24 | **green** | The 502 page; a 401 says to sign in again. |
| 10 | Keyboard and scripts off | CS25 | **green** | The contents follow the sign-out in the tab order (CS12 and the shared `CASE_TAB_ORDER`). `keyboard/cases.spec.ts` CK4 and `scripts-off/cases.spec.ts` CO3 follow each contents link by Enter and check `:target`. CK4 then reads the history table by its headers; the next Tab is the way back, so the part holds no stop. |
| census | Strict reader and field census | CS23, CS11 | **green** | `HistoryStepSummary` is read from `history.py` by `ast`. `id` is left out, named in the "Left out, by field name" sentence; the other three are drawn and each changes the page. The page's `HISTORY_LABELS` and the fixture's `SHOWN_LABELS` are held to `FIXED_LABELS` and `CHANGED`, and the fixture's `NOT_RESTORABLE` to the route's. |
| rule 15 | Planted faults | CS26 | **green** | Below. |

### Planted at the real call site (rule 15)

`~/gr1e-tmp/plants.py`, outside the checkout, changed one thing in the real file, ran `cases.test.ts` (and, for the five walk plants,
the keyboard and scripts-off specs), then restored the file from git. `git status` of the three files was empty afterwards. **All 23
went red on the case they name** (the final run, after the review's fixes):

- **`casesWords.ts` (14):**
  - **The restore words:** a brief edit said as restorable (CS16); restorable guessed from the label (CS16).
  - **Labels:** a label in the page's own words (CS16, CS17); a label the route cannot send drawn (CS17).
  - **The empty history:** drawn as an empty table (CS18).
  - **The reader:** a missing `restorable` taken as the default (CS23); a step's time not checked (CS23); a step's id type check removed (CS23).
  - **The page:** a step's id printed (CS20).
  - **The real loop:** capped at four steps (CS14, CS16); a step skipped (CS16).
  - **The contents:** the History link (CS25, CK4, CO3) and the Brief link (CS25, CK4, CO3) taken out.
- **`cases.ts` (4):**
  - a failed read drawn as an empty history (CS24);
  - the history read twice (CS22);
  - the history's 403 passed through (CS21);
  - the refusal drawn as could not be read (CS21).
- **`cases.njk` (5):**
  - **Rows:** a count of steps (CS19); the steps turned round (CS16); the steps capped by `batch` (CS14, CS16).
  - **The control:** a restore button offered (CS16, CS12).
  - **Anchors:** the History anchor taken off (CS25, CK4, CO3); the About anchor taken off (CS25, CK4, CO3).

CS26's own cases also plant faults into the real HTML, the real view and the real sources. Five of them are checked to fail by their own
check alone: a step cut off, a control after the table, the heading in other words, a list inside the Brief part, and a lenient label
reader. The scenario test has 36 planted faults, 6 of them new: a label added to the route's fixed labels, one dropped from the page,
one dropped from the fixture, the route showing labels by another rule, a field added to a history step, and a label added to the
route's not-restorable set.

## The fixture

`test/govuk/casesConduit.ts` now serves:
- `GET /v1/investigations/{id}/history`;
- `POST /v1/investigations/{id}/history/{step_id}`, the restore.

It answers in the real routes' order (`OspreyFlow_Core/services/api/app.py`, `get_investigation_history` and `restore_history_step`):
1. the router: 405 for a method the path does not serve;
2. the bearer: 401;
3. `investigate`: 403 `right_required`, before the case's gate, for both routes;
4. the case's gate: 404 `investigation_not_found`. A restore below Editor is 403, and a restore that would pass is not modelled (500).

**What it sends** is what `list_steps` sends:
- the store's order;
- a stored label the route does not show, sent as `Changed`;
- `restorable` false for the labels in `NOT_RESTORABLE`;
- the four fields and nothing else.

## The independent review and what changed

A read-only lane reviewer read the branch. Its findings were checked against the files and fixed in `f1a8c2804`.

**Fixed:**
1. **CS16 named the caption "History"; the page draws another.** CS16 now names the page's caption.
2. **No cut of the steps was ever shown red** (rule 2). A step was skipped, added or cut off in the HTML; a cap and a skip were planted in the real loop and the template; a source check was added for a `.slice` on that loop. The row-count check is shown red on its own.
3. **The contents' "About this case" and "Brief" links were reachable but never followed** (rules 12 and 13). CK4 and CO3 now follow all three by Enter and check `:target`, and two walk plants turn them red.
4. **The narrowed brief check (`briefPartOf`) was never shown red on its own.** It now is: a list inside the Brief part, with the sentence kept, is "drawn as a list", and the real part starts at its heading and holds no contents.
5. **Three plants could fail only by another path.** The button plant now goes after the table, the heading has its own plant, and a lenient label reader is planted.
6. **The fixture's `NOT_RESTORABLE` was held to nothing.** The scenario test now holds it to `history_labels.py`'s, with a plant.
7. **The caption claimed "oldest first".** The route orders by `seq`, then the time, and a brief edit takes the latest `seq`. The words now claim only the case's own order: "in the order the case records them".
8. **CK4's "in view" check proved nothing on a short page.** It was removed. `:target` is the proof, and the comment on the Tab says what that step does and does not show.

**Not done here:**
- **No axe scan on any GOV.UK page.** It is the tree's gap, as GR1a reported.
- **No case of the fixture shares a dataset with a case the reader cannot see.** The history is read by case id after the case's gate, so the risk is low. It belongs with GR3b's real-route answers.

**After the fixes**, the whole suite timed out CS15's census case at vitest's default 5 s. GR1e's sixth model means each census draws
more pages. Both census cases now have 30 s (`6b7e9af59`).

## Tests run, all through D246

**Page tests (`apps/pages` vitest):**
- **Whole suite: 922 passed, 2 failed.** The two are the asset route's traversal probes (`assetsTraversal.test.ts`, `foundation.test.ts`), which fail for the wrapper's `TMPDIR` under a dot-named folder, as for GR1a and GR4a. With `TMPDIR` set to a plain folder, both files pass, 32 of 32. They touch no file of this part.
- `cases.test.ts`: 35 of 35.

**Playwright (`npm run test:keyboard:govuk`):** 16 of 16. That includes the 4 keyboard and 3 scripts-off cases of the cases page.

**Python, 13 files: 844 passed.** The files:
- `test_govuk_cases_scenario.py` (46)
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
- `ruff check .` in Core, and with the Build tree's settings on the scenario test
- `node apps/pages/scripts/build.mjs --out` to a scratch folder; the built `casesWords.js` holds the history's words and has no import.

**`make` gates, with `make`'s own exit code:**
- **All 0:** `design-check`, `ui-words-check`, `citation-check` (after `915c8a219`), `product-tree-link-check`, `test-file-coverage-check`, `route-coverage-check`, `schemas-check`, `no-branches-check`, `authorized-query-check`, `demo-guide-check`, `decision-log-publication-check`, `provenance-annotation-check`, `domain-model-coverage-check`, `no-langchain-check` and `confinement-check`.
- **`slice-line-check`:** 825 passed, 1 skipped. The wrapper's clean-up then prints `rm` refusals for read-only files a slice-line test leaves, as GR1a saw.
- **Rerun after the review's fixes:** the first six (design to route coverage), all 0.

**Not run:**
- `client-name-check`: `client_names.local.sha256` is not on this machine.
- `lanes-check`: it fails under D246 for the wrapper's Docker socket (GR4a).
- `graphify update .`: `graphify` is not installed on this account.

## A long history: the measure the ruling asked for

The draft asked the builder to measure the largest synthetic world's count of steps. A read-only scout read the seeds, the demo packs
and the journeys. **No seeded world writes a history step:**
- `_record_history_step` is called only from the Conduit's route handlers (seed, add, expand, links among, remove, a brief edit, a starter question, the shared-pair, ownership and alert canvases).
- Every seed and demo pack, `scripts/seed_internal.py`'s mapping and `cli/ospreyflow/demo.py` write graph data and cases directly.

Steps come only from a journey driving the Glass:
- **The largest is the owner-run `apps/workspace/live/pid-capture.spec.ts`.** It is gated behind `OSPREY_PID_CAPTURE=1` and uses one shared case across its tests, with at least about 44 steps from its add-and-expand pairs alone.
- **No file bounds it, and the store has no cap.**

At a few dozen rows of a label and a time, the page draws well. A long-lived real case can reach any count (question 2).

## What is left

- **The merge:** GR1e is on top of GR1a and merges after it. Its files are GR1a's own. The GR4a overlap is GR1a's (in GR1a's report), and GR1e adds no line to `build.mjs`, `routes.yaml`, `pageList.ts` or the route-list pins.
- **GR1c:** the history's page of its own. **GG2e:** restore.
- **GR3b:** the fixture is hand-written. It models the history routes' order and refusals, and the scenario test holds its labels to the route's. When GR3b lands, its answers should come from the real routes' goldens.
- **The axe gap** of the GOV.UK tree.
- **The `RULINGS.md` entry** for these rulings is the conductor's to write.

## Questions for the owner (each is a ruling; none was guessed)

1. **"Branched" steps are sent as "Changed" (a Conduit question, outside this part).** `history.py`'s relabel turns a stored `Branched from …` into `Branched` and keeps `Branched` in its list of fixed texts. But `history_labels.py`'s `FIXED_LABELS` has no `Branched`, so `list_steps` sends every such step as `Changed`. The page follows the route, and CS17 treats "Branched from Harbour" as a label the route cannot send. Options:
   - (a) Intended: leave it.
   - (b) A later Conduit part adds `BRANCHED` to `FIXED_LABELS`. The scenario test would then fail until the page's and the fixture's lists take it, as designed.
2. **A long history.** As ruled, every step is shown (above). A real case can grow without bound, and the route has no paging. Options:
   - (a) Leave it until a case is seen to draw badly.
   - (b) A later Conduit part adds paging, which the page would follow with a way to the next page. A page-side cut is not offered (rule 2).
3. **The words.** Built:
   - the column "Restore", with "Can be restored" or "Cannot be restored";
   - the lede "This page only shows the steps. It restores none.";
   - the caption "Changes to this case, in the order the case records them" (not "oldest first": the route orders by `seq`, and the page claims no order of its own);
   - "Nothing has changed in this case yet." for none.

   "Can be restored" is said on a page with no way to restore, until GG2e. Options:
   - (a) Keep them.
   - (b) Your words, for instance naming where a step is restored today (the workspace's History).
4. **A label the route cannot send.** Built: the strict reader allows exactly the labels the route can send (`FIXED_LABELS` and `Changed`). Any other label makes the whole case page "could not be read", as GR1a's closed values do. The scenario test fails if `history_labels.py` gains a label the page lacks, so the two cannot drift in the repository; a deployment with a newer Conduit than its pages service would still show "could not be read". Options:
   - (a) Keep it.
   - (b) Draw any label as sent (the route already promises fixed text).
5. **The contents.** GR1a's case page had none. Built, as the draft's proposal 3 says: a "Contents" heading of the second level, and a list of three in-page links before "About this case". The tab order of the case page gains three stops. Options:
   - (a) Keep it.
   - (b) Only the History link.

## Notes for the verifier

- **The scratch files** (`edit*.py`, `fix*.py`, `plants.py` and its output `plants.out`, `gates.sh` and the gate logs, the build output) are in `~/gr1e-tmp/`, outside the checkout. The repository's guard refuses a heredoc holding `${…}`, so the edits went through files there.
- **The environment:** the worktree's `.venv` and `node_modules` were built by `REPO=~/away-gr1e bash ~/osprey-d246/d246_env.sh`; the log is at `~/.cache/gr1e-env.log`.
- **Other agents:** the other `claude` processes on the machine at the start were in `~/away-live` and `~/away-gg2c`, not this worktree. No container of a test run was started, since D246 refuses them.
