# make test and make -k ci at ccc7f39, the gated head: each failure explained

Both runs: `stack_lease.sh offline studio -- make test` / `-- make -k ci`, on the test server, with no stack and
no lease, on the orchestrator's word. Raw output, unfiltered: `ccc7f39.make-test.txt` and `ccc7f39.ci.txt`.

- **make test:** pytest had 3 failed, 12911 passed and 33 skipped; vitest had 1 failed and 3167 passed.
- **make -k ci:** every check passed but `route-coverage-check`.

**Why there is a second round.** The first round at 543baaa (`543baaa.make-test.txt`, `543baaa.ci.txt`) found
one defect of this step: `doc-citations-check` (and `tests/test_doc_citations_check.py`) refused my two live
explanations. Their test paths lacked the `tests/` prefix. ccc7f39 corrects the paths, and the check now reads
"every cited path exists".

| Failure | Cause | This step's? |
| --- | --- | --- |
| `tests/services/api/test_audit_kinds.py::test_every_action_the_conduit_writes_is_classified` | the new audit action `set_dataset_source_default_marking` is unclassified; `audit_section.py` belongs to the admin lane | fixed at merge: green with `carries_audit_section.diff` applied |
| `tests/test_route_coverage_check.py::test_no_new_drift_beyond_the_allowlist`, and `route-coverage-check` in ci | the new PUT route is undocumented in `spec/03` | fixed at merge: green with `carries_conduit_routes.diff` applied ("421 route(s), 0 allowlisted, no new drift") |
| `tests/harness/test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass` | the test server has a GPU, so the probe passes where the test expects a skip | no |
| vitest `src/matrix/MatrixView.budget.test.tsx` | a first-frame timing budget under parallel load; it fails in the admin lane's gates too | no |

With both diffs applied on the Mac at ccc7f39, stack-free on the closed ports,
`tests/services/api/test_audit_kinds.py` and `tests/test_route_coverage_check.py` passed: 13 passed. The tree was
then restored.
