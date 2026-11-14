"""Recreates stack d's ArcadeDB with the poc's heap, keeping its data (the orchestrator's instruction of
14 November, after the host's out-of-memory killer stopped B's load).

The heap is the client's own: the poc's ArcadeDB limit, 12 GiB (`harness/cloud_platform/profile.yaml`),
times `arcadedb_heap_fraction`, 0.75, by `harness.cloud_platform.arcadedb_heap_gib_from_limit`: 9 GiB.

Run on the test server's host, under the rules lane's lease of stack d, with its system Python:
`ssh ospreyflow-test python3 - --heap 9 < recreate_arcadedb.py`. It never touches any container but
`osprey-test-d-arcadedb`: it stops it, renames it `osprey-test-d-arcadedb-old` (never removed here),
and creates a new one from the same image, ports, environment, network, command and restart policy,
`--volumes-from` the old one, changing `ARCADEDB_OPTS_MEMORY` alone. Both containers' settings are
printed, every environment value whose name holds PASSWORD or that names a password left out. The old
container is removed by hand, once the graph is shown whole.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

NAME = "osprey-test-d-arcadedb"
OLD = f"{NAME}-old"
SECRET = re.compile(r"password|rootpassword|secret|token", re.I)


def inspect(name: str) -> dict:
    out = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)[0]


def redacted_env(env: list[str]) -> list[str]:
    shown = []
    for item in env:
        key, _, value = item.partition("=")
        if SECRET.search(key):
            shown.append(f"{key}=<redacted>")
        else:
            # A value can carry a password as a flag (`-Darcadedb.server.rootPassword=…`).
            shown.append(f"{key}=" + re.sub(r"(rootPassword=)\S+", r"\1<redacted>", value))
    return shown


def summary(c: dict) -> dict:
    h = c["HostConfig"]
    return {
        "name": c["Name"].lstrip("/"),
        "image": c["Config"]["Image"],
        "state": {k: c["State"].get(k) for k in ("Status", "ExitCode", "OOMKilled", "StartedAt")},
        "env": redacted_env(c["Config"].get("Env") or []),
        "cmd": c["Config"].get("Cmd"),
        "ports": h.get("PortBindings"),
        "networks": sorted((c["NetworkSettings"].get("Networks") or {}).keys()),
        "restart": h.get("RestartPolicy"),
        "mounts": [(m.get("Type"), m.get("Name") or m.get("Source"), m.get("Destination"))
                   for m in c.get("Mounts") or []],  # fmt: skip
        "memory_limit": h.get("Memory"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--heap", type=int, required=True, help="GiB, the poc's own")
    heap = parser.parse_args().heap
    before = inspect(NAME)
    print("== before\n" + json.dumps(summary(before), indent=1))
    if before["State"].get("Running"):
        subprocess.run(["docker", "stop", NAME], check=True)
    subprocess.run(["docker", "rename", NAME, OLD], check=True)
    h, cfg = before["HostConfig"], before["Config"]
    env = [e for e in cfg.get("Env") or [] if not e.startswith("ARCADEDB_OPTS_MEMORY=")]
    env.append(f"ARCADEDB_OPTS_MEMORY=-Xms{heap}G -Xmx{heap}G")
    cmd = ["docker", "create", "--name", NAME, "--volumes-from", OLD]
    for e in env:
        cmd += ["-e", e]
    for port, binds in (h.get("PortBindings") or {}).items():
        for b in binds or []:
            ip = b.get("HostIp") or ""
            cmd += ["-p", f"{ip + ':' if ip else ''}{b['HostPort']}:{port}"]
    networks = sorted((before["NetworkSettings"].get("Networks") or {}).keys())
    if networks:
        cmd += ["--network", networks[0]]
    policy = (h.get("RestartPolicy") or {}).get("Name")
    if policy and policy != "no":
        cmd += ["--restart", policy]
    for key, value in (cfg.get("Labels") or {}).items():
        cmd += ["--label", f"{key}={value}"]
    entrypoint = cfg.get("Entrypoint") or []
    if entrypoint:
        cmd += ["--entrypoint", entrypoint[0]]
    cmd.append(cfg["Image"])
    cmd += entrypoint[1:] + (cfg.get("Cmd") or [])
    subprocess.run(cmd, check=True, capture_output=True)
    for extra in networks[1:]:
        subprocess.run(["docker", "network", "connect", extra, NAME], check=True)
    subprocess.run(["docker", "start", NAME], check=True, capture_output=True)
    after = inspect(NAME)
    print("== after\n" + json.dumps(summary(after), indent=1))
    changed = [e for e in summary(after)["env"] if e not in summary(before)["env"]]
    print("== changed env: " + json.dumps(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
