# Platform P1 · gates at b298593 (tree f5bef1304019de5b52c2e662043b8344014f735e), on main b65cc9e

Run 8 November 2026 offline (store ports pinned to unused ports, no stack held), from `OspreyFlow_Build`:
`make -k ci` (`b298593.ci.txt`), `make -k test` (`b298593.test.txt`); then `make test-js` (`b298593.test-js.txt`,
which `make test` does not reach after a pytest failure), the Models keyboard walkthrough
(`b298593.keyboard-admin-models.txt`: `apps/workspace/keyboard/admin-models.spec.ts`, 9 passed) and its axe scans
(`b298593.axe-models-harness.txt`: `models-harness.html`, 4 states × dark, light and GOV.UK, 16 passed).

**make -k ci:** every gate passes but these.
- The seven `trivy-image-*` scans: Docker Hub refused the base images, `429 Too Many Requests` (14 lines).

**make -k test:** 8334 passed, 2 skipped (the two live gateway tests, run under a lease instead), 5 failed, 2 errors.
- `tests/services/api/test_admin_sections.py` (2): Models is in no section until the orchestrator commits the
  section-list diff; with it applied both pass.
- `tests/services/api/test_valkey_config.py::test_the_deployments_own_valkey_is_reached_plainly`: expects
  `VALKEY_PORT` unset or 6379; this offline run pinned it to an unused port. Not a code fault.
- `tests/harness/test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates`: the unstaged
  `OspreyFlow_Core/osprey.yaml` (identical to main's) names `osm-local-great-britain`. Not this lane's.
- `tests/test_layout.py::test_no_product_folder_is_left_at_the_root`: `graphify-out/` at the worktree root,
  there before the session began (gitignored). Not this lane's.
- 2 errors, `tests/harness/test_workspace_proxy.py`: its Docker build hit Docker Hub's 429.

**make test-js:** 2659 passed, 1 failed: `MatrixView.budget.test.tsx`'s first-frame budget under the full run's
load; it passes run alone, and this branch does not touch `matrix/`.

**Not in make test, run apart:** `tests/services/api/test_route_rights.py` fails on main itself: five admin routes
merged to main (`admin_dataset_authors_route` and four more) have no row in its table. Not this lane's. The live
gateway tests: `tests/services/api/test_model_gateway_live.py`, 2 passed under the platform lease on stack b
(`P1_RED_RECORD.md`).
