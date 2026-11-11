"""Reading a SQL, API or JSON source into its one file in the dataset's folder (`06_DECISIONS.md`
ADR-140 Amendment 13; the redesign's phase 9).

A non-file source's `location` is its own file, `<ingest root>/uploaded/<dataset>/<name>.csv`. Each
read (at registration, then each *Refresh now*) writes that file whole with the rows it found, so
the source's pipelines run on it exactly as on any file: by its folder watch, by *Run now*, with the
run's raw rows, watermark and rule gate as built. An incremental SQL source's read takes only rows
past its cursor, so the file then holds only what is new.

**Secrets** are the deployment's: a connection names one, and its value is read here from
`OSPREY_CONNECTION_SECRET_<NAME>` (set in `deployment.env` by an operator), never stored, logged,
audited or sent back. **Egress**: an API connection reaches only hosts on `OSPREY_CONNECTOR_EGRESS`.
"""

from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import os
import re
import socket
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import botocore.session
import httpx
import pyarrow.fs as pa_fs
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from services.ingest.connectors import reads
from services.ingest.connectors.athena_connector import read_athena
from services.ingest.connectors.athena_connector import refused_request as athena_refused
from services.ingest.connectors.reads import (
    ConnectorRefused,
    ReadRows,
    check_egress,
    egress_allow_list,
    read_api,
    read_json,
    write_snapshot,
)
from services.ingest.connectors.s3_connector import ObjectStore, read_s3, refused_by_store
from services.ingest.connectors.sql_connector import (
    Connect,
    Reach,
    check_sql_connection,
    read_sql,
    tcp_reaches,
)

from schemas.sources import (
    ApiConnectionSettings,
    ApiRead,
    AthenaConnectionSettings,
    AthenaRead,
    Connection,
    ConnectionTest,
    IpAddress,
    JsonRead,
    Network,
    S3ConnectionSettings,
    S3Read,
    SourceTable,
    SqlConnectionSettings,
    SqlRead,
    address_is_inside,
    admitted_privately,
    carried_address,
    literal_ip,
    refuse_inside_host,
)

from .ingest_sources import UPLOAD_SUBDIR, ingest_root, is_inside

#: A non-file source's own name for its file: plain, lower case, no path.
SOURCE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def declared_secrets() -> set[str]:
    """The connection secrets the operator declares in `osprey.yaml`'s `connectors.secrets`, as
    `apply` renders them (`OSPREY_CONNECTOR_SECRETS`): the names the Conduit alone is given, every
    other service having each blanked (the orchestrator's review of Amendment 15, item 9)."""
    raw = os.environ.get("OSPREY_CONNECTOR_SECRETS", "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def secret_of(name: str | None) -> str | None:
    """A connection's secret, by its name, from the deployment's environment; only a name the
    operator declared, since only those are kept from every service but the Conduit."""
    if not name or name not in declared_secrets():
        return None
    return os.environ.get(f"OSPREY_CONNECTION_SECRET_{name}") or None


def resolve_host(host: str) -> list[str]:
    """What `host` resolves to now, in the resolver's own order, each address once: the order a
    client would try them in, IPv4 first where this machine has no IPv6 route (`AI_ADDRCONFIG`
    leaves out a family it cannot reach). Nothing when it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM, flags=socket.AI_ADDRCONFIG)
    except (OSError, UnicodeError):
        return []
    found: list[str] = []
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        if address not in found:
            found.append(address)
    return found


def cloud_s3_store(settings: S3ConnectionSettings) -> ObjectStore:
    """The bucket, through pyarrow's S3 filesystem signed in as the deployment's own cloud identity
    (L1.9; ADR-148): given no key, the SDK's own chain finds it (on the `cloud-platform` profile,
    the namespace's IAM role for service accounts). Never given one: no connection holds a key.
    Virtual-hosted, so the one host it reaches is `settings.host()`, the one the egress check
    names."""
    store: ObjectStore = pa_fs.S3FileSystem(
        region=settings.region, scheme="https", access_key=None, secret_key=None,
        allow_bucket_creation=False, allow_bucket_deletion=False,
        connect_timeout=10, request_timeout=30,
    )  # fmt: skip
    return store


def cloud_athena_client(settings: AthenaConnectionSettings) -> Any:
    """botocore's Athena client, signed in as the deployment's own cloud identity (no key given,
    so botocore's own chain finds it) and sent to `settings.host()` alone, the host the egress check
    names, whatever an environment variable says."""
    return botocore.session.get_session().create_client(
        "athena", region_name=settings.region, endpoint_url=f"https://{settings.host()}",
        config=BotoConfig(connect_timeout=10, read_timeout=30,
                          retries={"max_attempts": 3, "mode": "standard"}),
    )  # fmt: skip


@dataclass
class Readers:
    """What a read reaches, so a test can stand a fixture in for each (rule 15: each refuses what
    the real one refuses)."""

    sql_connect: Connect = asyncpg.connect
    #: Whether a checked address answers over plain TCP, before asyncpg is given it.
    sql_reach: Reach = tcp_reaches
    http_transport: httpx.AsyncBaseTransport | None = None
    allowed_hosts: Collection[str] | None = None
    #: Where a connection may reach (`refuse_host`). A fixture on this machine (the leased stack's
    #: Postgres) stands one in that admits it; that is named wherever it is used.
    host_check: Callable[[str, str, Collection[str]], object] | None = None
    #: A bucket and an Athena client for a cloud connection (L1.9). A test stands in SeaweedFS with
    #: its own test credentials, or the recorded Athena; a deployment's sign in as its own identity.
    s3_store: Callable[[S3ConnectionSettings], ObjectStore] = cloud_s3_store
    athena_client: Callable[[AthenaConnectionSettings], Any] = cloud_athena_client

    def hosts(self) -> Collection[str]:
        return egress_allow_list() if self.allowed_hosts is None else self.allowed_hosts

    def check(self, kind: str, host: str) -> list[str] | None:
        """The host refused, or the addresses it was checked at; `None` from a fixture's check."""
        if self.host_check is not None:
            self.host_check(kind, host, self.hosts())
            return None
        return refuse_host(kind, host, allowed_hosts=self.hosts())

    def sql_addresses(self, host: str) -> list[str] | None:
        """The addresses a SQL connection may go to, looked up and checked now, in the resolver's
        order; asyncpg is sent to them in turn, the name kept for TLS's name check, so DNS cannot
        change between the check and the connection (the lane review of ADR-140 Amendment 15, item
        3), and a host with an IPv6 address this machine cannot reach is still reached by its IPv4
        one (the orchestrator's review, item 4). A name that does not resolve is refused. A
        fixture's own check pins nothing."""
        addresses = self.check("sql", host)
        if addresses is None:
            return None
        if not addresses:
            raise ConnectorRefused(f"{host} does not resolve; nothing was read")
        return addresses

    def pin(self, url: str) -> list[str] | None:
        """The address an API request goes to, looked up and checked now; the request is sent to
        that address, the name kept for its Host header and TLS, so DNS cannot change between the
        check and the connection (the orchestrator's second review of L1.6). A fixture's own check
        pins nothing."""
        host = urlsplit(url).hostname or ""
        if self.host_check is not None:
            self.host_check("api", host, self.hosts())
            return None
        addresses = refuse_host("api", host, allowed_hosts=self.hosts())
        if not addresses:
            raise ConnectorRefused(f"{host} does not resolve; nothing was read")
        return addresses


#: The deployment's own names, each resolved to find an address the list must never admit
#: (ADR-140 Amendment 15 decision 2): its compose services (a cluster's resolve too, through the
#: pod's search domain), Docker's names for this machine and the cluster's API.
SELF_NAMES = (
    "postgres", "keycloak", "arcadedb", "valkey", "api", "worker", "workspace", "proxy",
    "superset", "opensearch", "litellm", "ner", "objectstore", "minio", "clickhouse",
    "report-sync", "harness", "host.docker.internal", "gateway.docker.internal",
    "kubernetes.default.svc",
)  # fmt: skip
_OWN_FOR_SECONDS = 60.0
_own_cache: tuple[float, list[Network]] | None = None
#: One lookup at a time when the cache expires, so concurrent reads (each on a worker thread) do not
#: each resolve every name and tie up the executor all `to_thread` work shares (the lane review of
#: L1.8).
_own_lock = threading.Lock()


def _v4(column: str) -> ipaddress.IPv4Address:
    """One of `/proc/net/route`'s columns: an IPv4 address in hexadecimal, little-endian."""
    return ipaddress.IPv4Address(int(column, 16).to_bytes(4, "little"))


def _proc_routes(
    ipv4: str = "/proc/net/route", ipv6: str = "/proc/net/ipv6_route"
) -> list[Network]:
    """The networks this container's interfaces reach directly, and each gateway (on Docker, the
    host itself), from the kernel's route tables; none where there are no such files (not Linux)."""
    found: list[Network] = []
    try:
        lines = Path(ipv4).read_text().splitlines()[1:]
    except OSError:
        lines = []
    for line in lines:
        cols = line.split()
        if len(cols) < 8:
            continue
        dest, gateway, mask = (_v4(cols[i]) for i in (1, 2, 7))
        if int(dest):
            found.append(ipaddress.ip_network(f"{dest}/{mask}", strict=False))
        if int(gateway):
            found.append(ipaddress.ip_network(f"{gateway}/32"))
    try:
        lines6 = Path(ipv6).read_text().splitlines()
    except OSError:
        lines6 = []
    for line in lines6:
        cols = line.split()
        if len(cols) < 10:
            continue
        net6 = ipaddress.IPv6Address(int(cols[0], 16))
        length, hop = int(cols[1], 16), ipaddress.IPv6Address(int(cols[4], 16))
        if length and not net6.is_link_local and not net6.is_multicast:
            found.append(ipaddress.ip_network(f"{net6}/{length}", strict=False))
        if int(hop) and not hop.is_link_local:
            found.append(ipaddress.ip_network(f"{hop}/128"))
    return found


def own_networks() -> list[Network]:
    """Where the deployment itself lives, which no operator's list admits (ADR-140 Amendment 15
    decision 2): this container's own networks and gateways, the addresses its own service names
    and Docker's names for this machine resolve to, and the cluster's API. Looked up at most once
    a minute; asked only when a listed entry would admit a private address."""
    global _own_cache
    cached = _own_cache
    if cached is not None and time.monotonic() - cached[0] < _OWN_FOR_SECONDS:
        return cached[1]
    with _own_lock:
        cached = _own_cache  # another thread may have looked them up while this one waited
        now = time.monotonic()
        if cached is not None and now - cached[0] < _OWN_FOR_SECONDS:
            return cached[1]
        found = _proc_routes()
        for name in SELF_NAMES:
            for address in resolve_host(name):
                ip = literal_ip(address)
                if ip is not None:
                    found.append(ipaddress.ip_network(ip))
        cluster = literal_ip(os.environ.get("KUBERNETES_SERVICE_HOST", ""))
        if cluster is not None:
            found.append(ipaddress.ip_network(cluster))
        _own_cache = (now, found)
        return found


def is_own(ip: IpAddress, networks: Collection[Network]) -> bool:
    """Whether `ip` (or the IPv4 address it carries) is in one of the deployment's own networks."""
    carried = carried_address(ip)
    return any(n.version == carried.version and carried in n for n in networks)


def private_allow_list() -> list[str]:
    """The private hosts and networks the operator admits the connectors to (ADR-140 Amendment 15),
    as `apply` renders them from `osprey.yaml`'s `connectors.private_hosts`."""
    raw = os.environ.get("OSPREY_CONNECTOR_PRIVATE", "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def refuse_host(
    kind: str,
    host: str,
    *,
    allowed_hosts: Collection[str] | None,
    private_hosts: Collection[str] | None = None,
) -> list[str]:
    """Where a SQL or API connection may reach (ADR-147 decision 2a's rule, with `map_admin`'s own
    lookups; the orchestrator's review of L1.6): never this machine, a dotless name of the
    deployment's own (`postgres`, `keycloak`), or an address that is loopback, private, link-local
    (a cloud's metadata service), reserved, unspecified or multicast, written in any form or
    resolved to now; and, with `allowed_hosts`, only a host the operator's egress allow-list names.
    A name resolving to a private address is admitted only where the operator's list
    (`private_hosts`, else `OSPREY_CONNECTOR_PRIVATE`) names it or a network it resolves into, and
    never to this machine or the metadata service (ADR-140 Amendment 15). Called when a connection
    is named and again before every connection or request, since DNS can change in between.
    Refused in words; nothing is read."""
    private = private_allow_list() if private_hosts is None else private_hosts
    try:
        refuse_inside_host(host)
    except ValueError as refused:
        raise ConnectorRefused(f"{refused}; nothing was read") from refused
    bare = host.strip().strip("[]").rstrip(".").lower()
    if allowed_hosts is not None:
        allowed = {h.strip().strip("[]").rstrip(".").lower() for h in allowed_hosts if h.strip()}
        if bare not in allowed:
            raise ConnectorRefused(
                f"{bare} is not on this deployment's egress allow-list: ask an operator to add it "
                f"(OSPREY_CONNECTOR_EGRESS); nothing was read ({kind} connection)"
            )
    if literal_ip(bare) is not None:
        return [bare]
    addresses = resolve_host(bare)
    for address in addresses:
        ip = literal_ip(address)
        if ip is None or (
            address_is_inside(ip)
            and not (admitted_privately(bare, ip, private) and not is_own(ip, own_networks()))
        ):
            raise ConnectorRefused(
                f"{bare} resolves inside this deployment or its network, and the operator has not "
                f"admitted it (osprey.yaml's connectors.private_hosts); nothing was read"
            )
    return addresses


def connection_host(settings: object) -> tuple[str, str] | None:
    """A connection's kind and the host it reaches, or `None` for files."""
    if isinstance(settings, SqlConnectionSettings):
        return "sql", settings.host
    if isinstance(settings, ApiConnectionSettings):
        return "api", urlsplit(settings.base_url).hostname or ""
    if isinstance(settings, S3ConnectionSettings | AthenaConnectionSettings):
        return settings.kind, settings.host()
    return None


def refuse_connection_hosts(settings: object) -> None:
    """At save: the host refused if it is, or resolves, inside the deployment. The allow-list is
    not asked yet: an operator may add the host after the administrator names it."""
    found = connection_host(settings)
    if found is not None:
        refuse_host(found[0], found[1], allowed_hosts=None)


def source_file(dataset_id: str, name: str, root: Path | None = None) -> Path:
    """Where a non-file source's reads land: its one file in the dataset's uploaded folder."""
    if not SOURCE_NAME.match(name):
        raise ConnectorRefused(
            "a source read through a connection is named in lower-case letters, digits, '-' and "
            "'_' only, so its file can be found"
        )
    root = root if root is not None else ingest_root()
    return root / UPLOAD_SUBDIR / dataset_id / f"{name}.csv"


#: A file that changed between listing and reading (removed, or replaced by a link).
_CHANGED = "a file changed while it was being read; nothing was read, so read again"


def _json_files(dataset_id: str, pattern: str, root: Path) -> list[tuple[str, bytes]]:
    """The dataset's files matching `pattern`, in name order. A dot-name is never read (`*`
    matches one in `fnmatch`, and a read's half-written `.read-*.tmp` is one), and a link is never
    followed, wherever it points (the orchestrator's review of Amendment 15, item 10: a link named
    `a.json` could reach a dot-file or another folder). The files' sizes are added up before any is
    opened, so a read past the byte cap opens none, and each is read against what room is left, so
    a file that grows after it was sized is stopped while it is read, never read whole (rule 2)."""
    matched: list[tuple[str, Path]] = []
    for folder in (root / dataset_id, root / UPLOAD_SUBDIR / dataset_id):
        if not folder.is_dir() or folder.is_symlink():
            continue
        for candidate in sorted(folder.iterdir(), key=lambda p: p.name):
            if candidate.name.startswith(".") or candidate.is_symlink():
                continue
            if (
                fnmatch.fnmatchcase(candidate.name, pattern)
                and is_inside(folder, candidate.resolve())
                and candidate.is_file()
            ):
                matched.append((candidate.name, candidate))
    over = ConnectorRefused(
        f"the JSON files come to more than {reads.MAX_BYTES} bytes, more than one read may "
        "take; nothing was read (rule 2)"
    )
    try:
        sizes = sum(path.stat().st_size for _name, path in matched)
    except OSError as exc:
        raise ConnectorRefused(_CHANGED) from exc
    if sizes > reads.MAX_BYTES:
        raise over
    found: list[tuple[str, bytes]] = []
    room = reads.MAX_BYTES
    for name, path in matched:
        try:
            with open(path, "rb", opener=_no_follow) as handle:
                body = handle.read(room + 1)
        except OSError as exc:
            raise ConnectorRefused(_CHANGED) from exc
        if len(body) > room:
            raise over
        room -= len(body)
        found.append((name, body))
    if not found:
        raise ConnectorRefused(
            f"no file in the dataset's folder matches {pattern!r}; nothing was written"
        )
    return found


def _no_follow(path: str, flags: int) -> int:
    """Opens `path` without following a link put there after it was listed."""
    return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0))


async def read_rows(
    source: SourceTable | Any,
    connection: Connection,
    *,
    dataset_id: str,
    cursor: str | None,
    readers: Readers,
    root: Path,
) -> ReadRows:
    """The rows one read of `source` finds, through its connection."""
    settings, read = connection.settings, source.read
    if isinstance(settings, SqlConnectionSettings) and isinstance(read, SqlRead):
        # Off the event loop: getaddrinfo blocks (the independent review of L1.6, in L1.8).
        addresses = await asyncio.to_thread(readers.sql_addresses, settings.host)
        if read.table.split(".")[0] not in settings.schemas:
            raise ConnectorRefused(
                f"the table {read.table} is not in a schema this connection may read "
                f"({', '.join(settings.schemas)}); nothing was read"
            )
        refresh = getattr(source, "refresh", None)
        watermark = (
            refresh.watermark_column
            if refresh is not None and refresh.mode == "incremental"
            else None
        )
        return await read_sql(
            settings, read, secret=secret_of(settings.secret), watermark=watermark,
            cursor=cursor if watermark else None, connect=readers.sql_connect,
            addresses=addresses, reach=readers.sql_reach,
        )  # fmt: skip
    if isinstance(settings, ApiConnectionSettings) and isinstance(read, ApiRead):
        return await read_api(
            settings, read, secret=secret_of(settings.secret), allowed_hosts=readers.hosts(),
            transport=readers.http_transport,
            before_request=readers.pin,
        )  # fmt: skip
    if connection.kind == "json" and isinstance(read, JsonRead):
        return read_json(_json_files(dataset_id, read.pattern, root), read)
    if isinstance(settings, S3ConnectionSettings) and isinstance(read, S3Read):
        # The host on the egress allow-list first (ADR-148 decision 7), then the read, each off the
        # event loop: both block.
        await asyncio.to_thread(readers.check, "s3", settings.host())
        return await asyncio.to_thread(read_s3, readers.s3_store(settings), settings, read)
    if isinstance(settings, AthenaConnectionSettings) and isinstance(read, AthenaRead):
        await asyncio.to_thread(readers.check, "athena", settings.host())
        client = readers.athena_client(settings)
        return await asyncio.to_thread(read_athena, client, settings, read)
    raise ConnectorRefused(
        f"the source's read is not one a {connection.kind} connection takes; nothing was read"
    )


async def read_into_file(
    source: SourceTable | Any,
    connection: Connection,
    *,
    dataset_id: str,
    name: str,
    cursor: str | None,
    readers: Readers,
    root: Path | None = None,
) -> tuple[ReadRows, Path]:
    """One read, landed as the source's file; returns the rows and the file. An incremental read
    adds its rows to the rows the file holds (none of which may have been loaded yet) and leaves the
    file as it was when it finds nothing; any other read is the file, whole (the lane review of
    L1.6)."""
    refuse_unbound(connection, dataset_id)
    root = root if root is not None else ingest_root()
    target = source_file(dataset_id, name, root)
    rows = await read_rows(source, connection, dataset_id=dataset_id, cursor=cursor,
                           readers=readers, root=root)  # fmt: skip
    return rows, write_snapshot(rows, target.parent, name, keep_earlier=incremental(source))


NOT_BOUND = (
    "this connection is not bound to this dataset: an administrator binds a connection to the "
    "datasets whose sources may read through it (Admin › Connections); nothing was read"
)


def refuse_unbound(connection: Connection, dataset_id: str) -> None:
    """A source reads only through a connection bound to its own dataset (the orchestrator's ruling
    on L1.6, rule 3). Every connector read passes here, in `read_into_file`."""
    if connection.kind != "files" and dataset_id not in connection.datasets:
        raise ConnectorRefused(NOT_BOUND)


def incremental(source: SourceTable | Any) -> bool:
    """Whether the source is a SQL table read past a watermark."""
    refresh = getattr(source, "refresh", None)
    return (
        isinstance(getattr(source, "read", None), SqlRead)
        and refresh is not None
        and refresh.mode == "incremental"
        and bool(refresh.watermark_column)
    )


async def check_connection(connection: Connection, readers: Readers) -> ConnectionTest:
    """*Test connection*: a SQL login signed in over TLS and found read-only; an API's host on the
    allow-list and its secret set. Nothing is read."""
    settings = connection.settings
    found = connection_host(settings)
    addresses: list[str] | None = None
    if found is not None:
        try:
            if found[0] == "sql":
                addresses = await asyncio.to_thread(readers.sql_addresses, found[1])
            else:
                await asyncio.to_thread(readers.check, *found)
        except ConnectorRefused as refused:
            return ConnectionTest(ok=False, words=str(refused))
    if isinstance(settings, SqlConnectionSettings):
        return await check_sql_connection(
            settings, secret=secret_of(settings.secret), connect=readers.sql_connect,
            addresses=addresses, reach=readers.sql_reach,
        )  # fmt: skip
    if isinstance(settings, ApiConnectionSettings):
        try:
            check_egress(settings.base_url, readers.hosts())
        except ConnectorRefused as refused:
            return ConnectionTest(ok=False, words=str(refused))
        if settings.auth == "bearer" and not secret_of(settings.secret):
            return ConnectionTest(
                ok=False,
                words=f"the secret {settings.secret} is not set in this deployment, or not "
                "declared in osprey.yaml's connectors.secrets",
            )
        return ConnectionTest(ok=True, words="The host is allowed and the secret is set.")
    if isinstance(settings, S3ConnectionSettings | AthenaConnectionSettings):
        try:
            return await asyncio.to_thread(_check_cloud, settings, readers)
        except ConnectorRefused as refused:
            return ConnectionTest(ok=False, words=str(refused))
    return ConnectionTest(ok=True, words="Files in the ingest folder: nothing to sign in to.")


def _check_cloud(
    settings: S3ConnectionSettings | AthenaConnectionSettings, readers: Readers
) -> ConnectionTest:
    """*Test connection* for S3 (the prefix listed, one level, nothing opened) and Athena (the
    workgroup asked for), signed in as the deployment's own identity (L1.9)."""
    if isinstance(settings, S3ConnectionSettings):
        base = f"{settings.bucket}/{settings.prefix}".rstrip("/")
        try:
            readers.s3_store(settings).get_file_info(
                pa_fs.FileSelector(base, recursive=False, allow_not_found=True)
            )
        except OSError as error:
            raise refused_by_store(error) from error
        return ConnectionTest(ok=True, words="The bucket answered, and its folder can be listed.")
    try:
        readers.athena_client(settings).get_work_group(WorkGroup=settings.workgroup)
    except (ClientError, BotoCoreError) as error:
        raise athena_refused(error) from error
    return ConnectionTest(ok=True, words="Athena answered, and the workgroup is there.")
