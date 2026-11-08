# Case lane · L3.3 (drawing boards) · report, 8 November 2026

**Exit criteria, each red by a plant at its call site (`L3.3_RED_RECORD.md`):**

- **1 Boards: met.**
  - What a board does: declare an item, link it (by the handle, Alt-drag, the menu or the form) and move it.
  - Every drawn item carries a marking, a grading and a source (a note, a document, or both), and may have an icon.
  - *Same* merges nothing (rule 6). Pictures, uploaded or chosen, are kept in the layer.
  - Tests: `test_boards.py` (44). `keyboard/boards.spec.ts` (33): 28 keyboard cases covering all 23 `BOARD_ACTIONS` ids, and 4 pointer cases.
- **2 A drawing with no case: met.** It makes its drawn dataset, a home case and a board. `test_a_drawing_with_no_case_makes_its_dataset_case_and_board`.
- **3 Watch: met.** Drawing an item sets its watch, and withdrawing the item ends it. A reader who may not see the item sees no watch.
  - Tests: `test_drawing_sets_a_watch_and_withdrawing_ends_it`, `…_withheld_whole`.
  - The watch's queue is left to L3.6.
- **4 Ceiling: met** on every path, refused in words. `test_an_item_above_the_ceiling_is_refused_in_words`, `test_an_edit_an_upload_and_a_choice_above_the_ceiling_are_refused_in_words`.
- **5 Restore: met.** `test_a_drawn_item_and_its_picture_come_back_in_their_cases_layer` (live).
- **Rules 3 and 4: met.**
  - All 17 routes answer another case's member as for a missing case.
  - Nothing of a drawn item reaches another case. The test goes red with K's layer in B's read set, and on real Postgres with the SQL's case clause made true.
  - A lower-cleared member of the same case is told nothing of what they may not see, on any board read or by a withdrawal.
- **Axe:** 48 passed (dark, light and GOV.UK).
- **Gates at `3a6f21a`** (tree `e7a0a9957e88`; `gates/3a6f21a.notes.md`): `make -k ci` green but test-file-coverage (the CI patch); `make test` 8803 passed, failing only on this machine's own and the CI patch's tests; npm test 2693 passed, the matrix timing budget failing at load average 72.
- **Live at `c409fb2`:** lease case on stack b, 21:42–21:43Z, 79 passed. The 1 failure is main's own (P2's two model routes missing from the route-rights table). `gates/c409fb2.live.txt` has the run. Since then only a docstring and `places.json` have changed.

**Lane review (lane-reviewer):** two rounds.
- Round 1 found 14 items; all are fixed.
- Round 2 found 23 items, with two blockers: the restore test could not run, and a withdrawal's watch count told of a link the withdrawer could not see. Both blockers and every must-fix item are fixed.
- Minors left: `POST /v1/drawings` is not atomic (a failed board leaves a usable empty case); the link-change test calls the service directly, not the route; a view-started board reports `start: selection` (spec 03 says so).

**Decisions taken** (the owner may overrule each):
- Only a board's creator draws on it.
- A match is suggested at a score of 0.75 or more.
- Grading is 5x5x5 until L3.7.
- The form asks for the type's required properties.
- An edit is made in place; a marking is never lowered, and a drawn link's marking is never changed.
- Watches live in `drawn_watches`, with no expiry yet.
- A duplicate link is refused.
- The documents offered as a source or picture are those on the board.
- An unseen promoted link is left to L3.4. The orchestrator ruled (a): the node goes, the link stays, and the withdrawer is told nothing.
- `draw_on_boards` opens the Glass.
- **Open question 4** (moving versus linking): built as C7 says, for a field analyst's check.

**For the orchestrator:**
- Apply `registry-L3.3.patch` and `ci-wiring-L3.3.patch`. Without the second, test-file-coverage fails and `make test` errors on `test_board_store.py`.
- Ratify these files outside case's map: `App.tsx`, `App.chrome.test.tsx`, `shell/places{,ByRole}.json`, `canvas/`, `color/palette.ts`, `a11y/every-harness.spec.ts`, `dataset_scope.py`, `entity_pictures.py`, `link_changes.py`, and the board rows in three shared route tests.
- Run your independent review.

**Commits:** `git log main..lane/case`. **Before the merge:** a rebase onto rules' L2.9, as the orchestrator asked (App.tsx's Boards), with the gates run again. **Running:** nothing; the stack is down and the lease released.
