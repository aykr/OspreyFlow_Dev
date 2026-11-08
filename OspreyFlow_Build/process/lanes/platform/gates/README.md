# Platform P2 · gates at 58ee62c (tree 204d685bcadee902b6026863dbb767d9e95fd260), on main 1122bfa

Run 8 November 2026 offline (store ports pinned to unused ports, no stack held), from `OspreyFlow_Build`:
`make -k ci` (`58ee62c.ci.txt`), `make test` (`58ee62c.test.txt`), then `make test-js` (`58ee62c.test-js.txt`,
which `make test` does not reach after a pytest failure, with the one failing case run alone and the harness's
tests appended).

**`make -k ci`: green whole** (exit 0), the seven trivy image scans included.

**`make test`: 8660 passed, 4 failed, 2 errors, none from this branch:**
- `test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates`: this machine's own
  `OspreyFlow_Core/osprey.yaml` (the owner's, never staged) names the map `osm-local-great-britain`, the test
  expects `osm-local`. Not in the branch's diff.
- `test_valkey_config.py::test_the_deployments_own_valkey_is_reached_plainly`: reads `VALKEY_PORT`, which the
  offline run pins to the unused 59993; it expects 6379. An artefact of the offline pins.
- `test_layout.py::test_no_product_folder_is_left_at_the_root`: the repository root's `graphify-out/`, this
  machine's (gitignored) knowledge graph.
- `test_phone_extraction_fixture.py::test_the_extraction_loads_as_documents_held_by_the_phones`: needs an object
  store, and the offline run holds none (the port guard's pins).
- `test_workspace_proxy.py` (2 errors): its image build is refused by Docker Hub's pull limit (429 on
  `nginx:1.30-alpine`).

**`make test-js`: 2683 passed, 1 failed**: `MatrixView.budget.test.tsx` (the 50,000-node first-frame timing),
under the load of a full run; run alone straight after, 1 passed. `apps/harness`: 45 passed.

The branch's own suites, keyboard and axe (`process/lanes/platform/P2_RED_RECORD.md`): the Models keyboard
walkthrough 11 passed and its axe scans 28 passed (7 states × dark, light and GOV.UK, and the label checks), on
servers of the lane's own (the studio lane's Vite held 5185).
