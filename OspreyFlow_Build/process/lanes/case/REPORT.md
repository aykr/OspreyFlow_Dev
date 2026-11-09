# Case lane · L3.4 (promotion; a removed case's layer merged or deleted) · report after the fix round, 9 November 2026

Head: the commit that adds this report, on `lane/case`, rebased onto main `9db2051` (L2.6 at `0194eec` and L2.12 at
`dcb1406` both on it; not rebased again once gated). The fix round answers the orchestrator's independent review of
`d31f66f`; the earlier reports are in git history.

| Brief item | State | Proving test |
| --- | --- | --- |
| 1. Promotion: sheet, one load, the dataset's policy and highest marking, review by its approvers | **Met** | `test_promotions.py`, conformance `test_promotion.py`, `test_promotion_store.py` (live) |
| 1. *Promotions overdue* (admin's L2.6 seam) | **Met** | the lifespan's own seam (`app.waiting_promotions_seam`), the case store in `test_waiting_promotions_contract.py`'s `STORES` (nine readers), `test_promotion_sweep_live.py`'s real-store case (live; red with `NoPromotionsYet()`) |
| 2. The Studio's *Analyst promotions* in `ingest/runs/` | **Met** | `promotions.test.tsx`, `keyboard/promotions.spec.ts`, axe |
| 3. A removed case's layer merged (one grant, one merge) or deleted; a composite's never merged | **Met** | `test_a_merge_waits_for_review_under_the_policy_and_its_grant_ends_when_it_is_sent`; the composite cases and their plants |
| 4. `promoted_at`; an unseen promoted link stays, the withdrawer told nothing (`CARRIES.md` row 13) | **Met** | `test_promotions.py`; spec 03 |
| 4. Rules-b's alert badge and the boards' Alerts panel (`CARRIES.md` row 17) | **Met** | `canvas-badge.patch` applied; `boards/BoardAlerts.test.tsx`; `keyboard/boards.spec.ts`'s panel case |
| Open question 2 (online revert) | **Settled (a)** | the operator command alone |
| Keyboard ids as a diff; rule 4 on every route; each check red by a plant | **Met** | `registry-L3.4.patch`; `test_route_rights.py`; `L3.4_RED_RECORD.md`; `gates/keyboard-plants-L3.4.txt` |

## The independent review's findings, as fixed

- **Blocker 1** (`7ca6891`): the waiting seam asks admin's `may_review` of each dataset as it is now (unit,
  highest marking, home case's Authors, custom roles), the reviewable datasets in the store's WHERE; wired in
  the lifespan with `handling_scheme`; red by four plants (`gates/waiting-seam-plants.txt`) and live
  (`gates/sweep-real-store-plant.live.txt`). `ageing-seam-L3.4.md` deleted: nothing left to wire.
- **Blocker 2** (`7f6c59b`): a merge's grant closes when the merge is sent for review; red with the close
  removed (`gates/merge-grant-plant.txt`).
- **3** `audit-census-L3.4.patch` (admin's `audit_section.py`). **4** test-js left to the merge, as asked (it ran
  on the server too: one failure, the matrix's budget on a loaded server). **5** the composite plants and the
  realistic path (`c07072b`). **6** the canvas badge and the boards' Alerts panel (`65d1e8a`). **7** keyboard
  red records for the six actions. **8** Admin's Delete pinned deployment-wide (`3109ed5`, in
  `admin-delete-L3.4.patch`). **9** the friction row. Minors: the rule 4 gaps (Zed, Bob); `_as_pending` says a
  missing dataset in the log (rule 2); generated types checked (no drift); decision 7's composite rule named
  the owner's ruling; the live record names one base and its lease.
- **Found by this round's gates:** rules-b's viewer census red for L3.4's seven rightless routes, weighed in
  `reports-viewer-census-L3.4.patch`; a test helper this round broke, red live and fixed (`b249d29`).

## A defect on main fixed here (not in L3.4's brief)

L3.7's Glass takes its grades only from the opened board's `grading_grades`; the boards keyboard harness gave
none, so *an item is edited by keyboard* hung. Fixed in `7ef5b50` (`f6def92` before the rebase): red `gates/701c027.kb-red.txt`,
green `gates/f6def92.kb.txt` (44), and 45 now (`gates/40bf58e.kb.txt`).

**Gates** (`gates/e6ea09c.notes.md`, every failure explained): `make -k test SKIP_JS=1` and `make test-js` on the
server: 9748 passed, 4 failed (the viewer census, since fixed; main's `test_valkey_config`; the server's GPU and
the offline verb's own root folders), vitest 341 files, 1 failed (the matrix budget on the loaded server).
`make -k ci` here: red only for Docker. Keyboard 45; axe 776. Live, lease case on stack e held throughout:
route rights, the promotion store (11 after the fix), the sweep (2), promotion conformance (9), the board store
(6).

**Requests to the orchestrator:** apply `ci-wiring-L3.4.patch` (regenerated on `9db2051`), `registry-L3.4.patch`,
`admin-delete-L3.4.patch`, `audit-census-L3.4.patch` (admin's), `case-b-writer-gate-L3.4.patch` (case-b's) and
`reports-viewer-census-L3.4.patch` (rules-b's); regenerate `placesByRole.json` (`places-regeneration-L3.4.md`);
ADR-143 Amendment 5 to *written*. **For the owner to overrule, recorded in Amendment 5:** Admin's Delete
deployment-wide; the removed-case routes reached by a Reports Viewer only as a dataset's Author. **Left, not in
this lane's path:** `CARRIES.md`'s `test_valkey_store.py` branch case and the DatasetStore bootstrap lock.
**Questions for the owner:** none blocking. **Running:** nothing; stack e down and released.
