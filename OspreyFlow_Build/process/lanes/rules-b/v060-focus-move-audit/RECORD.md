# v0.6.0: the keyboard specs' focus-move audit (rules-b, 16 November 2026)

**What was looked for.** promotions.spec's lost Close press (`../v060-press-enabled/RECORD.md`) had this shape:
- a component moves focus in a `useEffect` whose state is set after an awaited request;
- React runs that effect after the answer is drawn;
- a spec that waits only for the answer's text, then focuses or presses another control, can lose that focus to
  the late move ("Received: inactive").

The audit covered every `.focus()` in `src/` (48 files, 37 in effects) and the keyboard specs whose harness draws
each one. A read-only pass listed them; rules-b checked each at-risk item against the code before fixing it.

**Not at risk:**
- **The spec waits for the moved focus first:**
  - promotions (details; the sheet opening);
  - drawnMerge (opening; "Merge sent");
  - PromoteSheet (`boards.spec.ts`);
  - ModelProposals;
  - CaseBrief (every change);
  - ViewLensBanner (`view-over-cap.spec.ts`).
- **Nothing is pressed after the move:**
  - `Datasets.tsx` DeletedWords (`admin.spec.ts`);
  - LinkNotes, whose harness never fires the effect.
- **The effect is a `useLayoutEffect`, so focus moves before paint:** DocumentReader, RadialMenu.
- **The move comes from a synchronous event, a prop or a mount, which React flushes before the next event:** the
  rest. The audit pass lists them; rules-b did not re-check each.

**At risk, and fixed here** (`keyboard/drawn-merge.spec.ts`, test only):
- Each "goes in as" or "goes into" choice reads Match again (`drawnMerge.tsx` `choose`/`place` → `rematch`, which
  sets `sheet` after its await). The `[sheet, sent]` effect then moves focus onto the sheet's heading.
- The spec then focused `flag` (after the Vessel choice) and pressed **Dry run** (after the flag choice) without
  waiting.
- Each now waits for the heading's focus first. No assertion is removed or weakened.

The third at-risk item, promotions.spec's Close, is fixed on lane/rules-b-v060-press-enabled.

**Outside the asked scope, not audited:** `BoardEditor.tsx:140-145` `focusItem` moves focus by
`requestAnimationFrame` after reloads. It is not an effect, so it was not audited here, but it has the same
after-paint shape.

## Proof (slot 9)
- **The stand-in** (`proof.spec.ts.txt`, run from `keyboard/` and then removed):
  - armed just before a choice, it holds the sheet's next move onto its heading while focus is still on the
    changed select;
  - the move lands on the next focus anywhere else, as on CI.
  - The OLD flow at each spot (:92, :96) is red with "inactive" in 30 of 30. The NEW flow is green in 30 of 30.
  - 120 passed at `--repeat-each 30 --workers 8` (`proof.txt`).
- **drawn-merge.spec.ts at `--repeat-each 10 --workers 8`:** 60 passed (`drawn-merge-x10.txt`).
- **The whole keyboard suite, `--workers 8`:** 1365 passed, 5 skipped, none failed (`whole-suite.txt`).

## A product question the audit raised (not changed here)
`drawnMerge.tsx`'s `[sheet, sent]` effect moves focus onto the sheet's heading on every Match re-read. A keyboard
user who changes a "goes in as" or "goes into" select is taken from the select to the heading after each choice,
and must Tab back to the next control. The fix would be to move focus only when the sheet is first drawn and when it
is sent, not on a re-read. It is a Glass change, for the sheet's owner: `CARRIES.md`.
