"""`test_harness_image.py::_wait_for_ports_bindable`'s own proof — round 13e, owner ruling R11.

Hermetic and fast (no Docker, no `OSPREY_TEST_HARNESS_IMAGE`): a bare TCP socket held on a scratch
port stands in for the `TIME_WAIT`-held port `_wait_for_ports_bindable` exists to wait out, with
short `timeout_seconds`/`poll_seconds` overrides so both the "clears in time" and "never clears"
paths run in well under a second of real waiting.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from pathlib import Path

import pytest
import yaml

from tests.harness.test_harness_image import _wait_for_ports_bindable


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _write_compose(tmp_path: Path, port: int) -> Path:
    """`--out-root` is a root the real code joins with a profile directory before reading
    `compose.yaml` (`harness.preflight.__main__`) — nested the same way here, under a fake
    profile name, so `_wait_for_ports_bindable`'s own `glob("*/compose.yaml")` finds it exactly
    as it would find the real one."""
    compose = {"services": {"workspace": {"ports": [f"{port}:80"]}}}
    out_root = tmp_path / "rendered"
    profile_dir = out_root / "local-lite"
    profile_dir.mkdir(parents=True)
    (profile_dir / "compose.yaml").write_text(yaml.safe_dump(compose), encoding="utf-8")
    return out_root


def test_returns_immediately_when_every_port_is_already_free(tmp_path: Path) -> None:
    out_root = _write_compose(tmp_path, _free_port())
    started = time.monotonic()
    _wait_for_ports_bindable(out_root, timeout_seconds=1.0, poll_seconds=0.1)
    assert time.monotonic() - started < 0.5, "waited on a port that was never taken"


def test_waits_for_a_held_port_and_returns_once_it_frees(tmp_path: Path) -> None:
    """The case this function exists for: a port that is taken *now* and frees itself shortly
    after — the `TIME_WAIT`-after-teardown shape, stood in for here by a socket a background
    thread holds open for a fixed, short interval before closing it."""
    port = _free_port()
    out_root = _write_compose(tmp_path, port)
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", port))
    holder.listen(1)

    hold_seconds = 0.6

    def release_after_delay() -> None:
        time.sleep(hold_seconds)
        holder.close()

    threading.Thread(target=release_after_delay, daemon=True).start()

    started = time.monotonic()
    _wait_for_ports_bindable(out_root, timeout_seconds=5.0, poll_seconds=0.1)
    elapsed = time.monotonic() - started
    assert elapsed >= hold_seconds, (
        f"returned after {elapsed:.2f}s, before the port ({port}) actually freed at "
        f"{hold_seconds:.2f}s — it did not really wait"
    )


def test_fails_by_name_if_the_port_never_frees(tmp_path: Path) -> None:
    port = _free_port()
    out_root = _write_compose(tmp_path, port)
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    try:
        with pytest.raises(pytest.fail.Exception, match=str(port)):
            _wait_for_ports_bindable(out_root, timeout_seconds=0.3, poll_seconds=0.1)
    finally:
        holder.close()


def test_no_declared_ports_returns_without_waiting(tmp_path: Path) -> None:
    out_root = tmp_path / "rendered"
    profile_dir = out_root / "local-lite"
    profile_dir.mkdir(parents=True)
    (profile_dir / "compose.yaml").write_text(
        yaml.safe_dump({"services": {"workspace": {}}}), encoding="utf-8"
    )
    _wait_for_ports_bindable(out_root, timeout_seconds=1.0, poll_seconds=0.1)
