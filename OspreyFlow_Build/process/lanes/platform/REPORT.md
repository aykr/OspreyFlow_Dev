# Platform lane · P1 · report (8 November 2026, after the independent review)

Owner's rulings (8 Nov): keys in the gateway's own database (B), a models file (A), no second person (A), `manage_models` (A); a changed address removes the key; no backup carries a key (§6.1, A). Recorded in ADR-135 Amendment 2 and ADR-112 Amendment 7.

**Exit criteria, all met at eeb7494; every test shown red first (`P1_RED_RECORD.md`):**
- Every Models route refuses anyone without `manage_models` (rule 4): `test_model_admin_routes.py::test_every_models_route_refuses_a_principal_without_manage_models`.
- The key in no response, log, audit row or argument, and no value echoed: `…::test_a_planted_key_appears_in_no_response_log_audit_file_or_gateway_row` and `…::test_a_refusal_names_the_field_never_the_value_in_the_answer_or_the_audit`.
- A changed address removes the key: `…::test_changing_an_engine_s_address_removes_its_key_and_sends_it_nowhere_new`.
- A refused rotation is recorded as lost: `…::test_a_rotation_the_gateway_refuses_is_recorded_as_lost_and_not_offered`.
- No key in a backup: `test_gateway_backup.py`.
- The key round trip and the real `pg_dump`, both live under a lease: `test_model_gateway_live.py`.
- Keyboard: 9 cases. axe: 16 scans in the dark, light and GOV.UK themes.
- The egress warning reads `providers`.

**Gates:** `gates/README.md` explains each failure. Not this lane's: the trivy scans (Docker Hub 429), the map in `osprey.yaml`, `graphify-out/`, the Matrix timing under load, and main's own `test_route_rights` gap. The section list's two clear with the diff.

**Left, and why:**
- Choosing each job's local model from the pinned lists: it downloads weights and re-renders, which stays `apply`'s.
- History shows people's subject ids, not their names.
- System has no link to Models: a link needs AdminPlace, which is admin's file.
- No live `apply` on the owner's deployment.
- Docs' D2 adds `restore`'s list of keys to enter again to the administration guide.

**Commits:** lane/platform at eeb7494 (main 8e80496), then the gates and this report.

**Requests to the orchestrator:**
- Commit the section diff and keep 06488b8 (`MODELS_ACTIONS` and the axe states).
- Ratify these changes outside the lane's map: `spec/03` and `spec/05` (§2.1, §6.1); `harness/{apply,cluster,cluster_install}.py`; `services/api/Dockerfile`; `cli/ospreyflow/main.py`; `shell/placesByRole.json`; `a11y/every-harness.spec.ts`; System.tsx lines 77–81 and 108–112.

**Questions:** none. **Running:** nothing. No stack is held.
