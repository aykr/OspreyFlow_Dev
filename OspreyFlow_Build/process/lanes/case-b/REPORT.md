# case-b · L3.8 (the ownership route Disable… reads) · report, 9 November 2026

**Exit.**
- **Route, met.** `GET /v1/admin/people/{user_id}/ownership`, `manage_people` only (`test_everyone_without_manage_people_is_refused`, rights row). It lists a person's views, boards, pending link-type proposals and open drawn-item watches. The reads are in SQL, in the administrator's unit, at the dataset's marking (`test_person_ownership_store.py`).
- **Words only, met.** Kind, the Conduit's id and the case name; never a view's, board's or type's own name (`test_labels_name_the_case_and_never_what_the_analyst_wrote`).
- **Hidden items, met.** A hidden item is never named or counted. `withheld` says only that some exist (`test_each_item_left_out_is_said_to_be_withheld_and_never_named`, 9 cases).
- **Disable refused, met.** `refuse_if_withheld` gives 409 `withheld_items`, its words naming nothing (two `test_disable_is_refused_…` cases). This is the owner's ruling.
- **Promotions: a seam.** `person_ownership.promotion_items`, with `PROMOTION_KINDS` in `not_yet_listed`. L3.4's store is not on main; case wires it.
- **Red, met.** Every test was shown red at its call site: 5 offline and 31 live plants (`L3.8_RED_RECORD.md`).

**Gates and live.** make -k ci at 82c1263 (with `OWNERSHIP_CI.diff`) is green except Docker's (8 image scans, opentofu, chart). test-js at 2361094: 2775 passed, and 1 failed, MatrixView.budget, under load; it passes alone. make test is not run here: the orchestrator gates the merge result through the offline verb. Live on stack g, through `stack_lease.sh remote` (`gates/live-L3.8*.txt`). Run 2 at d6cbdd1: 51 passed, 26 plants red. Run 3 at 2361094: 53 passed, 31 plants red. Run 4, the delta at 0f3c7e9 after the rebase onto L2.12: 23 passed. Run 1 found a fixture marking the scheme lacks (rule 15); fixed and pinned.

**Lane review.** Three rounds by my lane-reviewer, with 4, 5 and 2 must-fixes, all fixed. The two requests it raised are below.

**Commits** on main 9db2051: the schemas commit first, then the route, the fixes, spec 03's line and the records (`git log main..lane/case-b`).

**Decisions taken.**
1. **Items hidden from the administrator.** Options: name them, count them ("2 you can't see"), or leave them out. I left them out and say `withheld` (yes/no, ADR-145 Amendment 5 decision 8's form). That keeps A4, since Disable can still refuse.
2. **The strict default is now the owner's ruling (9 November).** Refused until an administrator of the unit cleared to the item's marking, or its case's Authors, transfers it. The code is `withheld_items`, not `other_unit`.
3. **Views and boards, shared ones too,** since only a view's creator shares or deletes it (ADR-144 decision 3). Drawn watches are included (ADR-143 Amendment 2 decision 8). They are read at their case's unit alone, holding no data.
4. **Unmarked datasets.** A dataset with no marking, or none at all, is read at the scheme's highest, the Model tab's strict side.
5. **No person check,** as `disable-plan`: an unknown id answers empty.
6. **Names.** The module is `person_ownership.py`, since `ownership.py` is ADR-109's UBO module (friction row).

**Requests to the orchestrator.**
- Apply `OWNERSHIP_CI.diff` (live list and ignore).
- Ratify spec 03's route line.
- Write the amendment for the ruling (no reservation held).
- The L2.5b carry: `OwnedKind` lacks the four kinds, `l38_owned_items` takes no `cleared`/`top`, `L38_OWNED_KINDS` says "private views" and omits watches, and `withheld` and `refuse_if_withheld` go into the transfer's transaction.

**Still running:** nothing. No stack is held.
