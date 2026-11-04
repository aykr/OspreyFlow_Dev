"""The stores keep their data in named volumes, and an existing deployment's data is moved into them
once (`06_DECISIONS.md` ADR-114 Amendment 35; build order step 26).

**As found on the first server (4 November 2026).** The rendered `compose.yaml` gave PostgreSQL,
ArcadeDB and Valkey only the anonymous volumes their images' `VOLUME` lines make, and OpenSearch
none at all. Compose carries an anonymous volume over when it recreates a container, so `stop`,
`start`, `apply` and `update` kept the data; a *new* container gets a new, empty one, so `down` then
`up`, or `uninstall --keep-data` then an install, did not.

**The stand-in (`FakeDocker`) models what the real things refuse, not only what they grant**
(`CLAUDE.md` rule 15): a fresh container gets an empty anonymous volume while a recreated one keeps
its own; PostgreSQL will not start on a data directory that is not its user's or whose mode is not
`0700`/`0750`; the named volume is real state the move has to find empty; and a copy can lose the
top folder's owner, as a copy that is not told to keep it does. The first two are pinned by their
own tests, so the stand-in cannot drift from them without failing here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness import store_volumes
from harness.render import render

from schemas.deployment import OspreyConfig

# --- The render ----------------------------------------------------------------------------------

#: **Written out here, not imported from the renderer**, so a row dropped from the renderer's own
#: table fails this test (rule 12). Each is a path the store's own image declares as a `VOLUME`
#: (PostgreSQL 16.4, ArcadeDB 26.10.1, Valkey 8.0) or, for OpenSearch 2.17.1, its data path.
STORE_PATHS: dict[str, list[str]] = {
    "postgres": ["/var/lib/postgresql/data"],
    "arcadedb": ["/home/arcadedb/databases", "/home/arcadedb/config"],
    "valkey": ["/data"],
    "opensearch": ["/usr/share/opensearch/data"],
}

HTTPS = {"public_origin": "https://osprey.example.org"}


def _resolver(image: str) -> str:
    _, _, pinned = str(image).partition("@")
    return pinned or "sha256:" + hashlib.sha256(str(image).encode()).hexdigest()


def _compose(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(render(config, resolver=_resolver).artefacts["compose.yaml"])


def _named_mounts(document: dict[str, Any], service: str) -> dict[str, str]:
    """`path -> volume` for each of the service's mounts from a volume the file declares."""
    declared = set(document.get("volumes") or {})
    found: dict[str, str] = {}
    for mount in document["services"][service].get("volumes") or []:
        source, _, rest = str(mount).partition(":")
        if source in declared:
            found[rest.split(":")[0]] = source
    return found


def _rendered(profile: str) -> dict[str, Any]:
    network = {"network": HTTPS} if profile == "small" else {}
    return _compose(OspreyConfig.model_validate({"profile": profile, **network}))


@pytest.mark.parametrize("profile", ["local-lite", "small"])
def test_every_store_has_its_named_volume_on_lite_and_small(profile: str) -> None:
    """**Rule 12: the test that fails if a store loses its named volume.** Each store's data path is
    mounted from a volume the compose file declares (so Docker names it `<project>_<volume>`), never
    left to the image's anonymous one."""
    document = _rendered(profile)
    missing = [
        f"{service} {path}"
        for service, paths in STORE_PATHS.items()
        for path in paths
        if path not in _named_mounts(document, service)
    ]
    assert not missing, f"stores with no named volume ({profile}): {missing}"


def test_a_store_left_off_its_named_volume_is_found_by_the_render_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check above shown able to fail for the reason it names: the renderer's table with
    ArcadeDB's databases row taken out, the real render, and the same check."""
    from harness import render as render_module

    kept = tuple(v for v in render_module.STORE_VOLUMES if v.volume != "arcadedb-databases")
    monkeypatch.setattr(render_module, "STORE_VOLUMES", kept)
    document = _rendered("small")
    assert "/home/arcadedb/databases" not in _named_mounts(document, "arcadedb")
    assert "/home/arcadedb/config" in _named_mounts(document, "arcadedb")


def test_the_named_volumes_are_the_amendments_names() -> None:
    document = _rendered("local-lite")
    assert {service: _named_mounts(document, service) for service in STORE_PATHS} == {
        "postgres": {"/var/lib/postgresql/data": "postgres-data"},
        "arcadedb": {
            "/home/arcadedb/databases": "arcadedb-databases",
            "/home/arcadedb/config": "arcadedb-config",
        },
        "valkey": {"/data": "valkey-data"},
        "opensearch": {"/usr/share/opensearch/data": "opensearch-data"},
    }


def test_a_store_the_deployment_does_not_run_gets_no_volume() -> None:
    """OpenSearch with `postgres-fulltext`, PostgreSQL on a managed server: no store, no volume —
    a declared volume nothing mounts is the shape
    `test_every_declared_volume_is_mounted_by_some_service` refuses."""
    document = _compose(
        OspreyConfig.model_validate(
            {"profile": "local-lite", "components": {"search": "postgres-fulltext"}}
        )
    )
    assert "opensearch-data" not in document["volumes"]
    assert "opensearch" not in document["services"]


def test_the_cluster_translation_is_unchanged_by_the_named_volumes() -> None:
    """Enterprise keeps its claims (`harness/cluster.py`'s `CLAIMS`): the named volumes are added to
    the compose document alone, so the services the chart is translated from carry none of them."""
    from harness.render import compose_services, service_images

    config = OspreyConfig.model_validate({"profile": "small", "network": HTTPS})
    services = compose_services(config, service_images(config))
    for service in STORE_PATHS:
        for mount in services[service].get("volumes") or []:
            assert not str(mount).startswith(tuple(v + ":" for v in store_volumes.VOLUME_NAMES))


# --- The stand-in for Docker, Compose and the stores ---------------------------------------------


@dataclass
class Entry:
    uid: int
    gid: int
    mode: int
    kind: str  # "directory" or "regular file"
    content: bytes = b""


Tree = dict[str, Entry]

PROJECT = "osprey-test"

#: Each image's `VOLUME` lines, as the real images declare them; OpenSearch's declares none.
IMAGES: dict[str, dict[str, Any]] = {
    "postgres:16.4": {"id": "sha256:pg", "volumes": ["/var/lib/postgresql/data"]},
    "arcadedata/arcadedb:26.10.1": {
        "id": "sha256:arcade",
        "volumes": [
            "/home/arcadedb/databases",
            "/home/arcadedb/backups",
            "/home/arcadedb/config",
            "/home/arcadedb/log",
            "/home/arcadedb/replication",
        ],
    },  # fmt: skip
    "valkey/valkey:8.0": {"id": "sha256:valkey", "volumes": ["/data"]},
    "opensearchproject/opensearch:2.17.1": {"id": "sha256:search", "volumes": []},
    "osprey/api:local": {"id": "sha256:api", "volumes": []},
}
SERVICE_OF_IMAGE = {
    "sha256:pg": "postgres", "sha256:arcade": "arcadedb", "sha256:valkey": "valkey",
    "sha256:search": "opensearch", "sha256:api": "api",
}  # fmt: skip
OPENSEARCH_DATA = "/usr/share/opensearch/data"


@dataclass
class Container:
    id: str
    service: str
    image: str  # its ID
    mounts: dict[str, tuple[str, str]]  # destination -> ("volume", name) | ("bind", folder)
    config: str  # what Compose would compare: the service's stanza as written
    layer: dict[str, Tree] = field(default_factory=dict)
    running: bool = False


class FakeDocker:
    """Docker Engine and Compose v2 as far as the move uses them, and the four stores' own
    behaviour over their data. **What it refuses, as the real ones do:** PostgreSQL will not start
    on a data directory that is not uid 999's or whose mode is not 0700/0750 ("FATAL: data
    directory … has wrong ownership"/"has invalid permissions"); a volume a container uses cannot
    be removed; a fresh container gets fresh, empty anonymous volumes, and only a recreated one
    keeps its own."""

    def __init__(self, compose_file: Path) -> None:
        self.compose_file = compose_file
        self.volumes: dict[str, Tree] = {}
        self.anonymous: set[str] = set()
        self.containers: dict[str, Container] = {}
        self.calls: list[list[str]] = []
        self.counter = 0
        #: Knobs: a copy that stops part way; a copy that loses the top folder's owner and mode.
        self.fail_copy = False
        self.lose_top_owner = False

    # The world -----------------------------------------------------------------------------------

    def _new_id(self, prefix: str) -> str:
        self.counter += 1
        return hashlib.sha256(f"{prefix}{self.counter}".encode()).hexdigest()

    def _fresh_volume(self) -> str:
        name = self._new_id("volume")
        self.volumes[name] = {}
        self.anonymous.add(name)
        return name

    def container_of(self, service: str) -> Container:
        found = [c for c in self.containers.values() if c.service == service]
        assert len(found) == 1, f"{service}: {len(found)} containers"
        return found[0]

    def tree(self, container: Container, path: str) -> Tree:
        kind, source = container.mounts.get(path, ("layer", ""))
        if kind == "layer":
            return container.layer.setdefault(path, {})
        return self.volumes.setdefault(source, {})

    def _initialise(self, service: str, tree: Tree) -> None:
        """What each image does on an empty data path at its first start."""
        if tree:
            return
        if service == "postgres":
            tree["."] = Entry(999, 999, 0o700, "directory")
            for name in ("postgres",):
                tree[f"./base/{name}"] = Entry(999, 999, 0o700, "directory")
        elif service == "valkey":
            tree["."] = Entry(999, 999, 0o755, "directory")
        else:
            tree["."] = Entry(1000, 1000, 0o755, "directory")

    def _refusal(self, container: Container) -> str | None:
        if container.service != "postgres":
            return None
        root = self.tree(container, "/var/lib/postgresql/data").get(".")
        if root is None:
            return None
        if (root.uid, root.gid) != (999, 999):
            return 'FATAL:  data directory "/var/lib/postgresql/data" has wrong ownership'
        if root.mode not in (0o700, 0o750):
            return 'FATAL:  data directory "/var/lib/postgresql/data" has invalid permissions'
        return None

    def _start(self, container: Container) -> tuple[int, str]:
        for path in ([OPENSEARCH_DATA] if container.service == "opensearch" else
                     IMAGES_BY_ID[container.image]["volumes"]):  # fmt: skip
            if container.service == "arcadedb" and path != "/home/arcadedb/databases":
                continue
            self._initialise(container.service, self.tree(container, path))
        refused = self._refusal(container)
        if refused:
            container.running = False
            return 1, f"container {container.service} is unhealthy\n{refused}"
        container.running = True
        return 0, ""

    # Compose -------------------------------------------------------------------------------------

    def _compose_document(self, argv: Sequence[str]) -> dict[str, Any]:
        path = Path(argv[argv.index("-f") + 1])
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def _up(self, document: dict[str, Any], names: list[str]) -> tuple[int, str]:
        project = document["name"]
        for name in names or list(document["services"]):
            stanza = document["services"][name]
            image = IMAGES[stanza["image"]]["id"]
            config = json.dumps(stanza, sort_keys=True)
            current = [c for c in self.containers.values() if c.service == name]
            old = current[0] if current else None
            if old is not None and old.config == config:
                code, said = self._start(old)
                if code:
                    return code, said
                continue
            mounts: dict[str, tuple[str, str]] = {}
            for mount in stanza.get("volumes") or []:
                source, _, rest = str(mount).partition(":")
                destination = rest.split(":")[0]
                if source.startswith("/"):
                    mounts[destination] = ("bind", source)
                else:
                    full = f"{project}_{source}"
                    self.volumes.setdefault(full, {})
                    mounts[destination] = ("volume", full)
            for path in IMAGES_BY_ID[image]["volumes"]:
                if path in mounts:
                    continue
                kept = old.mounts.get(path) if old is not None else None
                if kept is not None and kept[0] == "volume" and kept[1] in self.anonymous:
                    mounts[path] = kept  # Compose carries a recreated container's own over
                else:
                    mounts[path] = ("volume", self._fresh_volume())
            if old is not None:
                del self.containers[old.id]
            container = Container(self._new_id("container"), name, image, mounts, config)
            self.containers[container.id] = container
            code, said = self._start(container)
            if code:
                return code, said
        return 0, ""

    def compose(self, argv: list[str]) -> tuple[int, str]:
        document = self._compose_document(argv)
        if "up" in argv:
            names = [a for a in argv[argv.index("up") + 1 :] if not a.startswith("-")
                     and a != "never"]  # fmt: skip
            return self._up(document, names)
        if "down" in argv:
            for container in list(self.containers.values()):
                del self.containers[container.id]
            return 0, ""
        raise AssertionError(f"unexpected compose call: {argv}")

    # Docker --------------------------------------------------------------------------------------

    def __call__(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        self.calls.append(argv)
        assert argv[0] == "docker", argv
        verb = argv[1]
        if verb == "compose":
            return self.compose(argv)
        if verb == "ps":
            filters = [argv[i + 1] for i, a in enumerate(argv) if a == "--filter"]
            service = next((f.rsplit("=", 1)[1] for f in filters if ".service=" in f), None)
            found = [
                c.id for c in self.containers.values()
                if (service is None or c.service == service) and ("-a" in argv or c.running)
            ]  # fmt: skip
            return 0, "\n".join(found)
        if verb == "inspect":
            container = self.containers[argv[2]]
            mounts = [
                {"Type": kind, "Name" if kind == "volume" else "Source": source,
                 "Destination": destination}
                for destination, (kind, source) in container.mounts.items()
            ]  # fmt: skip
            return 0, json.dumps([{"Image": container.image, "Mounts": mounts}])
        if verb == "volume":
            return self._volume(argv[2], argv[-1])
        if verb == "start":
            return self._start(self.containers[argv[2]])
        if verb == "stop":
            for name in argv[2:]:
                self.containers[name].running = False
            return 0, ""
        if verb == "exec":
            return self._exec(self.containers[argv[2]], argv[-1])
        if verb == "run":
            return self._run(argv)
        raise AssertionError(f"unexpected docker call: {argv}")

    def _volume(self, action: str, name: str) -> tuple[int, str]:
        if action == "inspect":
            return (0, "[]") if name in self.volumes else (1, f"no such volume: {name}")
        if action == "create":
            self.volumes.setdefault(name, {})
            return 0, name
        if action == "rm":
            if any(("volume", name) in c.mounts.values() for c in self.containers.values()):
                return 1, f"volume is in use - [{name}]"
            self.volumes.pop(name, None)
            self.anonymous.discard(name)
            return 0, name
        raise AssertionError(action)

    def _exec(self, container: Container, command: str) -> tuple[int, str]:
        if not container.running:
            return 1, f"container {container.id} is not running"
        if container.service == "postgres":
            tree = self.tree(container, "/var/lib/postgresql/data")
            names = sorted(
                p.split("/")[2] for p in tree if p.startswith("./base/") and p.count("/") == 2
            )
            return 0, "\n".join(names)
        if container.service == "arcadedb":
            tree = self.tree(container, "/home/arcadedb/databases")
            names = sorted(p[2:] for p in tree if p.count("/") == 1 and p != ".")
            return 0, json.dumps({"result": names})
        if container.service == "valkey":
            dump = self.tree(container, "/data").get("./dump.rdb")
            keyspace = json.loads(dump.content) if dump else {}
            return 0, "# Keyspace\n" + "\n".join(
                f"{db}:keys={k},expires={e},avg_ttl=0" for db, (k, e) in keyspace.items()
            )
        if container.service == "opensearch":
            tree = self.tree(container, OPENSEARCH_DATA)
            listed = tree.get("./indices")
            return 0, listed.content.decode() if listed else ".plugins-ml-config\n"
        raise AssertionError(command)

    def _run(self, argv: list[str]) -> tuple[int, str]:
        mounts: dict[str, Tree] = {}
        for i, word in enumerate(argv):
            if word == "-v":
                source, _, rest = argv[i + 1].partition(":")
                destination = rest.split(":")[0]
                if source.startswith("/"):
                    mounts[destination] = self.volumes.setdefault(f"folder:{source}", {})
                else:
                    mounts[destination] = self.volumes.setdefault(source, {})
        script = argv[argv.index("-c") + 1]
        assert argv[argv.index("-c") - 1] in IMAGES_BY_ID, "a one-shot runs a store's image by ID"
        if script == "ls -A /to":
            return 0, "\n".join(p for p in mounts["/to"] if p != ".")
        if script == store_volumes._LISTING:
            return 0, _listing(mounts["/v"])
        if script == store_volumes._COPY:
            source, target = mounts["/from"], mounts["/to"]
            if [p for p in target if p != "."]:
                return 3, "the named volume is not empty"
            items = sorted(source.items())
            if self.fail_copy:
                for path, entry in items[: len(items) // 2]:
                    target[path] = Entry(**vars(entry))
                return 1, "cp: error writing '/to/base/1/1259': No space left on device"
            for path, entry in items:
                target[path] = Entry(**vars(entry))
            if self.lose_top_owner:
                target["."] = Entry(0, 0, 0o755, "directory")
            return 0, ""
        raise AssertionError(f"unexpected one-shot: {script}")


IMAGES_BY_ID = {spec["id"]: spec for spec in IMAGES.values()}


def _listing(tree: Tree) -> str:
    lines = []
    for path, entry in sorted(tree.items()):
        digest = hashlib.sha256(entry.content).hexdigest() if entry.kind == "regular file" else "-"
        lines.append(f"{entry.uid}:{entry.gid}:{entry.mode:o}:{entry.kind} {digest} {path}")
    return "\n".join(lines)


# The deployment, before and after the render gave the stores their volumes -----------------------

OLD_SERVICES = {
    "postgres": {"image": "postgres:16.4"},
    "arcadedb": {"image": "arcadedata/arcadedb:26.10.1"},
    "valkey": {"image": "valkey/valkey:8.0"},
    "opensearch": {"image": "opensearchproject/opensearch:2.17.1"},
    "api": {"image": "osprey/api:local", "volumes": ["osprey-data:/srv/data"]},
}


def _write_compose(folder: Path, *, named: bool) -> Path:
    services = json.loads(json.dumps(OLD_SERVICES))
    volumes: dict[str, Any] = {"osprey-data": {"driver": "local"}}
    if named:
        from harness.render import name_the_stores

        volumes.update(name_the_stores(services))
    path = folder / "compose.yaml"
    path.write_text(
        yaml.safe_dump({"name": PROJECT, "services": services, "volumes": volumes}),
        encoding="utf-8",
    )
    (folder / "deployment.env").write_text("OSPREY_ARCADEDB_PASSWORD=pw\n", encoding="utf-8")
    return path


def _seed(docker: FakeDocker, *, index: str | None = None) -> None:
    """Data in each store, as a deployment running v0.4.10 has it."""
    postgres = docker.tree(docker.container_of("postgres"), "/var/lib/postgresql/data")
    for name in ("keycloak", "osprey"):
        postgres[f"./base/{name}"] = Entry(999, 999, 0o700, "directory")
    postgres["./base/osprey/16384"] = Entry(999, 999, 0o600, "regular file", b"rows" * 100)
    postgres["./PG_VERSION"] = Entry(999, 999, 0o600, "regular file", b"16\n")
    graph = docker.tree(docker.container_of("arcadedb"), "/home/arcadedb/databases")
    graph["./osprey"] = Entry(1000, 1000, 0o755, "directory")
    graph["./osprey/Person_0.1.65536.v0.bucket"] = Entry(
        1000, 1000, 0o644, "regular file", b"g" * 64
    )
    config = docker.tree(docker.container_of("arcadedb"), "/home/arcadedb/config")
    config["."] = Entry(1000, 1000, 0o755, "directory")
    config["./server-users.jsonl"] = Entry(1000, 1000, 0o600, "regular file", b'{"name":"root"}')
    cache = docker.tree(docker.container_of("valkey"), "/data")
    cache["./dump.rdb"] = Entry(
        999, 999, 0o644, "regular file", json.dumps({"db0": [12, 4]}).encode()
    )
    if index is not None:
        search = docker.tree(docker.container_of("opensearch"), OPENSEARCH_DATA)
        search["./indices"] = Entry(1000, 1000, 0o644, "regular file", f"{index}\n".encode())


def _compose_argv(compose_file: Path) -> list[str]:
    return ["docker", "compose", "--env-file", str(compose_file.parent / "deployment.env"),
            "-f", str(compose_file)]  # fmt: skip


@pytest.fixture
def old_deployment(tmp_path: Path) -> tuple[FakeDocker, Path]:
    """A deployment rendered before the named volumes, running, with data; then its compose file
    rendered again with them, as `apply`, `refresh` or `update` leaves it before its `up`."""
    compose_file = _write_compose(tmp_path, named=False)
    docker = FakeDocker(compose_file)
    assert docker([*_compose_argv(compose_file), "up", "-d", "--wait"])[0] == 0
    _seed(docker)
    _write_compose(tmp_path, named=True)
    return docker, compose_file


@pytest.fixture(autouse=True)
def _move_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_volumes, "ENABLED", True)


def _figures(docker: FakeDocker) -> dict[str, str]:
    return {
        service: docker._exec(docker.container_of(service), "")[1]
        for service in ("postgres", "arcadedb", "valkey")
    }


def _old_volumes(docker: FakeDocker) -> dict[str, str]:
    """The anonymous volume each store's data is in now."""
    return {
        "postgres": docker.container_of("postgres").mounts["/var/lib/postgresql/data"][1],
        "arcadedb": docker.container_of("arcadedb").mounts["/home/arcadedb/databases"][1],
        "arcadedb-config": docker.container_of("arcadedb").mounts["/home/arcadedb/config"][1],
        "valkey": docker.container_of("valkey").mounts["/data"][1],
    }


def _quiet(_words: str) -> None:
    return None


# The stand-in pinned to what the real ones do ----------------------------------------------------


def test_the_stand_in_keeps_anonymous_volumes_on_recreate_and_not_for_a_new_container(
    tmp_path: Path,
) -> None:
    """Compose v2 on Docker Engine, as measured on the first server: a container recreated by `up`
    (its definition changed) keeps its anonymous volumes; `down` then `up` makes a new container
    with new, empty ones, the old left unattached. That is the loss the named volumes end."""
    compose_file = _write_compose(tmp_path, named=False)
    docker = FakeDocker(compose_file)
    up = [*_compose_argv(compose_file), "up", "-d", "--wait"]
    docker(up)
    _seed(docker)
    before = _figures(docker)["postgres"]
    first = _old_volumes(docker)["postgres"]

    services = json.loads(json.dumps(OLD_SERVICES))
    services["postgres"]["environment"] = {"CHANGED": "1"}
    compose_file.write_text(
        yaml.safe_dump({"name": PROJECT, "services": services}), encoding="utf-8"
    )
    docker(up)
    assert _old_volumes(docker)["postgres"] == first
    assert _figures(docker)["postgres"] == before

    docker([*_compose_argv(compose_file), "down"])
    docker(up)
    assert _old_volumes(docker)["postgres"] != first
    assert _figures(docker)["postgres"] == "postgres"  # a fresh, empty cluster
    assert "./base/osprey" in docker.volumes[first]  # the data, unattached


def test_the_stand_in_postgres_refuses_a_data_directory_with_the_wrong_owner_or_mode(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    docker, _ = old_deployment
    postgres = docker.container_of("postgres")
    tree = docker.tree(postgres, "/var/lib/postgresql/data")
    docker(["docker", "stop", postgres.id])
    tree["."] = Entry(0, 0, 0o700, "directory")
    code, said = docker(["docker", "start", postgres.id])
    assert code != 0 and "wrong ownership" in said
    tree["."] = Entry(999, 999, 0o755, "directory")
    code, said = docker(["docker", "start", postgres.id])
    assert code != 0 and "invalid permissions" in said
    tree["."] = Entry(999, 999, 0o750, "directory")
    assert docker(["docker", "start", postgres.id])[0] == 0


# The move ---------------------------------------------------------------------------------------


def test_the_move_keeps_every_stores_data_with_owners_and_modes(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    docker, compose_file = old_deployment
    before, old = _figures(docker), _old_volumes(docker)
    original = {k: _listing(docker.volumes[v]) for k, v in old.items()}
    said: list[str] = []
    moved = store_volumes.move(compose_file, run=docker, say=said.append, sleep=lambda _s: None)

    assert moved.services == ["postgres", "arcadedb", "valkey", "opensearch"]
    for service, path, volume in (
        ("postgres", "/var/lib/postgresql/data", "postgres-data"),
        ("arcadedb", "/home/arcadedb/databases", "arcadedb-databases"),
        ("arcadedb", "/home/arcadedb/config", "arcadedb-config"),
        ("valkey", "/data", "valkey-data"),
        ("opensearch", OPENSEARCH_DATA, "opensearch-data"),
    ):
        assert docker.container_of(service).mounts[path] == ("volume", f"{PROJECT}_{volume}")
    docker([*_compose_argv(compose_file), "up", "-d", "--wait"])
    assert _figures(docker) == before
    assert _listing(docker.volumes[f"{PROJECT}_postgres-data"]) == original["postgres"]
    assert _listing(docker.volumes[f"{PROJECT}_arcadedb-config"]) == original["arcadedb-config"]
    # The old volumes are left, with their data, and named in the words with how to remove them.
    for name in old.values():
        assert name in docker.volumes and name in moved.left
    assert f"docker volume rm {' '.join(moved.left)}" in "\n".join(said)


def test_after_the_move_a_new_container_keeps_the_data(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    """What the move is for: `down` then `up` (or `uninstall --keep-data` then an install) no longer
    starts the stores empty."""
    docker, compose_file = old_deployment
    before = _figures(docker)
    store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    docker([*_compose_argv(compose_file), "down"])
    docker([*_compose_argv(compose_file), "up", "-d", "--wait"])
    assert _figures(docker) == before


def test_a_second_move_does_nothing(old_deployment: tuple[FakeDocker, Path]) -> None:
    docker, compose_file = old_deployment
    store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    docker.calls.clear()
    said: list[str] = []
    moved = store_volumes.move(compose_file, run=docker, say=said.append, sleep=lambda _s: None)
    assert moved.services == [] and said == []
    assert {call[1] for call in docker.calls} <= {"ps", "inspect"}, "it only looked"


def test_a_new_install_has_nothing_to_move(tmp_path: Path) -> None:
    compose_file = _write_compose(tmp_path, named=True)
    docker = FakeDocker(compose_file)
    assert store_volumes.move(compose_file, run=docker, say=_quiet).services == []
    assert {call[1] for call in docker.calls} == {"ps"}


def test_a_copy_that_loses_the_top_folders_owner_is_refused_before_postgres_sees_it(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    """A copy that does not keep the data directory's own owner and mode (as `cp -r` would not) is
    caught by the check, before PostgreSQL is ever started on it — which would refuse it, as the
    stand-in's own test shows."""
    docker, compose_file = old_deployment
    old = _old_volumes(docker)
    docker.lose_top_owner = True
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert not refused.value.started
    assert "is not the same as the original" in refused.value.why
    assert f"{PROJECT}_postgres-data" not in docker.volumes
    assert docker.container_of("postgres").mounts["/var/lib/postgresql/data"] == (
        "volume",
        old["postgres"],
    )


def test_a_failed_copy_leaves_the_old_volume_and_removes_the_new_one(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    docker, compose_file = old_deployment
    before, old = _figures(docker), _old_volumes(docker)
    original = _listing(docker.volumes[old["postgres"]])
    docker.fail_copy = True
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert not refused.value.started and refused.value.made == []
    assert "No space left on device" in refused.value.why
    assert old["postgres"] in refused.value.words()
    assert _listing(docker.volumes[old["postgres"]]) == original
    assert not [
        n for n in docker.volumes if n.startswith(f"{PROJECT}_") and n != f"{PROJECT}_osprey-data"
    ]
    # Nothing was recreated: the old version's own `up` finds every store on its data.
    old_compose = _write_compose(compose_file.parent, named=False)
    docker.fail_copy = False
    docker([*_compose_argv(old_compose), "up", "-d", "--wait"])
    assert _figures(docker) == before
    # And the next try moves it.
    _write_compose(compose_file.parent, named=True)
    store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    docker([*_compose_argv(compose_file), "up", "-d", "--wait"])
    assert _figures(docker) == before


def test_opensearch_with_an_index_of_its_own_is_not_moved(tmp_path: Path) -> None:
    compose_file = _write_compose(tmp_path, named=False)
    docker = FakeDocker(compose_file)
    docker([*_compose_argv(compose_file), "up", "-d", "--wait"])
    _seed(docker, index="someones-index")
    _write_compose(tmp_path, named=True)
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert "someones-index" in refused.value.why
    assert OPENSEARCH_DATA not in docker.container_of("opensearch").mounts


def test_a_named_volume_already_holding_data_is_not_overwritten(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    docker, compose_file = old_deployment
    docker.volumes[f"{PROJECT}_valkey-data"] = {
        "./dump.rdb": Entry(999, 999, 0o644, "regular file", b"{}")
    }
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert f"{PROJECT}_valkey-data hold data" in refused.value.why
    assert not any(call[1] in ("stop", "run") and "-c" in call and store_volumes._COPY in call
                   for call in docker.calls)  # fmt: skip


def test_a_store_that_answers_differently_on_its_named_volume_fails_after_starting(
    old_deployment: tuple[FakeDocker, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Started on the named volume and another figure: `started` is set, so `update` restores its
    backup, and the old volume is named."""
    docker, compose_file = old_deployment
    real = docker._exec
    seen: dict[str, int] = {}

    def drifting(container: Container, command: str) -> tuple[int, str]:
        code, said = real(container, command)
        if container.service == "arcadedb":
            seen["n"] = seen.get("n", 0) + 1
            if seen["n"] > 1:
                return code, json.dumps({"result": []})
        return code, said

    monkeypatch.setattr(docker, "_exec", drifting)
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert refused.value.started
    assert f"{PROJECT}_arcadedb-databases" in refused.value.made
    assert "no databases" in refused.value.why


def test_the_command_says_what_failed_and_exits_one(
    old_deployment: tuple[FakeDocker, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    docker, compose_file = old_deployment
    docker.fail_copy = True
    monkeypatch.setattr(store_volumes, "_subprocess", docker)
    assert store_volumes.main([str(compose_file)]) == 1
    err = capsys.readouterr().err
    assert "could not be moved to named volumes" in err and "The deployment is stopped" in err
