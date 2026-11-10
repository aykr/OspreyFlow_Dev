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

**As found on the first server, a second time (4 November 2026; Amendment 35 point 7).** The
stand-in had given Valkey's image a `VOLUME /data`, as Redis's has; the server's `docker inspect`
showed Valkey 8.0 with **no mount at all**, its data in its container's layer, and the move refused
every deployment there. The stand-in now has Valkey's data in its layer, lost when its container is
replaced — `test_the_stand_in_valkey_keeps_its_data_in_its_container`. And a refused `apply` left
the compose file naming the new volumes, so `start` brought the stores up on fresh, empty ones, as
Compose makes a named volume that does not exist —
`test_the_stand_in_compose_gives_a_named_volume_that_is_not_there_empty`, and the refusals driven
through the real `start --build` then `start` —
`test_a_refused_move_leaves_the_files_as_they_were_and_start_runs_on_the_old_data`.
"""

from __future__ import annotations

import hashlib
import json
import re
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

#: Each image's `VOLUME` lines, as the real images declare them; OpenSearch's and Valkey 8.0's
#: declare none (Valkey's measured on the first server: `docker inspect` showed it with no mount).
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
    "valkey/valkey:8.0": {"id": "sha256:valkey", "volumes": []},
    "opensearchproject/opensearch:2.17.1": {"id": "sha256:search", "volumes": []},
    "osprey/api:local": {"id": "sha256:api", "volumes": []},
}
SERVICE_OF_IMAGE = {
    "sha256:pg": "postgres", "sha256:arcade": "arcadedb", "sha256:valkey": "valkey",
    "sha256:search": "opensearch", "sha256:api": "api",
}  # fmt: skip
OPENSEARCH_DATA = "/usr/share/opensearch/data"
#: The image each store's service runs, whatever the compose file spells it (the real render pins
#: by digest); any other service runs an image with no `VOLUME` and no data of its own here.
IMAGE_OF_SERVICE = {
    "postgres": "postgres:16.4", "arcadedb": "arcadedata/arcadedb:26.10.1",
    "valkey": "valkey/valkey:8.0", "opensearch": "opensearchproject/opensearch:2.17.1",
    "api": "osprey/api:local",
}  # fmt: skip
#: Where each store keeps what it initialises at its first start.
DATA_PATHS = {
    "postgres": ["/var/lib/postgresql/data"], "arcadedb": ["/home/arcadedb/databases"],
    "valkey": ["/data"], "opensearch": [OPENSEARCH_DATA],
}  # fmt: skip


def _image_spec(service: str) -> dict[str, Any]:
    known = IMAGE_OF_SERVICE.get(service)
    return IMAGES[known] if known else {"id": f"sha256:{service}", "volumes": []}


@dataclass
class Container:
    id: str
    service: str
    image: str  # its ID
    mounts: dict[str, tuple[str, str]]  # destination -> ("volume", name) | ("bind", folder)
    config: str  # what Compose would compare: the service's stanza as written
    layer: dict[str, Tree] = field(default_factory=dict)
    running: bool = False
    oneoff: bool = False  # made by `compose run`, not the service's own


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
        #: Images committed from a container: its service and its layer, as it was.
        self.committed: dict[str, dict[str, Any]] = {}
        #: Knobs: a copy that stops part way (every copy, or one service's); a copy that loses the
        #: top folder's owner and mode.
        self.fail_copy: bool | str = False
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
        found = [c for c in self.containers.values() if c.service == service and not c.oneoff]
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
        for path in DATA_PATHS.get(container.service, []):
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

    def _mounts(self, project: str, stanza: dict[str, Any]) -> dict[str, tuple[str, str]]:
        """The stanza's own mounts. **A named volume that is not there is made, empty**, as Compose
        makes it: what put the stores on fresh volumes on the first server."""
        mounts: dict[str, tuple[str, str]] = {}
        for mount in stanza.get("volumes") or []:
            source, _, rest = str(mount).partition(":")
            destination = rest.split(":")[0]
            if source.startswith(("/", ".")):
                mounts[destination] = ("bind", source)
            else:
                full = f"{project}_{source}"
                self.volumes.setdefault(full, {})
                mounts[destination] = ("volume", full)
        return mounts

    def _up(self, document: dict[str, Any], names: list[str]) -> tuple[int, str]:
        project = document["name"]
        for name in names or list(document["services"]):
            stanza = document["services"][name]
            image = _image_spec(name)["id"]
            config = json.dumps(stanza, sort_keys=True)
            current = [c for c in self.containers.values() if c.service == name and not c.oneoff]
            old = current[0] if current else None
            if old is not None and old.config == config:
                code, said = self._start(old)
                if code:
                    return code, said
                continue
            mounts = self._mounts(project, stanza)
            for path in IMAGES_BY_ID.get(image, {"volumes": []})["volumes"]:
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

    def _compose_run(self, document: dict[str, Any], argv: list[str]) -> tuple[int, str]:
        """`compose run -d --no-deps --name N service`: a new container of the service's own
        definition, apart from the service's own (fresh anonymous volumes, no carry-over)."""
        name, service = argv[argv.index("--name") + 1], argv[-1]
        if name in self.containers:
            return 1, f'Conflict. The container name "/{name}" is already in use'
        stanza = document["services"][service]
        spec = _image_spec(service)
        mounts = self._mounts(document["name"], stanza)
        for path in spec["volumes"]:
            mounts.setdefault(path, ("volume", self._fresh_volume()))
        container = Container(name, service, spec["id"], mounts,
                              json.dumps(stanza, sort_keys=True), oneoff=True)  # fmt: skip
        self.containers[name] = container
        return self._start(container)

    def compose(self, argv: list[str]) -> tuple[int, str]:
        document = self._compose_document(argv)
        verb = argv[argv.index("-f") + 2]
        if verb == "up":
            names = [a for a in argv[argv.index("up") + 1 :] if not a.startswith("-")
                     and a != "never"]  # fmt: skip
            return self._up(document, names)
        if verb == "run":
            return self._compose_run(document, argv)
        if verb == "down":
            for container in list(self.containers.values()):
                del self.containers[container.id]
            return 0, ""
        if verb == "build":
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
            oneoff = next((f.rsplit("=", 1)[1] for f in filters if ".oneoff=" in f), None)
            found = [
                c.id for c in self.containers.values()
                if (service is None or c.service == service)
                and (oneoff is None or str(c.oneoff) == oneoff)
                and ("-a" in argv or c.running)
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
            missing = [name for name in argv[2:] if name not in self.containers]
            for name in argv[2:]:
                if name in self.containers:
                    self.containers[name].running = False
            return (1, f"No such container: {missing[0]}") if missing else (0, "")
        if verb == "rm":
            name = argv[-1]
            gone = self.containers.pop(name, None)
            if gone is None:
                return 1, f"No such container: {name}"
            if "-v" in argv:  # its anonymous volumes go with it
                for kind, source in gone.mounts.values():
                    if kind == "volume" and source in self.anonymous:
                        self.volumes.pop(source, None)
            return 0, name
        if verb == "commit":
            container = self.containers[argv[2]]
            self.committed[argv[3]] = {
                "service": container.service,
                "layer": {path: {p: Entry(**vars(e)) for p, e in tree.items()}
                          for path, tree in container.layer.items()},
            }  # fmt: skip
            return 0, "sha256:committed"
        if verb == "image" and argv[2] == "rm":
            return (0, "") if self.committed.pop(argv[3], None) else (1, "No such image")
        if verb == "exec":
            if argv[2] not in self.containers:
                return 1, f"No such container: {argv[2]}"
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
        image = argv[argv.index("-c") - 1]
        committed = self.committed.get(image)
        assert image in IMAGES_BY_ID or committed is not None, (
            "a one-shot runs a store's image by ID, or one committed from its container"
        )
        service = committed["service"] if committed else SERVICE_OF_IMAGE.get(image)

        def folder(path: str) -> Tree:
            """A path in the one-shot: a mount, or else the image's own layer (an image committed
            from a container has that container's; any other has nothing there)."""
            if path in mounts:
                return mounts[path]
            return committed["layer"].get(path, {}) if committed else {}

        if script == "ls -A /to":
            return 0, "\n".join(p for p in mounts["/to"] if p != ".")
        if script == store_volumes._LISTING:
            return 0, _listing(folder(argv[-1]))
        if script == store_volumes._COPY:
            source, target = folder(argv[-1]), mounts["/to"]
            if [p for p in target if p != "."]:
                return 3, "the named volume is not empty"
            items = sorted(source.items())
            if self.fail_copy is True or self.fail_copy == service:
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
    """The anonymous volume each store's data is in now (Valkey's is in its container)."""
    return {
        "postgres": docker.container_of("postgres").mounts["/var/lib/postgresql/data"][1],
        "arcadedb": docker.container_of("arcadedb").mounts["/home/arcadedb/databases"][1],
        "arcadedb-config": docker.container_of("arcadedb").mounts["/home/arcadedb/config"][1],
    }


def _up(docker: FakeDocker, compose_file: Path) -> None:
    """The caller's own `up`, after the move."""
    assert docker([*_compose_argv(compose_file), "up", "-d", "--wait"])[0] == 0


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


def test_the_stand_in_valkey_keeps_its_data_in_its_container(tmp_path: Path) -> None:
    """Valkey 8.0's image declares no `VOLUME` (the first server's `docker inspect`: no mount):
    `/data` is in the container's own layer, kept across a stop and start, and gone when the
    container is replaced."""
    compose_file = _write_compose(tmp_path, named=False)
    docker = FakeDocker(compose_file)
    _up(docker, compose_file)
    _seed(docker)
    valkey = docker.container_of("valkey")
    assert "/data" not in valkey.mounts
    before = _figures(docker)["valkey"]
    docker(["docker", "stop", valkey.id])
    docker(["docker", "start", valkey.id])
    assert _figures(docker)["valkey"] == before
    docker([*_compose_argv(compose_file), "down"])
    _up(docker, compose_file)
    assert _figures(docker)["valkey"] == "# Keyspace\n"  # a new container, empty


def test_the_stand_in_compose_gives_a_named_volume_that_is_not_there_empty(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    """What put the stores on empty volumes on the first server: the compose file naming the
    volumes, and an `up` with no move before it. Compose makes each, empty, and the stores start
    on it — PostgreSQL a fresh cluster — with their data left where it was."""
    docker, compose_file = old_deployment
    old = _old_volumes(docker)
    _up(docker, compose_file)
    assert docker.container_of("postgres").mounts["/var/lib/postgresql/data"] == (
        "volume", f"{PROJECT}_postgres-data",
    )  # fmt: skip
    assert _figures(docker)["postgres"] == "postgres"
    assert _figures(docker)["valkey"] == "# Keyspace\n"
    assert "./base/osprey" in docker.volumes[old["postgres"]]


# The move ---------------------------------------------------------------------------------------


def test_the_move_keeps_every_stores_data_with_owners_and_modes(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    docker, compose_file = old_deployment
    before, old = _figures(docker), _old_volumes(docker)
    original = {k: _listing(docker.volumes[v]) for k, v in old.items()}
    original["valkey"] = _listing(docker.container_of("valkey").layer["/data"])
    said: list[str] = []
    moved = store_volumes.move(compose_file, run=docker, say=said.append, sleep=lambda _s: None)

    assert moved.services == ["postgres", "arcadedb", "valkey", "opensearch"]
    # The move replaced none of the deployment's containers: the caller's `up` does.
    assert docker.container_of("postgres").mounts["/var/lib/postgresql/data"] == (
        "volume", old["postgres"],
    )  # fmt: skip
    assert not [c for c in docker.containers.values() if c.oneoff], "the containers apart removed"
    assert docker.committed == {}, "the image committed from Valkey's container removed"
    _up(docker, compose_file)
    for service, path, volume in (
        ("postgres", "/var/lib/postgresql/data", "postgres-data"),
        ("arcadedb", "/home/arcadedb/databases", "arcadedb-databases"),
        ("arcadedb", "/home/arcadedb/config", "arcadedb-config"),
        ("valkey", "/data", "valkey-data"),
        ("opensearch", OPENSEARCH_DATA, "opensearch-data"),
    ):
        assert docker.container_of(service).mounts[path] == ("volume", f"{PROJECT}_{volume}")
    assert _figures(docker) == before
    assert _listing(docker.volumes[f"{PROJECT}_postgres-data"]) == original["postgres"]
    assert _listing(docker.volumes[f"{PROJECT}_arcadedb-config"]) == original["arcadedb-config"]
    assert _listing(docker.volumes[f"{PROJECT}_valkey-data"]) == original["valkey"]
    # The old volumes are left, with their data, and named in the words with how to remove them.
    for name in old.values():
        assert name in docker.volumes and name in moved.left
    assert f"docker volume rm {' '.join(moved.left)}" in "\n".join(said)
    assert "valkey: copying /data from valkey's container" in "\n".join(said)


def test_after_the_move_a_new_container_keeps_the_data(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    """What the move is for: `down` then `up` (or `uninstall --keep-data` then an install) no longer
    starts the stores empty."""
    docker, compose_file = old_deployment
    before = _figures(docker)
    store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    _up(docker, compose_file)
    docker([*_compose_argv(compose_file), "down"])
    _up(docker, compose_file)
    assert _figures(docker) == before


def test_a_second_move_does_nothing(old_deployment: tuple[FakeDocker, Path]) -> None:
    docker, compose_file = old_deployment
    store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    _up(docker, compose_file)
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
    assert refused.value.stopped
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
    _up(docker, compose_file)
    assert _figures(docker) == before


def test_valkeys_copy_from_its_container_that_fails_leaves_it_there_and_removes_the_rest(
    old_deployment: tuple[FakeDocker, Path],
) -> None:
    """Valkey's data, in its container, copied after the volumes' copies: a copy of it that fails
    removes every named volume the move filled, and the committed image, and leaves Valkey's own
    container — and its data — as they were."""
    docker, compose_file = old_deployment
    before = _figures(docker)
    docker.fail_copy = "valkey"
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert "valkey's container" in refused.value.words()
    assert docker.committed == {}
    assert not [n for n in docker.volumes if n.startswith(f"{PROJECT}_") and "osprey-data" not in n]
    old_compose = _write_compose(compose_file.parent, named=False)
    _up(docker, old_compose)
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


def test_a_store_that_answers_differently_on_its_named_volume_is_refused_and_nothing_is_left(
    old_deployment: tuple[FakeDocker, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Started on its named volume, apart, with another figure: refused like any other failure —
    the deployment's own containers were never replaced, so the old version's `up` (or `update`'s
    rollback) finds every store on its data, and the named volumes the move filled are gone."""
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
    before = _figures(docker)
    seen.clear()
    with pytest.raises(store_volumes.StoresNotMoved) as refused:
        store_volumes.move(compose_file, run=docker, say=_quiet, sleep=lambda _s: None)
    assert "no databases" in refused.value.why
    assert not [n for n in docker.volumes if n.startswith(f"{PROJECT}_") and "osprey-data" not in n]
    assert not [c for c in docker.containers.values() if c.oneoff]
    monkeypatch.setattr(docker, "_exec", real)
    _up(docker, _write_compose(compose_file.parent, named=False))
    assert _figures(docker) == before


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


# A refused move, through the real `start --build`, then `start` -----------------------------------


TOKENS = ":root { --brass: #c08a34; }\n"


def _old_rendered_deployment(repo: Path) -> Path:
    """A real `local-lite` render, as v0.4.10 left it: the stores with no named volume."""
    from harness.keycloak_theme import write_login_theme

    out = repo / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    for name, text in render(OspreyConfig(), allow_unpinned=True).artefacts.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(text, encoding="utf-8")
    # Every secret the compose file requires, held as an applied deployment holds them (`render`
    # writes none): refresh refuses one Compose could not interpolate (ADR-114 Amendment 39).
    required = set(
        re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?", (out / "compose.yaml").read_text())
    )
    held = "OSPREY_ARCADEDB_PASSWORD=pw\n" + "".join(
        f"{n}=held-{n.lower()}\n" for n in sorted(required - {"OSPREY_ARCADEDB_PASSWORD"})
    )
    (out / "deployment.env").write_text(
        (out / "deployment.env").read_text(encoding="utf-8") + held, encoding="utf-8"
    )
    tokens = repo / "apps" / "workspace" / "src" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(TOKENS, encoding="utf-8")
    write_login_theme(out, tokens_css=TOKENS)
    text = (out / "compose.yaml").read_text(encoding="utf-8")
    banner = text[: text.index("\nname:") + 1]
    document = yaml.safe_load(text)
    for service, paths in STORE_PATHS.items():
        stanza = document["services"][service]
        stanza["volumes"] = [v for v in stanza.get("volumes", []) if v.split(":")[1] not in paths]
        if not stanza["volumes"]:
            del stanza["volumes"]
    for volume in store_volumes.VOLUME_NAMES:
        document["volumes"].pop(volume, None)
    (out / "compose.yaml").write_text(banner + yaml.safe_dump(document, sort_keys=False),
                                      encoding="utf-8")  # fmt: skip
    return out


def _files(out: Path) -> dict[Path, tuple[bytes, int]]:
    return {p: (p.read_bytes(), p.stat().st_mode) for p in out.rglob("*") if p.is_file()}


@pytest.mark.parametrize("refusal", ["valkey", "copy", "opensearch"])
def test_a_refused_move_leaves_the_files_as_they_were_and_start_runs_on_the_old_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    """**ADR-114 Amendment 35 point 7, as found on the first server.** The move refused (there,
    Valkey's data in its container), but the compose file already named the new volumes, and a
    plain `start` brought the stores up on them, empty: PostgreSQL said `relation "investigations"
    does not exist`. Driven through the real `start --build` (`scripts.refresh`, which re-renders
    the compose file as `apply` does), refused three ways — Valkey's copy from its container, a
    volume's copy, OpenSearch holding an index of its own — then the command's `start` (the move's
    own command, then `up`): every file is as it was, byte for byte, and the stores come up on
    their old data."""
    from harness import ingest_uploads
    from scripts import refresh

    monkeypatch.setattr(ingest_uploads, "DOCKER_ENFORCES_OWNERSHIP", False)
    out = _old_rendered_deployment(tmp_path)
    compose_file = out / "compose.yaml"
    docker = FakeDocker(compose_file)
    _up(docker, compose_file)
    _seed(docker, index="someones-index" if refusal == "opensearch" else None)
    docker.fail_copy = {"valkey": "valkey", "copy": True}.get(refusal, False)
    before, files = _figures(docker), _files(out)
    old = _old_volumes(docker)

    def run(argv: Sequence[str]) -> None:
        code, said = docker(argv)
        if code != 0:
            raise refresh.RefreshFailed(said)

    with pytest.raises(refresh.RefreshFailed) as refused:
        refresh.refresh(tmp_path, run=run, register=lambda _argv: 0, docker=docker)
    assert _files(out) == files, "every file of the deployment's as it was"
    words = str(refused.value)
    assert "Nothing was removed" in words and "the deployment's files are as they were" in words
    assert "ospreyflow start starts it on that data" in words

    # `ospreyflow start`: the move's own command (nothing to move now), then `up`.
    docker.fail_copy = False
    monkeypatch.setattr(store_volumes, "_subprocess", docker)
    assert store_volumes.main([str(compose_file)]) == 0
    _up(docker, compose_file)
    assert _figures(docker) == before
    assert _old_volumes(docker) == old
    assert _files(out) == files
