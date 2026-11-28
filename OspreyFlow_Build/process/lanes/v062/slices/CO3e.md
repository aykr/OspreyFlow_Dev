# Slice CO3e · CO3 · The overdue-days keyboard case waits for the field's focus, and a registry's proved set survives a worker restart

- **Build id:** CO3 (GitHub's keyboard reds; slice id CO3e).
- **Kind:** test-only, on the owner's standing (a) (27 November 2026, about 17:00 UTC).
- **After:** nothing.
- **Status of this brief:** written by the conductor on the owner's word, after reading GitHub's log. **The cause is known. Do not rerun the red GitHub run, and write no stop.**

## What GitHub showed (run 46012575717 on 11ca672, job `glass-perf-a11y-keyboard`)

`11ca672` is records-only. The same job was green on its parent, `9e91748` (run 46001690198). Two cases failed:

1. **`apps/workspace/keyboard/admin.spec.ts:982`**, "when promotions are overdue is set in Operations by keyboard":
   ```
   Locator:  getByLabel('Alert the reviewers and administrators after N days')
   Expected: "4"   Received: "3"
   > 989 |   await expect(days).toHaveValue("4");
   ```
   The case calls `days.focus()` and presses ArrowUp straight away (lines 987 to 988), and the field stayed at 3. It is a focus timing fault in the test (the owner's reading). The case came in with `e22683a`, merged in `0194eec` (8 November).
2. **`admin.spec.ts:1040`**, "every registered Admin action has its own proving test case above":
   - `assertAllCovered` threw at `packages/glass-shared/src/keyboard/actionRegistry.ts:73`, naming 53 of ADMIN_ACTIONS' 57.
   - Those 53 are exactly the first 53 in the file's order, through the failed overdue case.
   - The 4 after it were not named.
   - The covered set is a module-level `Map` in the worker's memory (`actionRegistry.ts:54`). Playwright replaced the worker after the failure, so the set began again empty. **The list could not tell "never proved" from "proved in the worker that was replaced."**
   - Every keyboard spec that calls `assertAllCovered` carries the same weakness, more than 60 files, plus `apps/harness/keyboard/`.

## What

1. **Line 982 waits for focus.** Before ArrowUp, the case waits until the field holds focus (for example `await expect(days).toBeFocused()`). If the field can still be re-rendered by a late read after that, it also waits for that read to land. Change nothing else in the case.
   - **Red first, at its real shape (rule 15).** Plant the timing in the test's own harness, never in product code. One way: delay the harness's answer, or the field's mount, so that focus or the value lands after today's ArrowUp. Show today's line 982 red with "Expected: 4, Received: 3". Then show it green with your wait, under the same plant.
   - The plant must not stay in the suite as a permanent slowdown. Keep it as a switch the proof test sets (an environment variable, or a route delay in a test of its own), and name the switch in your report.
   - **If a focus wait alone does not make it green under the plant, stop and report the cause you found.** Do not widen the change.
2. **The proved set survives a worker restart.** `registerCovered` and `assertAllCovered` keep the proved set outside the worker's memory: for example, one file per proved id, or an append-only file, in a folder made fresh for each run and shared by its workers. Then a replaced worker's proofs still count.
   - **No stale proof.** A folder left by an earlier run must never count, or a real untested action would hide behind it (rule 15). Say how a run gets its own folder.
   - **Keep glass-shared plain.** `packages/glass-shared` is imported by the browser bundle, so it must gain no Node import that reaches the bundle. If the store needs `fs`, put it in a test-side module the specs import, and keep the registry's declarations where they are. Say which you chose.
   - **All specs and the harness move together.** Every `registerCovered` and `assertAllCovered` caller, including `apps/harness/keyboard/`, uses the new store, and `registryCoverage.test.ts`'s static scan still reads them.
   - **Red first, both ways:**
     - (a) **A worker restart.** Today's code goes red and the new code green. For example, a small Playwright run in a subprocess with a case that fails before others prove their ids, then the list. Today's list names ids that were proved; the new list names none.
     - (b) **A really untested action.** One registered id with no proving case is still named, under the new store. That is the list's own red, shown at its real call shape, not a hand-written string.
3. **Not in scope:**
   - any product code under `apps/workspace/src` or `packages/glass-shared/src` other than the registry's covered-set store;
   - any other keyboard case;
   - the CI workflow, the Makefile and any CLAUDE.md.

Binding: process/CLAUDE.md rules 12, 13 and 15; British English. You do not edit `.github/`, the Makefile or any CLAUDE.md.

## Acceptance test

`OspreyFlow_Core/apps/workspace/keyboard/registryRestart.test.ts` (Vitest, under `keyboard/**/*.test.ts`). It holds proofs 2(a) and 2(b), and it is red on main. Name the test that holds proof 1, the plant at line 982, in your report. It may sit beside the acceptance test or in its own file.

## Checks

- The workspace's unit tests: `keyboard/registryCoverage.test.ts` and the new test.
- `keyboard/admin.spec.ts` under `test:keyboard`, three runs in a row, all green.
- The harness's keyboard registry test.
- The workspace and glass-shared typecheck and lint.
- `no_react_check`.

The full keyboard suite runs in the merge's full gate. **Before your final report, run by hand the cheap checks the conductor will run again before the merge.**

## The owner's answer to round 2's question (28 November 2026, about 06:05 UTC; RULINGS.md, item 4)

**(B): CO3e lands as (A) now.** The product fault is a separate part, CO3f, which merges after CO3e. Do not fix the product here.

1. **Item 1, as (A).** `admin.spec.ts:982`, "when promotions are overdue", waits for two things before ArrowUp:
   - the field's focus;
   - the second ageing read to land: its `operations/ageing` answer after `/v1/me` has answered, as your round 2 measured.
   Change nothing else in the case. Prove it with your plant switch:
   - with `OSPREY_PLANT_LATE_AGEING=1`, the case as it was is red;
   - with both waits added, it is green 10 of 10;
   - with the plant off, it is green 10 of 10.
   Give the commands and the counts in your report.
2. **The plant stays.** `keyboard/lateAgeingPlant.ts` is off by default. CO3f uses it as its proof, so name its switch and what it holds back in your report.
3. **Item 2 is done.** It is your round 1 and 2 commits; leave it as it is.
4. Your round 2 note about the small gap (the wait sees the answer arrive, not the redraw) goes in your report. CO3f closes it.
