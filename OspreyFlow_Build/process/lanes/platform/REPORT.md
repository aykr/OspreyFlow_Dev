# Platform lane · P1 · report (8 November 2026)

Owner's rulings (8 Nov): keys in the gateway's own database (B), a models file (A), no second person (A), `manage_models` (A); recorded in ADR-135 Amendment 2 and ADR-112 Amendment 7.

**Exit criteria, all met at 6715150 (tree 6b87f3b6); every test shown red first (`P1_RED_RECORD.md`):**
- Every Models route refuses anyone without `manage_models` (rule 4): `test_model_admin_routes.py::test_every_models_route_refuses_a_principal_without_manage_models`.
- The key is in no response, log, audit row, file or argument: `…::test_a_planted_key_appears_in_no_response_log_audit_file_or_gateway_row` and `…::test_no_route_echoes_a_key_shaped_value_in_a_refusal`, plus `test_models_verb.py` and `test_cluster_install.py`.
- The key round trip (`…::test_the_key_reaches_the_gateway_credential…`): against the stand-in, which refuses as the measured gateway does; the Conduit's own client was also run once against the real pinned gateway, under the lease.
- The connection test's refusals in words: `test_connection_check.py`.
- Keyboard: `admin-models.spec.ts`, 9 cases. axe: 16 scans over 4 states in the dark, light and GOV.UK themes.
- The egress warning reads `providers`: `test_egress_consequence.py`.

**Gates** (`gates/`):
- `make -k ci` passes but for the seven trivy image scans (Docker Hub 429).
- `make test`: 8239 passed, 4 failed. Two clear with the section-list diff; two (`osprey.yaml`'s map provider, `graphify-out/` at the worktree root) aren't the lane's.
- `test-js`: 2656 passed, 1 timing budget failed under load (it passes alone).
- Each failure is explained in `gates/README.md`.

**Left:**
- Models is in Admin's list only once the orchestrator commits the section diff.
- System says where engines are changed, but has no link to Models: a link needs AdminPlace, which is admin's file.
- No live `apply` moving keys on a real deployment: it needs the owner's stack.

**Commits:** 6531f9c…6715150 (17, on main 83b3d17), then 5b040d4 (the gates) and this report.

**Requests to the orchestrator:**
- Commit the section diff, and keep 21a1b14 (`MODELS_ACTIONS` and the axe states).
- Ratify these changes outside the lane's map: `spec/03` and `spec/05` §2.1; `harness/{apply,cluster_install}.py`; `services/api/Dockerfile`; `cli/ospreyflow/main.py`; System.tsx lines 77–81 and 108–112.

**Questions:** none. **Running:** nothing. The stack is down and the lease released.
