"""Fix 2's plant, both shapes "never came up" can take (rule 15: the shape of the real failure).

    crash: every store port closed, so the Conduit's start-up fails and it exits;
    hang:  every store port a listener that accepts and never answers, so start-up waits.

Run from OspreyFlow_Core with the store ports pinned to 59991-59994 (and MINIO_ENDPOINT to 59996),
PYTHONPATH=.:packages:../OspreyFlow_Build. No stack is reached: nothing listens there but this."""

import socket
import sys
import time

import tests.services.api.test_statelessness as t

shape = sys.argv[1]
listeners = []
if shape == "hang":
    for port in (59991, 59992, 59993, 59994, 59996):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(64)  # never accepted: the handshake completes, nothing is ever said
        listeners.append(s)

real_wait = t._wait_until_up
t._wait_until_up = lambda url, **kw: real_wait(url, **{**kw, "timeout_s": 20.0})
began = time.monotonic()
try:
    t._ConduitInstance("http://127.0.0.1:59995/jwks.json")
    print("UP (unexpected)")
except TimeoutError as exc:
    said = str(exc)
    print(f"{type(exc).__name__} after {time.monotonic() - began:.1f} s: {said.splitlines()[0]}")
    print("--- the Conduit's last words (tail) ---")
    print("\n".join(said.splitlines()[-80:]))
