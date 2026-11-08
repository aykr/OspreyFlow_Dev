# admin lane · report · L2.4 part 2, Admin › Datasets and System (8 November 2026; after review round 1)

1. **Every route refuses without `administer_system`; the right alone is answered: met.** `test_admin_dataset_cases.py` (52). Each of the 8 gates is shown red alone, by its own `right_required` body.
2. **No layer contents on any route: met.** All 9 routes are scanned; red with a label planted. Open and removed rows carry the same fields.
3. **Counts taken by the store, under the reader's handling: met.** `dataset_footprints(ids, principal)` runs in the store's own Gremlin through the access step. `test_dataset_footprints.py` (8 live) was shown red before the method existed, and with each exclusion removed: SECRET items, `R` outside the unit, a link's own marking, reverted elements, cloned links.
4. **Change owner…: met.** It is refused as *Make live* refuses, and its grants and audit are one transaction (live red without it).
5. **Policy, approvers and dry runs: met.** The approvers are the Authors holding `review_promotions`. A composite takes no policy and offers no *Merge*; its layer is delete only (Q5). A dry run counts one layer and writes nothing.
6. **Keyboard: met.** 5 cases, each red without its handler; the ids are in `registry.diff`. **Axe: met.** 12 scans in dark, light and GOV.UK, 28 pass.
7. **Spec: met.** Specs 00, 01, 02 and 03 are updated. The red runs are in `L2.4p2_RED_RECORD.md`; the live runs were on stack a under admin's lease.
8. **Rulings.** The owner's: Q1 (a), Q2 (a), R4 (a). The orchestrator's: R1 (I built the count read), R2 dropped, R3 (a), Q5 (a).
9. **Left.** Backfilling older pictures' sizes; teams (L2.5); the actions themselves, and a member merge for composite layers if the owner chooses one (L3.4); a deployment default for the promotion policy; the policy sits under *Details*, not in the dataset's row; registry ids for *Details* and *Cancel*.
10. **Commits:** 22c5d9b (schemas; dropped on rebase), ca61f6a, 219bf3d, 39dad7c, 6c30dbe, 7cd3ed8, 474d18e, 37950c9, 28fe026, e827a1a, e4bdcbf, b03015d, 66034d5, and this one.
11. **Ratify:** graph.py, the ArcadeDB adapter, `default.yaml`, `entity_pictures.py`, `investigations.py`, `audit.py`, `datasets.py`, app.py's `_owners_allowed`, `every-harness.spec.ts`, `placesByRole.json` (rules'), and specs 00, 01 and 03.
12. **Running:** nothing; the stack is down and the lease released.
