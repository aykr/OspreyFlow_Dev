# Case lane · L3.3 (drawing boards) · report, 8 November 2026

**Exit, each with its proof (each red by a plant at its call site: `L3.3_RED_RECORD.md`):**
- **1 Boards:** declare, link by handle, Alt-drag, right-click and form; move; marking, grading and source (a note, a document, or both) on every drawn item; an icon; *Same* merges nothing (rule 6); pictures uploaded or chosen, in the layer. `test_boards.py` (36); `keyboard/boards.spec.ts`: 26 keyboard cases (`BOARD_ACTIONS`, 24 ids, in `registry-L3.3.patch`) and 4 pointer cases.
- **2 A drawing with no case:** its dataset, home case and board; its items go to the drawn dataset. `test_a_drawing_with_no_case_makes_its_dataset_case_and_board`.
- **3 Watch:** drawing sets it, withdrawing ends it, and it is withheld whole from a reader who may not see the item. `test_drawing_sets_a_watch_and_withdrawing_ends_it`, `test_a_watch_on_an_item_the_reader_may_not_see_is_withheld_whole`. Its queue case is L3.6's.
- **4 Ceiling:** refused in words naming it. `test_an_item_above_the_ceiling_is_refused_in_words`.
- **5 Restore:** `test_a_drawn_item_and_its_picture_come_back_in_their_cases_layer` (live).
- **Rule 3/4:** 16 routes refuse another case's member as a missing case. A drawn item is never readable outside its case: red with K's layer in B's read set; red on real Postgres with the case clause made true.
- **Axe:** dark, light and GOV.UK: GATES_AXE.
- **Gates:** GATES_LINE. **Live:** LIVE_LINE.

**Lane review:** REVIEW_LINE

**Decisions taken** (the owner may overrule each):
- Only a board's creator draws on it; others read a shared board.
- A match is suggested at a score of 0.75 or more.
- Grading is 5x5x5 until L3.7 makes it a deployment setting.
- The type's required properties are on the form, a required name filled from the label until changed.
- An edit is made in place. A marking is never lowered, and a drawn link's marking is never changed.
- Watches live in `drawn_watches`, with no expiry yet (for L2.10 and L3.6).
- A duplicate drawn link is refused.
- A picture's Document id is the layer's own.
- The documents offered as a source or picture are those on the board, since no route lists a case's documents.
- The restore test runs on a throwaway database.
- **Open question 4** (moving versus linking): built as C7 says (drag moves; the handle, Alt-drag or the menu links), for one field analyst's check.

**Commits:** `git log main..lane/case`.
**For the orchestrator:**
- Apply `registry-L3.3.patch` and `ci-wiring-L3.3.patch`.
- Ratify these, if outside case's map:
  - `App.tsx` and `App.chrome.test.tsx` (the Boards place);
  - `canvas/{GlassCanvas,nodeAttributes}` and `color/palette.ts` (dashed amber);
  - `a11y/every-harness.spec.ts`;
  - `dataset_scope.py`, `entity_pictures.py` and `link_changes.py` (`drawn_on_its_board`);
  - the board rows in `test_route_rights.py`, `test_investigation_levels.py` and `test_no_corpus_counts_on_the_wire.py`.
- Run the independent review (the brief).

**Running:** RUNNING_LINE
