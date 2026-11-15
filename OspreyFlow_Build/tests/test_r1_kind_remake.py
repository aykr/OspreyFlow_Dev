"""v0.6.0 #11 (the owner's choice (a), 15 November 2026): R1's images are kept when its kind cluster is made again.

`r1_kind.sh remake` deletes the kind cluster alone and runs `up` again: the cluster's registry container
(`osprey-r1-registry`), what it holds, and the `localhost:5001/*` and `kindest/node` images stay, so the second
install of the package test does not build and pull cold. `up` says whether it reused the registry or started an
empty one, so a record shows which. `down` stays the only verb that removes the registry (platform's ask).

The tools are fakes on the script's own tool folder, holding their state in a file and refusing what the real
ones refuse (rule 15): `docker run --name` for a name in use ("Conflict"), `docker rm`/`rmi` of something that
is not there ("No such container" / "No such image"), `docker start` of a missing container, and `kind create
cluster` for a cluster that exists.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "process/lanes/platform/gates/r1_kind.sh"

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
state_file = os.environ["R1_FAKE_STATE"]
s = json.load(open(state_file))
tool, args = os.path.basename(sys.argv[0]), sys.argv[1:]
s["calls"].append([tool, *args])
def out(text=""):
    if text: print(text)
def refuse(text, code=1):
    json.dump(s, open(state_file, "w")); print(text, file=sys.stderr); sys.exit(code)
def flag(name):
    return args[args.index(name) + 1] if name in args else None
if tool == "kind":
    if args[:1] == ["version"]: out("kind v0.27.0")
    elif args[:2] == ["get", "clusters"]: out("\n".join(s["clusters"]))
    elif args[:2] == ["get", "nodes"]:
        n = flag("--name"); out(f"{n}-control-plane" if n in s["clusters"] else "")
    elif args[:2] == ["create", "cluster"]:
        n = flag("--name")
        if n in s["clusters"]: refuse(f'ERROR: failed to create cluster: node(s) already exist for a cluster with the name "{n}"')
        s["clusters"].append(n); s["containers"].append(f"{n}-control-plane")
        if "kindest/node:v1.32.2" not in s["images"]: s["images"].append("kindest/node:v1.32.2"); s["pulled"].append("kindest/node:v1.32.2")
    elif args[:2] == ["delete", "cluster"]:
        n = flag("--name")
        if n in s["clusters"]: s["clusters"].remove(n); s["containers"].remove(f"{n}-control-plane")
        out(f'Deleting cluster "{n}" ...')
elif tool == "docker":
    verb = args[0]
    if verb == "inspect":
        name = [a for a in args[1:] if not a.startswith("-") and not a.startswith("{")][-1]
        if name not in s["containers"] and name not in s["images"]: refuse(f"Error: No such object: {name}")
        out("0")
    elif verb == "run":
        name = flag("--name")
        if name in s["containers"]: refuse(f'docker: Error response from daemon: Conflict. The container name "/{name}" is already in use.', 125)
        s["containers"].append(name); s["running"].append(name); s["registry_contents"] = []
    elif verb == "start":
        name = args[-1]
        if name not in s["containers"]: refuse(f"Error response from daemon: No such container: {name}")
        if name not in s["running"]: s["running"].append(name)
        out(name)
    elif verb == "ps": out("\n".join(s["containers"]))
    elif verb == "rm":
        for name in [a for a in args[1:] if not a.startswith("-")]:
            if name not in s["containers"]: refuse(f"Error response from daemon: No such container: {name}")
            s["containers"].remove(name)
            if name in s["running"]: s["running"].remove(name)
            if name.endswith("-registry"): s["registry_contents"] = []
    elif verb == "images": out("\n".join(s["images"]))
    elif verb == "rmi":
        for name in [a for a in args[1:] if not a.startswith("-")]:
            if name not in s["images"]: refuse(f"Error response from daemon: No such image: {name}")
            s["images"].remove(name)
    elif verb in ("network", "exec", "update", "stats"): pass
    else: refuse(f"fake docker: {verb} not modelled")
elif tool == "kubectl":
    if args[:1] == ["version"]: out("Client Version: v1.32.2")
    elif args[:1] == ["api-resources"]: out("networkpolicies  projectcalico.org/v3  true  NetworkPolicy")
elif tool == "helm":
    out("v3.16.3+g62b6324")
json.dump(s, open(state_file, "w"))
'''


def _world(tmp: Path, *, cluster: bool = True, registry_running: bool = True) -> tuple[dict[str, str], Path]:
    """A server after a first `up` and install: the cluster, its registry holding our images, and those images
    in the local Docker."""
    home = tmp / "home"
    tools = home / "osprey-runs" / "platform.tools" / "bin"
    tools.mkdir(parents=True)
    (home / "osprey-runs" / "platform.r1").mkdir(parents=True)
    for tool in ("kind", "docker", "kubectl", "helm"):
        (tools / tool).write_text(FAKE)
        (tools / tool).chmod(0o755)
    ours = ["localhost:5001/ospreyflow/api:abc123", "localhost:5001/ospreyflow/workspace:abc123"]
    state = {
        "clusters": ["osprey-r1"] if cluster else [],
        "containers": (["osprey-r1-control-plane"] if cluster else []) + ["osprey-r1-registry"],
        "running": ["osprey-r1-registry"] if registry_running else [],
        "images": ["kindest/node:v1.32.2", *ours, "postgres:16"],  # postgres: not ours, never removed
        "registry_contents": ours, "pulled": [], "calls": [],
    }  # fmt: skip
    state_file = tmp / "state.json"
    state_file.write_text(json.dumps(state))
    env = {"HOME": str(home), "PATH": f"{tools}:{os.environ['PATH']}", "R1_FAKE_STATE": str(state_file)}
    return env, state_file


def _run(env: dict[str, str], verb: str, tmp: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), verb], cwd=tmp, env=env, capture_output=True, text=True)


def _state(state_file: Path) -> dict[str, object]:
    return json.loads(state_file.read_text())


def test_remake_keeps_the_registry_and_our_images_and_says_so(tmp_path: Path) -> None:
    env, state_file = _world(tmp_path)
    done = _run(env, "remake", tmp_path)
    assert done.returncode == 0, done.stderr
    s = _state(state_file)
    assert "osprey-r1-registry" in s["containers"] and s["registry_contents"]  # type: ignore[operator]
    assert "localhost:5001/ospreyflow/api:abc123" in s["images"]  # type: ignore[operator]
    assert s["pulled"] == []  # the node image kept, not pulled again
    assert ["kind", "delete", "cluster", "--name", "osprey-r1", "--kubeconfig",
            str(tmp_path / "home/osprey-runs/platform.r1/kubeconfig")] in s["calls"]  # type: ignore[operator]
    assert s["clusters"] == ["osprey-r1"]  # made again by up
    assert "kept: the registry osprey-r1-registry" in done.stdout
    assert "registry: osprey-r1-registry kept, reused" in done.stdout


def test_remake_never_runs_a_second_registry(tmp_path: Path) -> None:
    """The kept registry is reused: a `docker run --name osprey-r1-registry` would be refused (Conflict)."""
    env, state_file = _world(tmp_path)
    assert _run(env, "remake", tmp_path).returncode == 0
    calls = _state(state_file)["calls"]
    assert not [c for c in calls if c[:2] == ["docker", "run"]]  # type: ignore[union-attr]


def test_a_stopped_kept_registry_is_started_again(tmp_path: Path) -> None:
    """`--restart=no`: after the host restarts, the kept registry is stopped, and `up` starts it."""
    env, state_file = _world(tmp_path, registry_running=False)
    assert _run(env, "remake", tmp_path).returncode == 0
    assert "osprey-r1-registry" in _state(state_file)["running"]  # type: ignore[operator]


def test_remake_with_no_registry_to_keep_refuses_in_words(tmp_path: Path) -> None:
    env, state_file = _world(tmp_path)
    s = _state(state_file)
    s["containers"].remove("osprey-r1-registry")  # type: ignore[union-attr]
    state_file.write_text(json.dumps(s))
    done = _run(env, "remake", tmp_path)
    assert done.returncode != 0 and "no osprey-r1-registry to keep: run up first" in done.stderr


def test_up_from_nothing_starts_an_empty_registry_and_says_so(tmp_path: Path) -> None:
    env, state_file = _world(tmp_path, cluster=False)
    s = _state(state_file)
    s["containers"], s["running"], s["registry_contents"] = [], [], []
    state_file.write_text(json.dumps(s))
    done = _run(env, "up", tmp_path)
    assert done.returncode == 0, done.stderr
    assert "registry: osprey-r1-registry started (empty)" in done.stdout


def test_down_still_removes_the_registry_and_our_images_alone(tmp_path: Path) -> None:
    env, state_file = _world(tmp_path)
    done = _run(env, "down", tmp_path)
    assert done.returncode == 0, done.stderr
    s = _state(state_file)
    assert s["containers"] == [] and s["registry_contents"] == []
    assert s["images"] == ["postgres:16"]  # another's image never removed
