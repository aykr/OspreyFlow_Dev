# PL7f, round 10: every open case (the conductor, 25 November 2026, 10:23 UTC; the owner's second reserve add-round, its last)

The merge's full gate refused tip `4315b4623a`: **all 40 cases of `tests/harness/test_page_addresses_caddy.py` failed**
with "the real Caddy cannot be run ...: docker could not run caddy:2.11.4-alpine (exit 1: refused: a server-only test:
it calls the docker CLI, and local stacks are off on this machine". The same file passed at your Stop hook. **D234's
exemption does not hold under the merge's own conditions. This round is that row and nothing else. It is the last
round: there is no reserve left.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **The exemption refuses the Caddy test's own command under the merge gate.** The gate runs `make test` from a **temporary copy of the tree** (`/var/folders/.../T/slice-PL7f-merge-*/`), as `.venv/bin/pytest -c <tree>/OspreyFlow_Build/pytest.ini -n auto --dist loadgroup ...` (xdist workers), with `PYTEST_DEBUG_TEMPROOT` set to a temp base of its own beside the tree (`<tree>-pytest`). `is_the_caddy_validation` (`tests/local_docker_guard.py` about lines 192 to 210) compares `PYTEST_CURRENT_TEST`'s file with `CADDY_TEST` and each mount's host with `tempfile.gettempdir()`; one of these differs there (the file relative to a different root, the worker's environment, or the temp base), and the session's refusing `docker` on `PATH` may also be reached. | `tests/local_docker_guard.py`; the Caddy test | **Find which, by running the Caddy test exactly as the gate does** (a copy of your tree under the temporary folder, `-c` its own `pytest.ini`, `-n auto --dist loadgroup`, `PYTEST_DEBUG_TEMPROOT` beside it), red first there, and fix the exemption so it holds in every way pytest runs the file (the checks' direct run and `make test`'s xdist run) **while still naming only that one command asked by that one test** (D234: every other docker call stays refused, the planted second commands still refused). A test reproduces the gate's conditions so this cannot come back. **If it cannot hold under xdist without widening what it allows, stop and say why: that is the owner's.** |
