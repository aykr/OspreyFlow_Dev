# Platform P1 · gates at 6715150 (tree 6b87f3b6bab8ade9181aaf1809681016a7652ea4), on main 83b3d17

Run 8 November 2026 under the platform lease on test stack a (ports pinned), `make -k ci` and `make -k test` from
`OspreyFlow_Build`; `make test-js` run separately, since `make test` stops its recipe at pytest's failure.

**make -k ci** (`6715150.ci.txt`): every gate passes but the seven `trivy-image-*` scans, each refused building its
base image by Docker Hub: `429 Too Many Requests` (14 lines). No other target failed.

**make -k test** (`6715150.test.txt`): 8239 passed, 39 skipped, 4 failed.
- `services/api/test_admin_sections.py`, 2 cases: the Models routes and `Models.tsx` are in no section until the
  orchestrator commits the section-list diff (`sections.json`, `AdminPlace.tsx`, `AdminSections.test.tsx`). With
  that diff applied both pass (with `test_place_routes.py`: 107 passed).
- `harness/test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates`: the working
  `OspreyFlow_Core/osprey.yaml` (identical to main's, never staged) names `osm-local-great-britain`; not this lane's.
- `test_layout.py::test_no_product_folder_is_left_at_the_root`: `graphify-out/` at the worktree root, there before
  this session began (gitignored); not this lane's.

**make test-js** (`6715150.test-js.txt`): 2656 passed, 1 failed: `MatrixView.budget.test.tsx`'s 50,000-node
first-frame budget, under the full suite's load; it passes run alone, and this branch does not touch `matrix/`.
