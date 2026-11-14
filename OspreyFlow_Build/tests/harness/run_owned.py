"""Docker objects a test starts, owned by the run that started them (the orchestrator's ruling of 14 November 2026,
after the test server ran out of memory with twelve test-IdP Keycloaks no run could be shown to own).

- **Labelled with their run.** Each container and network is labelled `osprey.lane` (`OSPREY_LANE`, else the
  lane `stack_lease.sh` names for an offline run, `OSPREY_PORTS_LANE`) and `osprey.run` (`OSPREY_RUN_TAG`, the run's
  folder, which `stack_lease.sh` exports to every process of a run; `local:<pid>` outside one). So whatever a
  run leaves, `stack_lease.sh stop` and `reap` remove by that label, and never another run's.
- **Removed when the run is ended.** Each object is recorded as it is started, and removed by its fixture's own
  teardown, on TERM (what `stack_lease.sh stop` sends) and at exit, containers before networks (Docker refuses to
  remove a network a container is still on). A KILL leaves them to the reaper's label.
"""

from __future__ import annotations

import atexit
import os
import signal
import threading
from collections.abc import Callable
from types import FrameType
from typing import Any

LANE_LABEL = "osprey.lane"
RUN_LABEL = "osprey.run"


def run_labels() -> list[str]:
    """`docker run` / `docker network create` arguments labelling an object with this run."""
    lane = os.environ.get("OSPREY_LANE") or os.environ.get("OSPREY_PORTS_LANE") or "none"
    run = os.environ.get("OSPREY_RUN_TAG") or f"local:{os.getpid()}"
    return ["--label", f"{LANE_LABEL}={lane}", "--label", f"{RUN_LABEL}={run}"]


class Owned:
    """What this process has started and not yet removed: containers, then networks."""

    def __init__(self, docker: Callable[..., Any]) -> None:
        self._docker = docker
        self._lock = threading.Lock()
        self._containers: list[str] = []
        self._networks: list[str] = []
        self._installed = False

    def container(self, name: str) -> str:
        self._install()
        with self._lock:
            self._containers.append(name)
        return name

    def network(self, name: str) -> str:
        self._install()
        with self._lock:
            self._networks.append(name)
        return name

    def remove_container(self, name: str) -> None:
        self._docker("rm", "-f", "-v", name, check=False)
        with self._lock:
            if name in self._containers:
                self._containers.remove(name)

    def remove_network(self, name: str) -> None:
        self._docker("network", "rm", name, check=False)
        with self._lock:
            if name in self._networks:
                self._networks.remove(name)

    def remove_all(self) -> None:
        with self._lock:
            containers, networks = list(self._containers), list(self._networks)
        for name in containers:
            self.remove_container(name)
        for name in networks:
            self.remove_network(name)

    def _install(self) -> None:
        if self._installed:
            return
        self._installed = True
        atexit.register(self.remove_all)
        if threading.current_thread() is not threading.main_thread():
            return  # a signal handler is set from the main thread alone; atexit still holds
        previous = signal.getsignal(signal.SIGTERM)

        def on_term(signum: int, frame: FrameType | None) -> None:
            self.remove_all()
            signal.signal(signal.SIGTERM, previous)
            if callable(previous):
                previous(signum, frame)
            else:
                os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGTERM, on_term)
