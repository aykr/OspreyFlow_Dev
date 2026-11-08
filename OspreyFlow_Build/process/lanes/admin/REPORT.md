# admin lane · report · L2.4 part 2, Admin › Datasets and System (8 November 2026)

1. **Each route refuses without `administer_system`, and the right alone is answered: met.** `test_admin_dataset_cases.py` checks all nine routes both ways. `test_admin_sections.py` checks over HTTP, and System's owner-setting route is off its list of routes no screen calls.
2. **No layer contents on any route: met.** The response text has no item label or property, and each row holds only its allowed fields. Red with one label planted. Removed and open rows have the same fields.
3. **The store takes the counts (rule 3): met.** `GraphPort.dataset_footprints` has no principal and returns numbers only; conformance written first, 5 live cases. Red tests: superseded counted, ref leaked, zero bytes, empty ids.
4. **Change owner…: met.** Refused for a service account, an unknown account, a team, and against people-only and teams-only. It replaces the Authors and is audited.
5. **Promotion policy and approvers: met.** Approvers are Authors holding `review_promotions`; the test goes red with the right taken from the Data Engineer.
6. **Dry runs: met.** Refused for an open case, a case read through a composite, a composite target, and a merge by a non-Author. They write nothing.
7. **Keyboard (rule 13): met.** Five new cases in `keyboard/admin.spec.ts`, each red with its handler removed; the 24 cases pass. The five registry ids are in `process/lanes/admin/registry.diff`, for you.
8. **Axe, dark, light and GOV.UK: met.** Four new states, 12 scans plus 4 label checks; 28 pass. The scan caught a 2.5.3 fault, now fixed.
9. **Spec: met.** spec/02's Admin area, spec/03's routes, spec/00's principal-free read and spec/01's `size_bytes`. Red runs are in `L2.4p2_RED_RECORD.md`; the live runs were under admin's lease on stack a, 13:17:30Z–13:23Z. Locally, `make -k ci` passes whole (offline, closed ports); vitest for shell and admin: 105 pass.
10. **Rulings recorded:**
    - The owner: Q1 (a) bytes; Q2 (a) the policy field now; R4 (a) a stored `size_bytes`.
    - The orchestrator: R1, I built the count read; R2, dropped (no finding traced); R3, `review_promotions` only.
11. **Left:**
    - Backfill of old pictures' sizes, dry run first: a follow-up; the screen says such pictures aren't counted.
    - Teams in *Change owner…*: waits for L2.5.
    - The actions themselves: L3.4's.
    - *Make live*'s owner screen in the Glass: none exists yet.
12. **Commits:** 22c5d9b (schemas, merge first), ca61f6a, 219bf3d, 39dad7c, 6c30dbe, 7cd3ed8, 474d18e, 37950c9 and this report.
13. **To ratify:**
    - graph.py, the ArcadeDB adapter, the ontology, entity_pictures.py and investigations.py;
    - datasets.py, and app.py's `_owners_answered` split (case's Make live code);
    - every-harness.spec.ts, and spec 00, 01 and 03.
    - Check graph.py and the adapter against lane/case: `dataset_footprints` only.
14. **Still running:** nothing. The stack is down and the lease released.
