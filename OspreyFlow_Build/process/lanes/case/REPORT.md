# Case lane · L3.4 (promotion; a removed case's layer merged or deleted) · report, 9 November 2026

Head `f6def92`, rebased onto main `3be89a7` (main has since moved; not rebased again, as gated). The earlier
version of this report (at `f315852`) is in git history; this one replaces it after the independent review's
fixes, a lane review of the delta after them, and fresh gates.

| Brief item | State | Proving test |
| --- | --- | --- |
| 1. Promotion: sheet, one load, the dataset's policy and highest marking, review by its approvers | **Met** | `test_promotions.py` (above-marking refusal, nothing readable before review, never the proposer), conformance `test_promotion.py`, `test_promotion_store.py` (live) |
| 1. *Promotions overdue* (admin's ageing seam) | **Half: our side built, wiring waits** | `WaitingFromStore` (`test_the_waiting_seam_lists_only_the_readers_unit_and_clearance`); admin's L2.6 not on main, wiring in `ageing-seam-L3.4.md` |
| 2. The Studio's *Analyst promotions* in `ingest/runs/` | **Met** | `promotions.test.tsx`, `keyboard/promotions.spec.ts`, axe (dark, light, GOV.UK) |
| 3. A removed case's layer merged (grant ends with the merge) or deleted; a composite's never merged | **Met** | `test_promotions.py`'s merge, grant, restored-case and delete cases |
| 4. `promoted_at` at promotion; an unseen promoted link stays, the withdrawer told nothing | **Met** | `test_promotions.py`; spec 03 |
| 4. Rules-b's alert badge overlay and the boards' Alerts panel | **Untouched: blocked** | rules-b's L2.12 not on main |
| Open question 2 (online revert) | **Settled (a)** | the operator command alone, `scripts/revert_promotion.py` (ADR-143 Amendment 5 decision 8) |
| Keyboard ids as a diff; rule 4 on every route; each check red by a plant | **Met** | `registry-L3.4.patch`, `test_route_rights.py`, `L3.4_RED_RECORD.md` |

**This session's changes.** `701c027`: the lane review of the commits after the independent review's answer
found decision 12 describing the revert's Conduit probe as a `/healthz` call "as a seed does" (the code makes a
bare connection, stopped only when refused) and claiming "conformance first" for the transaction read (it was
red afterwards, by a plant in the adapter); both corrected, with the dry runs (shown first, never required),
the port's narrowed `tx` promise and the conformance case's control named as such.

## A defect on main fixed here (not in L3.4's brief)

L3.7 (`30ec059`, `b9121e7`) made the Glass take its grades only from the opened board's `grading_grades`;
`keyboard/boards-harness.tsx` (this lane's, from L3.3) was never given them, so *an item is edited by keyboard*
hung on an empty *Source* list, on main as here. `f6def92` gives the harness `GRADING_PARTS["5x5x5"]`.
**Red** without it: `gates/701c027.kb-red.txt` (2 failed: the case and the registry check counting it). **Green**
with it: `gates/f6def92.kb.txt` (44 passed). Nothing in `src/` changed. Accepted into L3.4 by the orchestrator.

**Gates** (`gates/f6def92.notes.md`, every failure explained), with the four hand-off patches and
`placesByRole.json` applied, uncommitted:
- `make -k ci` (`701c027.ci.txt`): exit 2, only Docker's targets (eight trivy scans, opentofu, chart): Docker is
  off on this machine by the owner's ruling.
- `make test` (`701c027.test.txt`): 9573 passed, 24 failed, 30 errors, all Docker's harness cases, the closed
  offline Valkey port, no object store offline, `graphify-out` at the root; none in a file of this branch.
- Keyboard 44 (`f6def92.kb.txt`); axe 740 (`701c027.axe.txt`).
- **Live**, lease case, stack e, on the server by `stack_lease.sh remote`: **407 passed** (`f6def92.live.txt`):
  the whole graph-port conformance suite, route rights, the promotion, board, analyst-layer and case-writes
  stores, composite writes, the drawn layer's restore. Earlier attempts not results: over the tunnel,
  withdrawn on the owner's stop (`701c027.live-withdrawn.txt`); a dropped ssh connection
  (`f6def92.live-dropped.txt`).

**Requests to the orchestrator:** apply `ci-wiring-L3.4.patch`, `registry-L3.4.patch`, `admin-delete-L3.4.patch`
(admin's; its `app.py` hunk applies with an offset, its spec 03 hunk only after this merge) and
`case-b-writer-gate-L3.4.patch` (case-b's); regenerate `placesByRole.json` as `places-regeneration-L3.4.md` says;
wire `ageing-seam-L3.4.md` at L2.6's merge; ADR-143 Amendment 5 to *written* at merge. **Left, not in this
lane's path:** `CARRIES.md`'s `test_valkey_store.py` branch case (c467064) and the DatasetStore bootstrap lock,
for a hygiene step. **Questions for the owner:** none. **Running:** nothing; stack e down and released.
