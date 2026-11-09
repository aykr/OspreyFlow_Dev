# case-b · L3.8 (the ownership route Disable… reads) · report, 9 November 2026

**Exit.**
- **Route, met.** `GET /v1/admin/people/{user_id}/ownership`, `manage_people` only (`test_everyone_without_manage_people_is_refused`, its row in `test_route_rights.py`). It lists views and boards (shared too), pending link-type proposals and open drawn-item watches. The SQL reads each in the administrator's unit and, for proposals and watches, at the dataset's marking. Items carry kind, id and case name, never an analyst-written name (`test_person_ownership_store.py`, live).
- **Hidden items, met.** They are never named or counted; `withheld` says only that some exist (`test_each_item_left_out_is_said_to_be_withheld_and_never_named`).
- **Disable refused: the seam is met; the 409 is L2.5b's.** `refuse_if_withheld` raises `admin_people.DisableRefused` with `withheld_items`, its words naming nothing. It is asked after the visible transfers commit, and those stand, as `other_unit` is. This is the owner's ruling of 9 November. Promotions are a seam (`promotion_items`; L3.4 is not on main).
- **Red, met.** Each clause, refusal and assertion was planted red alone: 6 offline and 35 live (`L3.8_RED_RECORD.md`).

**Gates and live.**
- make -k ci at 82c1263 (with `OWNERSHIP_CI.diff`): green except Docker's (8 image scans, opentofu, chart).
- test-js at 2361094: 2775 passed, and 1 failed, MatrixView.budget under load; it passes alone.
- make test: the orchestrator gates the merge result.
- Live on stack g, through `stack_lease.sh remote`: run 5 at 786f081 passed 53, with 35 plants red (`gates/live-L3.8*.txt`). Run 1 found a fixture marking the scheme lacks (rule 15); fixed and pinned.

**Reviews.** Three rounds by my lane-reviewer (4, 5 and 2 must-fixes), then the orchestrator's review: all fixed.

**Commits:** `git log main..lane/case-b`, on main 9db2051. The schemas commit is first; then the route, the fixes, spec 03's line and the records.

**Decisions taken.**
1. **Hidden items.** Options: name, count or leave out. I left them out and say `withheld` (yes/no, Amendment 5 decision 8's form).
2. **Views and boards.** Read at their case's unit alone, since they hold no data.
3. **Unmarked datasets.** Read at the scheme's highest, the strict side.
4. **The module's name.** `person_ownership.py`, since `ownership.py` is ADR-109's (friction row).

**Left, for the owner.**
- No route yet lets an Author transfer another person's view, board, proposal or watch, though the refusal's words name Authors. Owner: admin, at L2.5b.
- An item on a dataset whose marking the scheme lacks is withheld from everyone, so its owner cannot be disabled.

**Requests.**
- Apply `OWNERSHIP_CI.diff`; it applies to 538ae67.
- Ratify spec 03's line.
- The L2.5b carry:
  - `OwnedKind` and `OwnedItem.investigation_id`.
  - `l38_owned_items` needs the admin and scheme (`reach`).
  - `L38_OWNED_KINDS`' wording.
  - `_TRANSFER_SQL` and `NEEDS` (draw_on_boards, propose_types) for the four kinds.
  - `refuse_if_withheld` after the commit.

**Still running:** nothing; no stack held.
