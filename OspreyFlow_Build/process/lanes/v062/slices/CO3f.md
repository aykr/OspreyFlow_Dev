# Slice CO3f · CO3 · A late read in Admin never overwrites an administrator's edit: a stable api, and every section checked

- **Build id:** CO3 (GitHub's keyboard reds; slice id CO3f).
- **Kind:** a product fix. The owner's ruling of 28 November 2026, about 06:05 UTC (RULINGS.md, item 4, option (B)). It is the separate part that follows CO3e.
- **After:** CO3e. Its plant, `apps/workspace/keyboard/lateAgeingPlant.ts`, is this part's proof.
- **Status of this brief:** written by the conductor on the owner's word, from CO3e's round 2 report. Re-read every line it cites before you change anything.

## The fault (CO3e's round 2, measured)

- **Two reads on one open:** the Admin page reads `operations/ageing` when it opens, and again when `/v1/me` answers.
  - `apps/workspace/src/admin/AdminPlace.tsx` makes a new `api` object on every render; its `SCREENS` map is at about line 56.
  - `sections/Operations.tsx` (about line 19) re-reads whenever `api` changes.
- **Each answer resets the field to the server's value.** If the second one lands after the administrator has changed it, the edit is lost, and Save then sends the old value.
- **The proof:** with `OSPREY_PLANT_LATE_AGEING=1` (CO3e's plant), the second answer is held until just after ArrowUp, and `admin.spec.ts:982` reads 3 where it expects 4.

## What

1. **A stable `api`.** `AdminPlace` gives its sections the same `api` object across renders, for example made once with `useMemo` on what it really depends on. A section's read then runs once per open, not again on a render that changes nothing.
2. **A late read never overwrites an edit.** In `Operations`, once the administrator has changed a field, an answer that lands afterwards does not replace the value they typed.
   - The page may tell them, in words, that the saved value differs; it never silently swaps the value.
   - Save sends what is on the screen.
3. **Every other Admin section, checked for the same shape** (an editable field filled from a read that `api` or a render can repeat), under `src/admin/sections/` and `src/admin/` (People, Roles, Grading scheme, Dashboards, Datasets, Connections, System, Models, Schedules and the rest).
   - List each section in your report: the shape found or not, and the file and line.
   - Fix each one found the same way, each with its own test.
4. **Red first (rules 12 and 15), at the real shape.**
   - **The acceptance test:** a Vitest test, `apps/workspace/src/admin/lateRead.test.tsx`. It renders `AdminPlace` with a fake api whose `operations/ageing` answers twice, the second time after the field has been changed. It asserts:
     - the typed value is kept;
     - the read ran once.
     It must be red on main, then green.
   - **The keyboard proof:** `admin.spec.ts` under the plant is green 10 of 10 with CO3e's waits removed from the case at `:982`. Do not commit that removal; it is a temporary edit for the proof. Give the commands and counts.
5. **Not in scope:**
   - the Conduit;
   - the keyboard registry;
   - CO3e's waits, which stay;
   - the CI workflow and any CLAUDE.md.

**Access control:** no read path changes. Each section keeps its own rule-4 tests; say so for any section you touch.

Binding: process/CLAUDE.md rules 4, 12, 13 and 15; British English.

## Acceptance test

`OspreyFlow_Core/apps/workspace/src/admin/lateRead.test.tsx`, red on main.

## Checks

- The workspace's and glass-shared's unit tests.
- `admin.spec.ts` under `test:keyboard`, three runs.
- Lint, typecheck and `no_react_check`.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**
