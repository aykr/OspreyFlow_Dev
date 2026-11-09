# Platform P4 · gates at fbbd982 (tree 8bbc7662fb695b7d9aaab43a0f2562cbed107a7a), on main 2a2f46c

After the lane's own review round. Run 9 November 2026 offline (store ports pinned to the closed ports
59991–59994, no `OSPREY_LANE`, no stack held), from `OspreyFlow_Build`: `make -k ci` (`fbbd982.ci.txt`),
`make test` (`fbbd982.test.txt`), and `make test-js` from `OspreyFlow_Core` (`fbbd982.test-js.txt`), since
`make test` stops at pytest's failures before its own `test-js` step. Only this README and the report follow.

**`make -k ci`: green but the seven `trivy-image-*` scans**, which could not build: Docker Hub refused the base
images' pulls (`429 Too Many Requests`, 14 times). `core-check` reports an error only because those seven are
among its targets; every other target in it passed. Every other gate passed (`lanes-check`, with ADR-147
Amendment 1 reserved; `route-coverage-check`, with the place-search route in spec 03; `schemas-check`;
`test-file-coverage-check`; `licence-check`; `design-check`; `harness-a11y` among them).

**`make test`: 9094 passed, 3 skipped, 4 failed and 2 errors, none the branch's**, the same six as P3's gates:
`test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates` (the committed `osprey.yaml`'s map
default, as on main), `test_valkey_config.py` (the offline pins), `test_layout.py` (this machine's
`graphify-out/`), `test_phone_extraction_fixture.py` (no object store offline), and `test_workspace_proxy.py`'s
two errors (its image build, Docker Hub's 429).

**`make test-js`: workspace 2756 passed, 1 failed**: `MatrixView.budget.test.tsx`'s first-frame timing under a
full run's load (as at P3); alone, 1 passed. Harness 45 passed.

**Live** (`P4_RED_RECORD.md`, "The leased live run"): platform lease on stack b, 02:23–02:31 UTC at `e1470f1`
on main `90b3149` (the branch then rebased onto `2a2f46c` with one conflict, two amendments appended at the
same place in `06_DECISIONS.md`, both kept): 23 passed; `test_statelessness.py`'s two failed on its 15-second
start-up wait at a load average of 24–29 and passed with the wait at 90 seconds; the stamp and the case's
dataset limit each red live by a plant.

An earlier gate run at `e1470f1` was stopped and discarded: it overlapped the live plants, which change files
in this worktree for a moment, so its results could not be trusted.
