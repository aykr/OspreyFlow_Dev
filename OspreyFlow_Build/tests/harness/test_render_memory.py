"""The rendered deployment carries the stores' sizes (ADR-114 Amendment 33 decision 6; drop 2,
unit 5), and the real stores start with them.

Rule 15, measured on 3 November 2026 before these were written: PostgreSQL 16.4 **does not refuse**
shared buffers above its container's memory (2 GB in a 512 MB container starts and answers; the
memory is reserved, not touched), and refuses only a value above what the machine can map at all
(64 GB: the server never starts). OpenSearch 2.17.1 with a 4 GiB heap in a 1 GiB container is
killed for memory (exit 137). So the real stores are run here with the rendered settings and shown
to take them, and the impossible values are shown refused by the real stores — the check that keeps
an override within the server is the schema's own (`test_profiles.py`). Each container is a
throwaway on a free port of 127.0.0.1, removed afterwards.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.request
import uuid
from typing import Any

import yaml
from harness.profiles import POSTGRES_MAX_CONNECTIONS, StoreMemory, postgres_command
from harness.render import render

from schemas.deployment import OspreyConfig

from .tls_fixtures import docker

POSTGRES_IMAGE = "postgres:16.4"
OPENSEARCH_IMAGE = "opensearchproject/opensearch:2.17.1"
ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.1"


def _own_server(memory: int | None = 32, **resources: Any) -> OspreyConfig:
    raw: dict[str, Any] = {
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.internal",
                    "tls": {"certificate": "/etc/ospreyflow/tls/osprey.crt",
                            "key": "/etc/ospreyflow/tls/osprey.key"}},
    }  # fmt: skip
    if memory is not None or resources:
        raw["resources"] = {**({"memory_gib": memory} if memory else {}), **resources}
    return OspreyConfig.model_validate(raw)


def _rendered(config: OspreyConfig) -> tuple[dict[str, Any], str]:
    artefacts = render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts
    return yaml.safe_load(artefacts["compose.yaml"])["services"], artefacts["deployment.env"]


def test_the_rendered_compose_and_env_carry_the_sized_values() -> None:
    services, env = _rendered(_own_server(64))
    assert services["arcadedb"]["environment"]["ARCADEDB_OPTS_MEMORY"] == (
        "${OSPREY_ARCADEDB_HEAP:--Xms1G -Xmx25G -XX:+ExitOnOutOfMemoryError}"
    )
    assert services["opensearch"]["environment"]["OPENSEARCH_JAVA_OPTS"] == "-Xms4096m -Xmx4096m"
    # ADR-114 Amendment 43: `max_connections` first, on every owned PostgreSQL, sized or not.
    assert services["postgres"]["command"] == [
        "postgres", "-c", f"max_connections={POSTGRES_MAX_CONNECTIONS}",
        "-c", "shared_buffers=2048MB", "-c", "effective_cache_size=6144MB",
    ]  # fmt: skip
    # Not in deployment.env, which every owned service reads whole: a resize restarts the stores
    # concerned, not the Conduit and the workspace.
    assert "OSPREY_ARCADEDB_HEAP" not in env
    # Unsized, every store is as before.
    plain, plain_env = _rendered(_own_server(None))
    assert plain["opensearch"]["environment"]["OPENSEARCH_JAVA_OPTS"] == "-Xms512m -Xmx512m"
    assert plain["postgres"]["command"] == [
        "postgres", "-c", f"max_connections={POSTGRES_MAX_CONNECTIONS}",
    ]  # fmt: skip
    assert "OSPREY_ARCADEDB_HEAP=-Xms1G -Xmx8G -XX:+ExitOnOutOfMemoryError" in plain_env


def test_a_resize_restarts_only_the_stores_concerned(tmp_path: Any) -> None:
    """`ospreyflow apply` after `resources.memory_gib` changes starts again the graph store,
    OpenSearch and PostgreSQL, and nothing else (ADR-137's `services_to_restart`)."""
    from harness.apply import services_to_restart
    from harness.render import write

    for memory, folder in ((32, "before"), (64, "after")):
        write(
            render(_own_server(memory), resolver=lambda _i: "sha256:" + "0" * 64),
            tmp_path / folder,
        )
    assert services_to_restart(tmp_path / "before", tmp_path / "after") == {
        "arcadedb", "opensearch", "postgres",
    }  # fmt: skip


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _name(store: str) -> str:
    return f"osprey-test-{store}-memory-{uuid.uuid4().hex[:8]}"


def _wait(name: str, ready: Any, seconds: int = 120) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = docker("inspect", "-f", "{{.State.Running}}", name, check=False).stdout.strip()
        if state != "true":
            return False
        if ready():
            return True
        time.sleep(2)
    return False


def _psql(name: str, setting: str) -> str:
    done = docker("exec", name, "psql", "-U", "postgres", "-tAc", f"show {setting}", check=False)
    return done.stdout.strip()


def _initialised(name: str) -> bool:
    """The image's entrypoint, on a first start, runs a temporary server for its set-up and stops
    it before the real one starts (`docker-entrypoint.sh`). Asked before then, a probe can be
    answered by the temporary server and the next one by nothing: measured on the test server on 14
    November 2026, the temporary server ready at 01:46:59.561, shutting down at .710, the real one
    ready at 01:47:00.088. So the server is the real one only once the set-up says so."""
    logs = docker("logs", name, check=False)
    return "PostgreSQL init process complete" in logs.stdout + logs.stderr


def test_postgres_starts_with_the_rendered_settings_and_refuses_an_impossible_one() -> None:
    services, _env = _rendered(_own_server(32))
    command = services["postgres"]["command"]
    name = _name("postgres")
    docker("run", "-d", "--name", name, "--memory", "2g", "-e", "POSTGRES_PASSWORD=throwaway",
           POSTGRES_IMAGE, *command)  # fmt: skip
    try:

        def ready() -> bool:
            return _initialised(name) and _psql(name, "shared_buffers") != ""

        assert _wait(name, ready), docker(
            "logs", name, check=False
        ).stderr[-1500:]
        assert _psql(name, "shared_buffers") == "1GB"
        assert _psql(name, "effective_cache_size") == "3GB"
    finally:
        docker("rm", "-f", "-v", name, check=False)
    # Clearly beyond its 512 MiB: 256 GiB of buffers, whose descriptors alone (about 2 GiB) are
    # written at start. At 64 GiB they were about 512 MiB, the container's whole limit, and on a
    # host that always overcommits (`vm.overcommit_memory=1`, the test server) it sometimes started.
    impossible = postgres_command(StoreMemory(8, 512, 256 * 1024, 3 * 256 * 1024))
    refused = _name("postgres")
    docker("run", "-d", "--name", refused, "--memory", "512m", "-e", "POSTGRES_PASSWORD=throwaway",
           POSTGRES_IMAGE, *impossible)  # fmt: skip
    try:
        assert not _wait(refused, lambda: _psql(refused, "shared_buffers") != "", seconds=40)
        state = docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", refused).stdout
        assert state.split()[0] == "false" and state.split()[1] != "0", state
    finally:
        docker("rm", "-f", "-v", refused, check=False)


def _opensearch_heap(port: int) -> int | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_nodes/jvm", timeout=5) as answer:
            nodes = json.loads(answer.read())["nodes"]
    except OSError:
        return None
    (node,) = nodes.values()
    return int(node["jvm"]["mem"]["heap_max_in_bytes"])


def test_opensearch_starts_with_the_rendered_heap_and_is_killed_by_one_beyond_its_memory() -> None:
    services, _env = _rendered(_own_server(32))
    environment = services["opensearch"]["environment"]
    port = _free_port()
    name = _name("opensearch")
    argv = ["run", "-d", "--name", name, "--memory", "3g", "-p", f"127.0.0.1:{port}:9200"]
    for key, value in environment.items():
        argv += ["-e", f"{key}={value}"]
    docker(*argv, OPENSEARCH_IMAGE)
    try:
        assert _wait(name, lambda: _opensearch_heap(port) is not None, seconds=180), docker(
            "logs", name, check=False
        ).stdout[-1500:]
        assert _opensearch_heap(port) == 2 * 1024**3
    finally:
        docker("rm", "-f", "-v", name, check=False)
    beyond = _name("opensearch")
    docker("run", "-d", "--name", beyond, "--memory", "1g", "-e", "discovery.type=single-node",
           "-e", "DISABLE_SECURITY_PLUGIN=true", "-e", "OPENSEARCH_JAVA_OPTS=-Xms4096m -Xmx4096m",
           OPENSEARCH_IMAGE)  # fmt: skip
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = docker("inspect", "-f", "{{.State.Running}} {{.State.OOMKilled}}", beyond).stdout
            if state.split()[0] == "false":
                break
            time.sleep(2)
        assert state.split() == ["false", "true"], state
    finally:
        docker("rm", "-f", "-v", beyond, check=False)


def test_the_graph_store_starts_with_the_rendered_heap() -> None:
    """ArcadeDB says its heap when it starts (`MAXRAM=`); its page cache is a quarter of it by
    default on 26.10.1 (`arcadedb.maxPageRAM`, read from the engine), so it follows the heap."""
    services, _env = _rendered(_own_server(32))
    heap = services["arcadedb"]["environment"]["ARCADEDB_OPTS_MEMORY"]
    heap = heap.removeprefix("${OSPREY_ARCADEDB_HEAP:-").removesuffix("}")
    name = _name("arcadedb")
    docker("run", "-d", "--name", name, "--memory", "2g",
           "-e", "JAVA_OPTS=-Darcadedb.server.rootPassword=throwaway-root",
           "-e", f"ARCADEDB_OPTS_MEMORY={heap}", ARCADEDB_IMAGE)  # fmt: skip
    try:
        def logs() -> str:
            done = docker("logs", name, check=False)
            return done.stdout + done.stderr

        assert _wait(name, lambda: "MAXRAM=" in logs(), 90), logs()[-1500:]
        assert "MAXRAM=12.00GB" in logs(), logs()[-1500:]
    finally:
        docker("rm", "-f", "-v", name, check=False)
