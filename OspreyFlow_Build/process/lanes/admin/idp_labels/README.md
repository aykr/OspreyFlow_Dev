# Test-IdP containers owned by their run (the orchestrator's ruling, 14 November 2026)

After the test server ran out of memory at 04:40Z, twelve `osprey-test-idp-*` Keycloaks stood on it that no run could
be shown to own: `test_organisation_sign_in.py`'s fixture named them by a bare uuid and labelled nothing, and a run
ended mid-test (TERM from `stack_lease.sh stop`) left its containers and network behind.

- `tests/harness/run_owned.py`: each container and network labelled `osprey.lane` and `osprey.run` (`OSPREY_RUN_TAG`,
  the run's folder `stack_lease.sh` exports to every process of a run), recorded as started, removed by the
  fixture's teardown, on TERM and at exit, containers before networks.
- `stack_lease_reap.diff` (the orchestrator's file): the reaper `stop` and `reap` run also removes, by that label,
  what a KILL left, never another run's; with its test.

Records (offline; Docker a fake on PATH with Docker's refusals, never a real container on this machine):
- `red_main.txt`: main's fixture, TERM mid-test: its container and network left, unlabelled.
- `plant_*.txt` (`replant.py`): eight plants, each red.
- `reap_red.txt` / `reap_green.txt`: the reaper's test before and with the diff.

Still to run, on a server slot: a real run of `test_organisation_sign_in.py` stopped mid-test with
`stack_lease.sh stop`, then `docker ps -a --filter label=osprey.run=<its tag>` and the network list empty.
