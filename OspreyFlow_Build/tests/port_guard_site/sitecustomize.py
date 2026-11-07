"""Carries the test-harness port guard into every Python process a test starts (rule 14).

`tests/port_guard.py`'s `pytest_configure` puts this folder and `OspreyFlow_Build` first on the
`PYTHONPATH` it hands to children, with `OSPREY_PORT_GUARD=1`; Python imports `sitecustomize` at
start-up, so a child (a second Conduit under `uvicorn`, a seeding script) wraps its own sockets and
turns uvloop off before it can connect anywhere. Found 7 November 2026: a stopped run's orphaned
`uvicorn` held 35 connections to the leased stack during another lane's lease. Its proof is
`tests/test_port_guard.py`'s `test_a_process_a_test_starts_is_refused_the_leased_stack_too`.
"""

import os

if os.environ.get("OSPREY_PORT_GUARD") == "1" and os.environ.get("CI", "").strip().lower() != "true":
    from tests.port_guard import guard_socket, neutralise_uvloop

    guard_socket()
    neutralise_uvloop()
