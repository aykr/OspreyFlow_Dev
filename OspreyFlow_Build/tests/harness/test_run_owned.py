"""The test-IdP fixture's containers and network are its run's (`run_owned`; the orchestrator's ruling of 14 November
2026): labelled with the lane and the run, and removed when the run is ended mid-test, by TERM as `stack_lease.sh
stop` sends it, or by the process simply exiting. Offline: Docker is a fake on PATH that refuses what Docker refuses
(rule 15): a network removed while a container is on it, a name started twice, a container or network that does not
exist. Nothing here starts a real container."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[2]
CORE = BUILD.parent / "OspreyFlow_Core"
TAG = "/root/osprey-runs/admin.meta/runs/20261114T050000Z-0123abcd"

#: Docker as far as this fixture uses it, with Docker's refusals; its state in $FAKE_DOCKER_STATE.
FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
path = os.environ["FAKE_DOCKER_STATE"]
state = json.load(open(path)) if os.path.exists(path) else {"containers": {}, "networks": {}, "calls": []}
args = sys.argv[1:]
state["calls"].append(args)
def labels(a):
    return [a[i + 1] for i, x in enumerate(a) if x == "--label"]
def done(code=0, out=""):
    json.dump(state, open(path, "w"))
    if out: print(out)
    sys.exit(code)
if args[:2] == ["network", "create"]:
    name = args[-1]
    if name in state["networks"]: done(1)
    state["networks"][name] = labels(args); done(0, name)
if args[:2] == ["network", "rm"]:
    name = args[2]
    if name not in state["networks"]: done(1)
    if any(c["network"] == name for c in state["containers"].values()): done(1)  # "has active endpoints"
    del state["networks"][name]; done(0, name)
if args[:2] == ["run", "-d"]:
    name, net = args[args.index("--name") + 1], args[args.index("--network") + 1]
    if name in state["containers"] or net not in state["networks"]: done(125)
    state["containers"][name] = {"network": net, "labels": labels(args)}; done(0, name)
if args[0] == "rm":
    name = args[-1]
    if name not in state["containers"]: done(1)  # "No such container"
    del state["containers"][name]; done(0, name)
done(1)
'''

#: A test process, as a run's pytest worker is: the fixture's network and one Keycloak started, then waiting,
#: mid-test, until it is ended (`term`), or returning without its teardown (`exit`).
WORKER = textwrap.dedent('''
    import sys, time
    from pathlib import Path
    from tests.harness import test_organisation_sign_in as m
    network = m._network()
    m._start_keycloak(network, host="login.example.internal", folder=Path("."), certificate=Path("/c.pem"),
                      key=Path("/k.pem"), extra_args=[], environment={}, volumes=[], command=["start-dev"],
                      port=55555)
    print("started", flush=True)
    if sys.argv[1] == "term":
        time.sleep(60)
''')


@pytest.fixture
def world(tmp_path: Path) -> dict[str, object]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(FAKE_DOCKER, encoding="utf-8")
    fake.chmod(0o755)
    state = tmp_path / "docker.json"
    env = {k: v for k, v in os.environ.items() if k not in ("OSPREY_LANE", "OSPREY_RUN_TAG", "OSPREY_PORTS_LANE")}
    env |= {"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}", "FAKE_DOCKER_STATE": str(state),
            "OSPREY_RUN_TAG": TAG, "OSPREY_PORTS_LANE": "admin",
            "PYTHONPATH": os.pathsep.join(str(p) for p in (CORE, CORE / "packages", CORE / "cli", BUILD))}  # fmt: skip
    return {"env": env, "state": state}


def _worker(world: dict[str, object], how: str) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-c", WORKER, how], cwd=BUILD, env=world["env"],  # type: ignore[arg-type]
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # fmt: skip


def _state(world: dict[str, object]) -> dict[str, object]:
    return json.loads(Path(world["state"]).read_text(encoding="utf-8"))  # type: ignore[arg-type]


def _started(proc: subprocess.Popen[str]) -> None:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if line.strip() != "started":
        proc.kill()
        raise AssertionError(f"the worker did not start: {line!r} {proc.stderr.read() if proc.stderr else ''}")


def test_the_fixture_labels_its_containers_and_network_with_the_lane_and_the_run(world: dict[str, object]) -> None:
    proc = _worker(world, "term")
    try:
        _started(proc)
        state = _state(world)
        wanted = ["osprey.lane=admin", f"osprey.run={TAG}"]
        ((network, network_labels),) = state["networks"].items()  # type: ignore[union-attr]
        assert network.startswith("osprey-test-idp-") and network_labels == wanted
        ((name, container),) = state["containers"].items()  # type: ignore[union-attr]
        assert name.startswith("osprey-test-idp-") and container["labels"] == wanted
    finally:
        proc.kill()
        proc.wait()


def test_a_run_ended_mid_test_by_term_leaves_nothing_with_its_label(world: dict[str, object]) -> None:
    """`stack_lease.sh stop` sends TERM: the container goes, then the network, which Docker refuses the other way
    round; the worker still ends by the signal, as it would have without the handler."""
    proc = _worker(world, "term")
    _started(proc)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=30) == -signal.SIGTERM
    state = _state(world)
    assert state["containers"] == {} and state["networks"] == {}
    removals = [c for c in state["calls"] if c[0] == "rm" or c[:2] == ["network", "rm"]]  # type: ignore[union-attr]
    assert [c[0] for c in removals] == ["rm", "network"]


def test_a_run_that_exits_without_its_teardown_leaves_nothing_with_its_label(world: dict[str, object]) -> None:
    proc = _worker(world, "exit")
    _started(proc)
    assert proc.wait(timeout=30) == 0
    state = _state(world)
    assert state["containers"] == {} and state["networks"] == {}


def test_outside_a_run_the_label_names_the_process_not_an_empty_run() -> None:
    from tests.harness.run_owned import run_labels

    saved = {k: os.environ.pop(k, None) for k in ("OSPREY_RUN_TAG", "OSPREY_LANE", "OSPREY_PORTS_LANE")}
    try:
        assert run_labels() == ["--label", "osprey.lane=none", "--label", f"osprey.run=local:{os.getpid()}"]
    finally:
        os.environ.update({k: v for k, v in saved.items() if v is not None})
