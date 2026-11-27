# Slice CO3c · CO3 · A keyboard spec waits for its first control before its first key press

- **Build id:** CO3 (GitHub's keyboard reds; slice id CO3c).
- **Kind:** test-only, on the owner's standing (a). The owner's ruling of 27 November 2026, about 11:15 UTC (RULINGS.md, item 1).
- **After:** nothing.
  - **CO3e also edits keyboard specs**, to move every `registerCovered` caller onto its new store. Touch only the lines between a case's `page.goto(...)` and its first key press. Whichever of the two merges second takes main in under rule 5.
- **Status of this brief:** written by the conductor on the owner's word. **The cause is known. Do not rerun the red GitHub runs, and write no stop.**

## What GitHub showed

`OspreyFlow_Core/apps/workspace/keyboard/rule-standards.spec.ts:21`, "Show as BPMN is reached by Tab…", fails on GitHub's runner.
- It presses Tab straight after `page.goto(...)` (lines 23 to 28), before the React harness has drawn its button. When the harness is slow, the Tab lands on the page, and "Show as BPMN" is not focused.
- Its sibling at `:85`, "every registered … action has its own proving test case", then fails only because `:21` never recorded its proof. CO3e deals with that list's weakness. Do not touch it here.
- `account-unread.spec.ts`, "Sign out is reached by keyboard with no account read" (about line 35), has the same shape: `page.goto(HARNESS)`, then `Tab` at once.

## What

1. **Before its first key press, each keyboard case that starts with `page.goto(...)` waits until the control it is about to reach is visible.** For example, `await expect(button).toBeVisible()`, or the harness's own ready mark if it has one. That covers these two specs, and every spec of the same shape under `apps/workspace/keyboard/` and `apps/harness/keyboard/` that you find by reading.
   - List each site in your report: the file, the line, and what it now waits for.
   - Change nothing else in a case.
2. **A standing guard, red first (rule 15).** Write `OspreyFlow_Core/apps/workspace/keyboard/firstKeyWaits.test.ts`, a Vitest test that reads the keyboard spec files as text. It fails when a case's first `page.keyboard.press(` after its `page.goto(` comes with no `await expect(…)` between them.
   - **It must be red on main, naming the sites it finds**, rule-standards.spec.ts:21's at least, and green after your fix.
   - **Plant at the real shape:** remove the wait you added at `rule-standards.spec.ts:21` and show the guard name that line.
   - Any allowed exception is listed with its reason. Say in your report which folders it walks: the conductor writes its scan-map row.
3. **The load proof.** Run `rule-standards.spec.ts` and `account-unread.spec.ts` 20 times each (`--repeat-each=20`) under CPU load, and report the command and the load you used. Under the same load, with the wait removed, show red at least once, or say plainly that the load could not make it red.
4. **Not in scope:**
   - product code;
   - the action registry and its list cases (CO3e);
   - the CI workflow, the Makefile and any CLAUDE.md.

Binding: process/CLAUDE.md rules 12, 13 and 15; British English.

## Acceptance test

`OspreyFlow_Core/apps/workspace/keyboard/firstKeyWaits.test.ts` (Vitest, under `keyboard/**/*.test.ts`), red on main.

## Checks

- The workspace's and the harness's unit tests.
- `rule-standards.spec.ts` and `account-unread.spec.ts` under `test:keyboard`, three runs each.
- Lint, typecheck and `no_react_check`.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**
