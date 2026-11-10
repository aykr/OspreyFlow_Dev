# Platform-b lane · brief P5b · backups in a folder the administrator names at setup

Written by the orchestrator, 9 November 2026 (the owner: "platform-b on P5b"), for a **fresh platform-b session on
the default account** (`ayan`). A sister lane of platform (ADR-142 Amendment 4), running beside platform's P5.
Read `spec/06_DECISIONS.md` **ADR-114 Amendment 37** first: it is this step, and its tests are named there. Opus,
medium. Size S.

**The lane, the stacks, the merge rule.** Your files are platform-b's row in `process/BUILD_PLAN_PARALLEL_LANES.md`:
`harness/{backup,restore}.py`, `cli/ospreyflow/{answers,doctor}.py` and the backup and restore dispatch in
`cli/ospreyflow/main.py`, and their tests. Platform's P5 is building beside you, in `cli/ospreyflow/maps.py`,
`harness/geospatial.py` and the map routes: never edit those. The administration guide's §13 is the docs lane's:
write its new text as a carry in your report, not in `docs/**`. Test stacks are on the server only (b to g);
Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator before taking a stack, and
before `make -k ci` or Playwright here. `make test` runs on the server: `stack_lease.sh offline platform-b -- sh -c
'make -k test SKIP_JS=1; cd ../OspreyFlow_Core && make test-js'`. Never call remote or offline while one of your
runs is alive. Prompt L's rules: never stop on a question, except that loosening access, real data, or contradicting
an accepted ADR stops the piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under
`process/lanes/platform-b/gates/`. Report to the orchestrator **by message**.

**Binds.** `process/CLAUDE.md` rules 1–15 (2, 9, 12 and 15 above all; rule 9: a backup holds a deployment's data and
any real-data exception); ADR-114 Amendments 33 and 37; ADR-138 (a deployment's sets never mixed with another's).

**Build** (Amendment 37's decisions 1–6): `folders.backups` read for every profile and asked at install, defaulting
to `~/OspreyFlow/backups`; `server.backups` read as the same setting, both given and differing refused; no backup
ever written inside the checkout (`DEFAULT_BACKUP_ROOT` removed, an `--out-root` inside the checkout refused); a
deployment's sets in `<folder>/<deployment name>/`, restore looking there first and still listing a set in the old
places with the move command; `doctor` naming sets left in the checkout or an old place (size, and the one `mv`),
never moving or deleting one; `doctor` warning about a backups folder a sync client copies (`~/Library/CloudStorage`,
`~/Library/Mobile Documents`, `~/Documents`, `~/Desktop`, OneDrive), a warning, not a refusal.

**Tests first, each red by a plant at its real call site** (rule 15): the ones Amendment 37's table names, at the
paths it gives. Rule 15's second worked example applies: a fake filesystem or runner must refuse what the real
one refuses.

**Exit.** Amendment 37's table green; `make ci` and `make test` green offline (the server); a friction fragment
(one row); the §13 text as a carry. Report in Prompt L's format, then stop.

---

# Platform-b · brief P6 · the case's gazetteer panel beside place search

Folded in from `P6_PLAN.md` (prepared on `prep/platform-b-p6`, accepted by the orchestrator on 10 November 2026; no separate brief). Started from main ec28c67. The orchestrator's additions at the start: the keyboard ids as literals, and axe in three themes.


Step: the case's gazetteer panel beside place search; add and remove a gazetteer (ruling 6), by keyboard.
Exit (build plan row P6): a keyboard case and registry id, red first; axe in three themes.
Spec: ADR-147 Amendments 1 and 2 (on lane/platform until P5 merges; decision 2 there is the API, and its "Left,
and why" names this panel). Start only after P5b merges, rebased onto main with P5 in, from the orchestrator's brief.

## What the Conduit gives (platform's P5)
- GET `/v1/investigations/{id}/map/gazetteers`: Viewer plus `investigate`. `CaseGazetteers{gazetteers:[{dataset_id,
  name, added}], said}` lists the case's own unit's gazetteers. It is empty unless the case reads exactly one source dataset.
- PUT and DELETE `/v1/datasets/{dataset}/gazetteers/{gazetteer}`: `run_pipelines` plus the dataset gate. They are
  synchronous and return `CaseGazetteers`. A gazetteer that isn't there, or is another unit's, gets one 404 with fixed
  words. A composite or drawn dataset is refused. DELETE's `said` is `REMOVED_WORDS`.
- The GET doesn't return the case's dataset id. Use `caseDatasets` (`src/investigation/cases.ts:80`), the one source dataset.

## The Glass (all in apps/workspace/src/map/** and its keyboard/a11y files)
1. `src/map/gazetteers.ts`: `caseGazetteers`, `addGazetteer` and `removeGazetteer`, plain fetch as in `places.ts`. A
   `GazetteersFailed` error says the Conduit's own words for 403, 404 and 409 and never invents a count (rule 2/7).
2. `MapControls.tsx`: a `CaseGazetteerPanel` beside `PlaceSearch`, in its own form and group with the label
   "Gazetteers in this case". Each gazetteer is a row with an "Add"/"Remove <name>" button. The Conduit's
   `said` goes in a `role=status` line. The rows show names only and no counts. It is hidden when the list is
   empty, and the buttons are disabled with a reason when the person lacks `run_pipelines` (`placesByRole.json`).
   The Conduit still refuses, so this loosens nothing (rule 3/4 untouched).
3. `MapView.tsx` gets the props `gazetteers?`. `App.tsx` binds them as it binds `searchPlaces`. After an add or a
   remove, place search runs again.
4. `src/shell/placesByRole.json`: move `add_/remove_dataset_gazetteer_route` from `answered_hidden` to the panel's place.

## Tests, written first and each shown red at its call site (rule 15)
- `keyboard/actionRegistry.ts` gets `MAP_VIEW_ACTIONS` with `add-a-gazetteer-by-keyboard` and
  `remove-a-gazetteer-by-keyboard`. These are red ("registered with no proving test case") until the cases exist.
- `keyboard/map-view.spec.ts`: Tab to the panel and add one with Enter. The harness records the PUT
  (`window.__GAZETTEER_CALLS__`), the row says "added", and place search is offered its places. Then remove it.
  The removal's fixed words are spoken, and the row is back to "Add". Keyboard only, never a click.
- `keyboard/map-view-harness.tsx` gets stubs and the states `?gazetteers=none|one|added|refused`.
  `a11y/every-harness.spec.ts`'s `EXTRA_STATES` gets the same states, so axe runs them in dark, light and GOV.UK.
- vitest: `gazetteers.test.ts` (paths, methods, the Conduit's words on 403/404/409) and
  `MapControls.test.tsx` (the panel lists names only, a status line, disabled without the right).
- The Conduit's access-control tests are P5's (rule 4). P6 adds no route, so `test_route_rights.py` doesn't change.

## Answered by the orchestrator (10 November 2026)
1. The dataset id comes from `caseDatasets`, and the GET gets no new field.
2. A case reading more than one source dataset still shows the panel, which says why in words that name no dataset.
Order: P5b first (after D2a), then P6. P6's code starts after P5 and P5b merge. When P6 starts, this plan is
folded into `lane/platform-b`'s BRIEF; no new brief is coming.

## Checked against P5 as merged (main 984194c, P5 at 1ddbc9a)
- The routes, rights and models are as planned. GET is at `app.py:8180`, PUT at `:9388`, DELETE at `:9433`.
  `_own_dataset` is at `:8141` and `REMOVED_WORDS` at `:8152`. `CaseGazetteer` and `CaseGazetteers` are exported
  from `generated/index.ts:239-240`. `placesByRole.json:95,97,570,572` still lists both routes as answered and hidden.
- The GET's `[]` covers three cases: the case reads nothing; it reads a composite or more than one dataset
  (`chosen_of_case`); or the unit has no gazetteer built. The panel tells them apart with `caseDatasets`. For
  the first two it says why in words that name no dataset. For the third it says none is built for this
  case's dataset yet (Admin › Maps).
- The record is the dataset's (ADR-147 Amendment 2), so an add shows as added in every case reading that dataset.
  The panel's words say "this case's dataset", not "this case".

## As built, where it departs from the plan above (10 November 2026, after the lane review)
- The client gives its own words for every refusal, never the Conduit's (rule 7). Only a removal's fixed
  words are the Conduit's.
- Without `run_pipelines` the buttons are not drawn at all, rather than drawn disabled: a line says what a
  change needs. A disabled button cannot be reached by keyboard to read why.
- The panel is a region headed "Gazetteers in this case's dataset", since the record is the dataset's.
- `placesByRole.json` and the census are unchanged, by the orchestrator's ruling (option 1); the census's
  blind spot is the orchestrator's carry.
- Four empty cases, not three: a drawn dataset is told apart (the Conduit offers it no gazetteer).
- The keyboard cases: add, then the search asked again and the place offered, then remove at once; a
  separate removal from a preset; and a panel offering no change. The registry ids go to the orchestrator as
  `registry-P6.patch`, not on the branch (`actionRegistry.ts` is shared).
- The ADR text is ADR-147 Amendment 4 in `spec/06_DECISIONS.md` (reserved by the orchestrator, written here).
