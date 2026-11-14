# case-b: the lease tests that fail while a real lane run is live (14 November 2026)

From the orchestrator (ospreyflow-58), 14 November 2026: re-check the `tests/test_stack_lease.py` cases that fail
whenever a real lane run is live on the server; find what they read from the real server state and isolate them
from it, red first; send a diff for the orchestrator's script.

Done when: the cases that collided are named, with what they read; main is shown red under the conditions they
failed in and the change green under the same; every plant is red for its own reason; `stack_lease.sh`'s change is
`stack_lease_sh.diff`, not on the branch; `make -k test` and `make -k ci` pass at the head with the diff applied,
save failures that are main's.
