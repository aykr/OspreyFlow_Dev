"""T1 part 1's meter (admin lane, 10 November 2026): a pytest plugin, loaded only for the measured run with
``-p t1_meter`` and this folder on PYTHONPATH, that writes one JSON line per test to $OSPREY_T1_METER:

- ``phases``: setup, call and teardown seconds, as pytest reports them;
- ``sleep_s`` and ``sleeps``: the time spent inside ``time.sleep`` and ``asyncio.sleep`` (with a delay above zero)
  while the test, or a fixture it set up or tore down, ran; concurrent sleeps in one event loop are each counted,
  so this is an upper bound;
- ``ports``: the TCP ports the test connected to, read at ``socket.socket.connect`` (which asyncio's own
  connections reach too), so a test that touched no store's port needed none.

It changes no result: each patched call goes through unchanged. Its own check is ``check_t1_meter.py`` beside it.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from typing import Any

import pytest

_current: dict[str, Any] | None = None
_real_sleep = time.sleep
_real_asleep = asyncio.sleep
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _note_sleep(started: float) -> None:
    if _current is not None:
        _current["sleep_s"] += time.perf_counter() - started
        _current["sleeps"] += 1


def _sleep(seconds: float) -> None:
    started = time.perf_counter()
    try:
        _real_sleep(seconds)
    finally:
        if seconds > 0:
            _note_sleep(started)


async def _asleep(delay: float, result: Any = None) -> Any:
    started = time.perf_counter()
    try:
        return await _real_asleep(delay, result)
    finally:
        if delay > 0:
            _note_sleep(started)


def _note_port(address: Any) -> None:
    if _current is not None and isinstance(address, tuple) and len(address) >= 2 and isinstance(address[1], int):
        _current["ports"].add(address[1])


def _connect(self: socket.socket, address: Any) -> None:
    _note_port(address)
    return _real_connect(self, address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    _note_port(address)
    return _real_connect_ex(self, address)


def pytest_configure(config: pytest.Config) -> None:
    time.sleep = _sleep
    asyncio.sleep = _asleep  # type: ignore[assignment]
    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):  # type: ignore[no-untyped-def]
    global _current
    _current = {"nodeid": item.nodeid, "phases": {}, "sleep_s": 0.0, "sleeps": 0, "ports": set()}
    yield
    record, _current = _current, None
    out = os.environ.get("OSPREY_T1_METER")
    if out:
        record["ports"] = sorted(record["ports"])
        record["sleep_s"] = round(record["sleep_s"], 3)
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _current is not None and report.nodeid == _current["nodeid"]:
        _current["phases"][report.when] = round(report.duration, 3)
        if report.when == "call" or report.outcome != "passed":
            _current.setdefault("outcome", {})[report.when] = report.outcome
