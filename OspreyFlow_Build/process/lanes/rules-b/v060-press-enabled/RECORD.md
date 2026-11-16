# v0.6.0: promotions.spec's lost Close press (rules-b, 16 November 2026)

**The failure.** CI run 43813698501 (0c158b8), glass-perf-a11y-keyboard: `promotions.spec.ts:69`, "a removed
case's layer is merged through its sheet by keyboard", failed at `press(page, "Close")` (line 84). The error was
`expect(locator).toBeFocused()`, `Received: inactive`, with the button resolved 14 times as
`<button type="button" class="btn board__button">Close</button>`. `:122`'s registry check failed after it.

**Why.** The Close button was enabled: "inactive" is Playwright's word for an element that is not focused, and this
Close has no `disabled` at all (`src/ingest/runs/promotions.tsx:459`). The focus was taken from it:
- the merge sheet moves focus onto its outcome's heading once the merge is answered (`promotions.tsx:309-312`,
  "onto its outcome once sent");
- that move is an effect run after the outcome is drawn, from an answered request;
- so the test can see "Merge sent" and focus Close before the effect runs, and the effect then moves focus to the
  heading. `press()` focuses once, so the check never sees Close focused again.

af5d2cb's fix in `ingest-studio.spec.ts` (wait for the button to be enabled) does not catch this alone.

**The fix** (`keyboard/promotions.spec.ts`, test only):
1. Before pressing Close, wait for the move: `await expect(page.getByRole("heading", { name: "Merge sent" })).toBeFocused()`.
   This is the component's own stated behaviour, so the test now also proves it.
2. `press()` waits for `toBeEnabled()` before focusing, as af5d2cb does.

No assertion is removed or weakened. The file's other presses that follow an answered request already wait for the
heading the answer focuses (the review dialog's and the merge sheet's headings).

## Proof
- **The stand-in** (`proof.spec.ts.txt`, run from `keyboard/` and then removed): the sheet's move onto "Merge sent"
  is held from the moment that heading is drawn, and lands on the next focus anywhere else, as on CI.
- **OLD**, CI's own flow (press Close as soon as "Merge sent" shows): it fails with CI's own "inactive" in 30 of 30.
  The case asserts that failure.
- **NEW**, the fixed flow: Close is pressed and the sheet closes, 30 of 30.
- 60 passed at `--repeat-each 30 --workers 8` (`proof.txt`).
- **promotions.spec.ts at `--repeat-each 10 --workers 8`:** 90 passed (`promotions-x10.txt`).
- **The whole keyboard suite** at 3256d67, `--workers 8`: 1365 passed, 5 skipped, none failed (`whole-suite.txt`).

Playwright slot 9 (rules-b's), with the owner's yes for this run.
