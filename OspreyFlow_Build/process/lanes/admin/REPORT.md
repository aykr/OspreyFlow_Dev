# admin lane · report · L2.5, people and roles, custom roles, teams and leads, and Disable (8 November 2026)

1. **People row (R3), Author visibility and *Name an Author* (R1): met.** The row: places, case levels and *through ‹team›*. *Name an Author* is Admin's own route. Proved by `PeopleAndRoles.test.tsx`, `test_admin_roles_routes.py` (N1, N2 red) and `test_custom_roles_store.py` (rows of one unit, R1 red).
2. **Custom roles (R2), decision 7's refusals at the route: met.** Name used, no rights, unknown right, each pair, an administration right the giver lacks, and the lock-out are each red with its check removed (C1–C9, V1, V6). Rights are exactly as given (C8 red with one extra); an edit applies at the next request (C9).
3. **ADR-112 Am. 5: met.** `author_rules`, `merge_datasets`, *Rule author*, the Super user preset as three roles, and the pairs. `test_rights.py`, red three ways. Landed on main in 3bb3475.
4. **Teams, lead, hand-over, cover: met.** A team's level is gained and lost with membership (M1 red with membership kept). L2.10 reads `CustomRoleStore.team(role_id, today)` and `custom_roles.acting_lead(team, today)`; the lead's own hand-over and cover are L2.10's.
5. ***Disable…*: met for today's owners.** It covers cases and home cases, team leads, hotlists, watches, saved patterns, rules, and pipeline and list schedules. Refused in words while any item is untransferred (D1); allowed once all are, in one transaction (T1, T2, W6). Each unit transfers its share (Y1, Y2). **L2.5b's seam:** `admin_people.l38_owned_items` and `L38_OWNED_KINDS`.
6. **Service accounts own nothing:** refused as member, owner, lead and cover (S1–S3, D2). A dashboard identity may be a Viewer only (Q5; Q1, Q2 red). **Keyboard:** 12 new cases, all green, and `registry.diff` holds their 12 ids. **Axe:** 56 admin-harness cases green, dark, light and GOV.UK. **Live:** stacks a and b, leases named in `L2.5_RED_RECORD.md`.
7. **Gates at e7ddd18 (tree 747c0846), offline:** make -k ci green apart from test-file-coverage-check (the wiring above); the seven trivy scans passed. make test: 8555 passed, 4 failed and 15 errors. All are explained in `gates/e7ddd18.*`: the 15 errors are the unwired store test and fail with the coverage check; the other three failures are this machine's own (osprey.yaml, Valkey, graphify-out), as at 8c2786a.
8. **Reviews:** the lane-reviewer ran two passes (15 findings, then 4 new). All are fixed and red at their call sites, except #10 (a fake) and #13 (owner principals with no right check today), noted here.
9. **Decisions taken:** Q1–Q4 are the owner's rulings and Q3b is (a); Q5 is your settlement. Taken by me:
   - Name an Author got its own route, so an Admin screen does not call the Glass's grant route.
   - A rule or pipeline schedule goes only to an Author of its case.
   - A person's covers end when they are disabled.
   - The dry run checks its right before reading its action (your report).
10. **Not done:** the three items carried from L2.4p2: a deployment default for the promotion policy, the policy under Details, and the Details and Cancel ids. The default needs an `osprey.yaml` setting.
11. **Commits:** ddd96aa fb56ba5 f2d1b06 8e730ac b02aeab 0c0f0e7 db3d883 77fcfba ea2cd64 7d2cb48 e7ddd18 (3bb3475's schemas are on main).
12. **Requests to the orchestrator:**
    - Apply `registry.diff` and `ci-wiring.diff`.
    - Mark `ADR_RESERVATIONS.md` row 69 written.
    - Ratify the out-of-map edits:
      - `investigations.py` (grant_subjects and its three queries);
      - the case grant route's `_may_hold_a_level`, `get_principal`'s custom roles, and `_owners_allowed` (Make live);
      - `admin_people.py` writing the rules, Studio and case lanes' owner columns in one transaction;
      - the tests `test_home_cases.py`, `test_investigation_access_routes.py`, `test_no_corpus_counts_on_the_wire.py` and `test_route_rights.py`;
      - `placesByRole.json`.
    - Note for the case and rules lanes: owner principals built without custom roles (kyc_sweep, the rescreeners, `recipe_run._owner_resolver`, the websocket bearer).
13. **Questions:** none. **Still running:** nothing; no stack is held.
