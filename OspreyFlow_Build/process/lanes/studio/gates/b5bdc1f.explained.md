# studio · gates at b5bdc1f (lane/studio rebased onto main 3be89a7), 9 November 2026

The head's code is b5bdc1f; the branch carries records only above it (`8e445ad`, the placesByRole diff, and
the records commit holding this file). Docker Desktop is off on this Mac by the owner's ruling, so the
Docker-dependent cases ran on the server (`stack_lease.sh offline`) and are recorded as this Mac's here.

**Live, under lease studio on stack b, on the server** (`b5bdc1f.live.txt`; `stack_lease.sh remote`, detached,
started 16:10:30Z, survived this Mac's restart at about 17:09, reattached by `remote-log`, ended 19:09:23Z; then
down and released): `test_route_rights.py`, `tests/ingest` whole, `tests/conformance/graph_port` (ADR-006's
cases), the studio store files, both stamping files, `test_source_refresh_snapshot_live.py` and
`test_recipe_runs.py`: **1773 passed, 2 failed, 10 skipped, 1 error.**

- `test_kyc_rules` (a true positive's match left inferred) and `test_typology_rule_routes` (the rule list): main's
  own, failing the same way at main c678a84 under the same lease (`39e2348.explained.md`, `39e2348.reruns.txt`).
- `test_committed_recipes_pin.py` (collection error): the server's copy was no git checkout before main's
  `dc0b7cd`, so its `git ls-files` failed. It reads no stack; run here offline it is 55 passed (`b5bdc1f.reruns.txt`).

Four earlier attempts at this head are kept and withdrawn, none a measurement:
`b5bdc1f.live-withdrawn.txt` (stack b's Postgres had no `ospreyflow` database; created under this lease and
kept), `b5bdc1f.live-tunnel-withdrawn.txt` (the owner's stop: about 0.7 s a call over the tunnel),
`b5bdc1f.live-collect-error.txt` (the git-less copy stopped collection) and `b5bdc1f.live-ssh-dropped.txt`
(the ssh session dropped at 52%; the orphaned pytest stopped by the orchestrator before the rerun).

**`make -k test SKIP_JS=1` and `test-js`, on the server** (`b5bdc1f.server-test.txt`, `stack_lease.sh offline`,
closed ports, no lane): pytest **9535 passed, 2 failed, 11 skipped**; vitest **2767 passed, 1 failed**.

- `test_valkey_config`: main's own (the orchestrator's trial at main, and `39e2348.explained.md`).
- `test_webapp_preflight::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: the server's platform
  reports a GPU check `pass` where the case expects `skip`; on this Mac the file is 6 passed (`b5bdc1f.reruns.txt`).
  Harness code; the lane touches none of it.
- `MatrixView.budget` (7943 ms against the budget under the server's load): run alone it passes
  (`b5bdc1f.reruns.txt`). Not the lane's.

**`make -k ci`, on this Mac** (`b5bdc1f.ci.txt`, offline, closed ports): exit 2, every failure the Docker socket:
the eight `trivy-image-*` scans (and `core-check`, which runs them), `opentofu-check` and `chart-check`. Ruff,
mypy, eslint, tsc and every other gate green.

**`make test` and `test-js`, on this Mac, before the server verb existed** (`b5bdc1f.test.txt`,
`b5bdc1f.test-js.txt`): 24 failed and 30 errors, every one the Docker socket (harness, helm, caddy, TLS, render
memory, workspace proxy) or this machine's own as at 39e2348 (`test_valkey_config`, `test_phone_extraction_fixture`,
`test_deployment_schema`'s skip-worktree `osprey.yaml`, `test_layout`'s `graphify-out`); MatrixView's budget
under load, green alone. Superseded by the server run above.

**Keyboard and axe, on this Mac, on the orchestrator's go** (`b5bdc1f.keyboard.txt`, `b5bdc1f.a11y.txt`): `keyboard/ingest-studio.spec.ts` 51 passed (phase 8's cases and the registry's own coverage case included); `a11y/every-harness.spec.ts -g ingest-studio`, dark, light and GOV.UK, 124 passed.
