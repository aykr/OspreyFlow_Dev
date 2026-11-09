# Platform P3 · gates at fe56149 (tree 477bc806b5d78f1d0e49ae696090be3db4577605), on main ab3d638

After the orchestrator's independent review round. Run 9 November 2026 offline (store ports pinned to
unused ports, no stack held), from `OspreyFlow_Build`: `make -k ci` (`fe56149.ci.txt`), `make test`
(`fe56149.test.txt`), `make test-js` (`fe56149.test-js.txt`). Only this README and the report follow.

**`make -k ci`: green but the seven `trivy-image-*` scans**, which could not build: Docker Hub refused the
base images' pulls (`429 Too Many Requests`, 14 times). Every other gate passed, `harness-a11y`,
`licence-check`, `opentofu-check` and `schemas-check` included. (At the previous head, 21342c3, the NER
image's scan built and was clean.)

**`make test`: 9022 passed, 4 failed and 2 errors, none the branch's**, as at
P2's gates: `test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates` (the committed
`osprey.yaml`'s map default), `test_valkey_config.py` (the offline pins), `test_layout.py` (this machine's
`graphify-out/`), `test_phone_extraction_fixture.py` (no object store offline), and
`test_workspace_proxy.py`'s two errors (its image build, Docker Hub's 429).

**`make test-js`: 2738 passed, 1 failed**: `MatrixView.budget.test.tsx`'s first-frame timing under a full
run's load; alone, 1 passed.

**Live** (Prompt L's set: `test_route_rights.py`, `test_statelessness.py`, `test_tile_cache.py`,
`test_prefetch.py`, `tests/ingest/test_map_admin_build_end_to_end.py`,
`tests/ingest/test_build_local_basemap_end_to_end.py`): platform lease on stack b, 00:35:15–00:38:26 UTC
at fe56149, 20 passed. Earlier runs on stacks b and c failed for the environment alone (a full Docker
disk; another lane's rows), each recorded in `P3_RED_RECORD.md`.
