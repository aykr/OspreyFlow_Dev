# L1.10b's gates after the rebase onto main 77200db (code 5e8736b, records 8d20acf)

## make test (`gates/efdd801.test.txt`, server, offline)
- pytest: 10,853 passed, 3 failed. The failures are webapp_preflight GPU, valkey_config and render_memory, the same three as at b4881aa: the host's, not the lane's.
- vitest: 1 failed, the MatrixView budget, as before.
- The file's trailing "# exit 0" is grep's status, not the run's; the run's is "make test rc=2 test-js rc=2".
- Since efdd801 the only change is one line in `tests/ingest/test_deployment_ceiling_staged_live.py`, which every offline run skips.

## make -k ci
Not re-run, since no Core code changed in the rebase (the merger's word). Its last run is at b4881aa (`gates/b4881aa.ci.txt`, exit 0).

## The live set (narrowed, by the orchestrator's grant)
The rebase changed only fixtures, so the live set is the branch's own test files plus route rights, not the change-based selection:
- `tests/ingest/test_deployment_ceiling_staged_live.py`
- `tests/services/api/test_deployment_ceiling_staged.py`
- `tests/services/api/test_deployment_ceiling_verify.py`
- `tests/test_seed_internal_ceiling.py`
- `tests/services/api/test_route_rights.py`

`tests/ingest/recipe_test_support.py` changed only by a new `LocalStore.delete_file`, which only these files call.

- **First run, at efdd801 on stack c** (`gates/efdd801.live.txt`): 2 failed, 36 passed. Both failures were the live file's:
  - The refused case's first bucket call had its connection reset. MinIO's port answered but it was not yet ready.
  - The control read no owners, because the live `_load` never committed its transaction. Main's staged tests commit after `run_staged_recipe`. The assertion was new and had only ever been skipped offline.
  - Fixed in 5e8736b. The runner now waits on MinIO's health route.
- **Second run, at 8d20acf on stack c** (`gates/8d20acf.live.txt`): 38 passed, 0 failed, 0 skipped. Both live cases passed against MinIO, in buckets of their own, removed in teardown. Stack c was brought down and released; c to g are free.
