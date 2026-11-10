# c2e3da8 · make test (offline, on the server) · every failure explained

The run was `stack_lease.sh offline studio-b -- sh -c 'make -k test SKIP_JS=1; …; make test-js'` at `c2e3da8` (rebased
onto main `15d0d24`), on `ospreyflow-test` with no stack and the closed ports 59991–59994. The output is `c2e3da8.test.txt`.

**pytest: 9,664 passed, 2 failed, 11 skipped.** Neither failure is in code this branch touches, and both depend
on the host:

- `tests/services/api/test_valkey_config.py::test_the_deployments_own_valkey_is_reached_plainly`: it expects
  port 6379 and sees the closed offline port 59993 pinned by the run (the offline rule). The same failure is
  explained in `admin/gates/8c2786a.explained.md` and `studio-b/gates/28775d8.explained.md`.
- `tests/harness/test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: the set-up
  console's GPU check answers `pass` on the server's Linux host, where the test expects `skip` for "this
  platform". It is in the harness's preflight, which L1.7a does not touch.

**vitest (test-js): 2,813 passed, 1 failed.** `src/matrix/MatrixView.budget.test.tsx` opened in 4,280 ms against
its 2,500 ms budget on the shared server under the full run. It is a known timing failure under load
(`studio/gates/e8b508b.explained.md`, `rules-b/REPORT.md`). L1.7a changes no Glass code.

**L1.7a's own files are all green in this run:**
- `tests/services/api/test_recipe_repository.py`;
- `test_studio_publish_commit_file.py`;
- `tests/test_connectors_are_carried_into_the_image.py`;
- `tests/test_no_branches_check.py`.
