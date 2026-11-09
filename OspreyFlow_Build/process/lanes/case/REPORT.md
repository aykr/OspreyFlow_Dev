# Case lane · L3.4 (promotion; a removed case's layer merged or deleted) · report after round 2, 9 November 2026

Gated head: **`2ce2377`**, on `lane/case`, rebased onto main `9db2051` (not rebased again once gated). After it,
records only: `d90f94e` (ADR-143 Amendment 5 to the owner's rulings, and the two comments naming them) and
`09683c2` (the gate files), then the commit adding this report. Round 2 answers the orchestrator's independent
review of `d577c14`; the earlier reports are in git history.

| Brief item | State | Proving test |
| --- | --- | --- |
| 1. Promotion: sheet, one load, the dataset's policy and highest marking, review by its approvers | **Met** | `test_promotions.py`, conformance `test_promotion.py`, `test_promotion_store.py` (live) |
| 1. *Promotions overdue* (admin's L2.6 seam) | **Met** | the lifespan's own seam (`app.waiting_promotions_seam`), the case store in `test_waiting_promotions_contract.py`'s `STORES` (nine readers, `p-item-high` among the waiting), `test_promotion_sweep_live.py`'s real-store case (live; red with `NoPromotionsYet()`) |
| 2. The Studio's *Analyst promotions* in `ingest/runs/` | **Met** | `promotions.test.tsx`, `keyboard/promotions.spec.ts`, axe |
| 3. A removed case's layer merged (one grant, one merge, claimed atomically) or deleted, by an Author holding `investigate`; Admin's Delete within the dataset's unit; a composite's never merged | **Met** | `test_a_merge_waits_for_review_under_the_policy_and_its_grant_ends_when_it_is_sent`, `test_a_merge_whose_grant_another_merge_closed_meanwhile_records_nothing`, `test_a_reports_viewer_who_is_an_author_writes_nothing_to_a_removed_cases_layer`, `test_admin_delete_is_scoped_to_the_datasets_unit` (in `admin-delete-L3.4.patch`); the composite cases and their plants |
| 4. `promoted_at`; an unseen promoted link stays, the withdrawer told nothing (`CARRIES.md` row 13) | **Met** | `test_promotions.py`; spec 03 |
| 4. Rules-b's alert badge and the boards' Alerts panel (`CARRIES.md` row 17) | **Met** | `canvas-badge.patch` applied; `boards/BoardAlerts.test.tsx`; `keyboard/boards.spec.ts`'s panel case |
| Open question 2 (online revert) | **Settled (a)** | the operator command alone |
| Keyboard ids as a diff; rule 4 on every route; each check red by a plant | **Met** | `registry-L3.4.patch`; `test_route_rights.py`; `L3.4_RED_RECORD.md`; `gates/keyboard-plants-L3.4.txt` |

## Round 2's findings, as fixed

- **1** (`b47708a`): Admin's Delete of a removed case's layer within the dataset's current unit; another unit's
  administrator, or one with none, answered 404 as for no dataset, before anything is read. Red with the check
  removed (`gates/admin-delete-unit-plant.txt`). In `admin-delete-L3.4.patch` with spec 03's line. **The owner
  ruled this way on 9 November**; Amendment 5 says so (`d90f94e`).
- **2** (`d567733`): the five removed-case writes name `investigate` (every Author role holds it, a Reports
  Viewer does not); a Reports Viewer who is an Author writes nothing, 403 before anything is read. Red with the
  right removed (`gates/layer-writes-right-plant.txt`). `test_route_rights.py`'s five rows; the census patch now
  weighs only the two reads. **The owner ruled this way on 9 November; ADR-112 stands.**
- **3** (`f63d4d8`): the seam's `waiting()` also filters `marking = ANY(the markings the reader clears)` in the
  store's WHERE; the contract gains `p-item-high` (items marked above the dataset's highest), red for the case
  store with the filter planted out (`gates/waiting-seam-plants.txt`, round 2 section); `promotion_store.py`'s
  comment names `waiting(markings=…)`.
- **4** (`2ce2377`): the friction fragment is one row.
- **5**: one green live run at `2ce2377` of the whole set through one remote call: **409 passed**
  (`gates/2ce2377.live.txt`).
- **Minors:** the grant claimed atomically before anything is recorded, `close_grant` answering whether this call
  closed it, a merge losing the race refused 403 `no_open_grant` with nothing recorded (`c2b1b18`, red in
  `gates/grant-claim-plant.txt`); the seam's dataset-marking branch planted (`gates/waiting-seam-plants.txt`); the
  board composite plant carried through the promote route (`cd30250`, `3d1df6e`: refused 409
  `composite_read_only` at the write, recorded rejected, nothing promoted); one gated head named here.

## A defect on main fixed here (not in L3.4's brief)

L3.7's Glass takes its grades only from the opened board's `grading_grades`; the boards keyboard harness gave
none, so *an item is edited by keyboard* hung. Fixed in `7ef5b50`: red `gates/701c027.kb-red.txt`, green 45
(`gates/40bf58e.kb.txt`).

**Gates at `2ce2377`** (`gates/2ce2377.notes.md`, every failure explained), with the six patches applied and
`placesByRole.json` regenerated, uncommitted, reversed after: `make -k test SKIP_JS=1` and `make test-js` on the
server (`2ce2377.test.txt`): pytest 9751 passed, 2 failed (main's `test_valkey_config`; the server's GPU), vitest
341 files, 1 failed (the matrix budget on the shared server); none this branch's. `make -k ci` here
(`2ce2377.ci.txt`): red only for Docker (off on this Mac). Live (`2ce2377.live.txt`): 409 passed, lease case on
stack e, acquired before and down and released after. No screen changed this round, so keyboard 45 and axe 776
(round 1) stand.

**Requests to the orchestrator:** apply `ci-wiring-L3.4.patch`, `registry-L3.4.patch`, `admin-delete-L3.4.patch`,
`audit-census-L3.4.patch` (admin's), `case-b-writer-gate-L3.4.patch` (case-b's) and
`reports-viewer-census-L3.4.patch` (rules-b's); regenerate `placesByRole.json` (`places-regeneration-L3.4.md`);
ADR-143 Amendment 5 to *written* (the owner's rulings now in it). **Pending, another lane's:** admin's
`PendingPromotion.items_marking` (`lane/admin` `b2a9cc2`, not on main): when it lands, `_as_pending` passes
`items_marking=r.marking` and the probe asks it, and the contract's `p-item`/`p-item-high` are reconciled. **Left,
not in this lane's path:** `CARRIES.md`'s `test_valkey_store.py` branch case and the DatasetStore bootstrap lock.
**Questions for the owner:** none. **Running:** nothing; stack e down and released.
