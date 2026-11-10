# Draft: ADR-147 Amendment (number to be reserved): the case's gazetteer panel as built (P6)

For the orchestrator to reserve and append after Amendment 2 (rule 11). Amendment 2's "Left, and why" says
"The Glass has no control for a gazetteer yet"; P6 is that control.

**Decisions.**
1. **Where, and for whom.** The map's controls draw the panel beside the place search ("Gazetteers in this
   case's dataset"). It lists each gazetteer of the case's dataset's unit by name, added or not, and never a
   count. Add and Remove are offered only to a person holding `run_pipelines`; anyone else sees the list and
   a line saying what changing it needs. The Conduit's routes refuse them all the same: the panel hides a
   control and grants nothing (rule 3).
2. **The dataset changed is the case's own,** read from the datasets the case reads
   (`GET /v1/investigations/{id}/datasets`). The GET of the gazetteers gains no field.
3. **The empty list's four reasons are told apart** from those datasets, each in words that name no dataset:
   the case reads none; it reads a composite or more than one; it reads a drawing; or no gazetteer is built
   for its unit (Admin › Maps).
4. **Refusals are said in the Glass's own words,** never the Conduit's text (rule 7). One answer covers a
   404 for an unknown gazetteer and one from the dataset's gate. A removal shows the Conduit's fixed words
   (`REMOVED_WORDS`), which give no count.
5. **A change keeps the keyboard user's place.** The pressed button stays focusable while the copy runs
   (seconds per thousand places, decision 2's measurement); a press meanwhile does nothing. A failed change
   reads the list again, as a copy that failed part way keeps its record.
6. **The place search follows.** An answer shown is asked again after an add or a remove, so it neither lists
   places no longer offered nor leaves out new ones.

**Tests.** `apps/workspace/src/map/gazetteers.test.ts` (the routes, the four empty cases, the words);
`src/map/MapControls.test.tsx` (`CaseGazetteerPanel`: names only, no change without the right, busy and
focus, the re-read, a case change, and `PlaceSearch`'s `asOf`); `keyboard/map-view.spec.ts` (add, the
search asked again, remove, and a panel offering no change, keyboard alone; the registry ids
`add-a-gazetteer-by-keyboard` and `remove-a-gazetteer-by-keyboard`); `a11y/every-harness.spec.ts`
(`map-view-harness.html`'s eight panel states, dark, light and GOV.UK).

**Left.** The places census (`test_place_routes.py`) does not see a client bound in `App.tsx`; a
non-entry route of a place is the orchestrator's carry.
