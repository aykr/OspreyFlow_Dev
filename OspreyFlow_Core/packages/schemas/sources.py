"""Connections and registered sources (`06_DECISIONS.md` ADR-140 decision 7; Amendments 4 and 13).

A **connection** is where sources are read from, owned by the deployment's administrators: `files`
(the ingest root, `OSPREY_INGEST_ROOT`), phase 9's `sql`, `api` and `json` (Amendment 13), and
L1.9's `s3` and `athena`, which hold no secret at all (each read signs in as the deployment's own
cloud identity, ADR-148). A SQL or API connection **names** its secret; the secret itself is the
deployment's (`OSPREY_CONNECTION_SECRET_<NAME>` in `deployment.env`), never stored here, in a
recipe or on the wire. A **source** is one table, file set or endpoint on a connection,
registered once for a dataset and carrying, at the source, its handling (marking, units, the
columns a row's marking is read from), its legal basis and its refresh policy. Every pipeline that
uses it inherits those: the Connect gate leaves the pipeline. Editing a source's governance is a
new version of the source, and every deployed pipeline using it then needs attention (Amendment 4,
the owner's ruling).

**A source's profile is never stored.** The profiler masks sample values by the reader's clearance,
so a stored profile would show one reader what was masked for another (rule 3): it is computed for
whoever asks (`GET …/sources/{id}/profile`), as Profile is today.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
from collections.abc import Collection
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ingest import check_source_declarations

ConnectionKind = Literal["files", "sql", "api", "json", "s3", "athena"]
#: A secret is named, never given: `OSPREY_CONNECTION_SECRET_<name>` holds it (Amendment 13).
SECRET_NAME = r"^[A-Z][A-Z0-9_]{0,63}$"
#: A SQL table, always schema-qualified: names, never an expression (rule 8). Its schema must be
#: one its connection names (the orchestrator's review of L1.6).
SQL_NAME = r"^[A-Za-z_][A-Za-z0-9_]{0,62}\.[A-Za-z_][A-Za-z0-9_]{0,62}$"
#: Schemas no connection may name: the server's own catalogue.
SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})
SQL_COLUMN = r"^[A-Za-z_][A-Za-z0-9_]{0,62}$"
#: Where a JSON document's records are: dotted names only, no index, filter or expression (rule 8).
#: A dataset's id, as a connection names the datasets it is bound to.
DATASET_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
RECORDS_PATH = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$"
#: Phase 3 records a refresh policy; phase 4 executes it (ADR-140 decision 15).
RefreshTrigger = Literal["manual", "watch"]
#: ADR-110 Amendment 6 point 1: how each read of the source is taken.
RefreshMode = Literal["snapshot", "incremental"]
#: On a full snapshot, a row the new file no longer carries: its elements kept, or withdrawn
#: (`GraphPort.withdraw_elements`, restored by the refresh's revert).
DroppedRows = Literal["keep", "withdraw"]


def literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """`host` read as an IP address in any form a resolver takes (as `services/api/map_admin`'s):
    dotted, IPv6, and the short, hexadecimal and whole-number IPv4 forms."""
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except OSError:
        return None


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _carried(ip: IpAddress) -> IpAddress:
    """An IPv6 address carrying an IPv4 one (mapped, NAT64 `64:ff9b::/96`, 6to4) as the IPv4
    address it carries; any other address as itself."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip in _NAT64:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if ip.sixtofour is not None:
            return ip.sixtofour
    return ip


#: `_carried`, for the Conduit's own-network check (ADR-140 Amendment 15).
carried_address = _carried


def address_is_inside(ip: IpAddress) -> bool:
    """Whether an address is anything but a global unicast one: loopback, private, shared
    (100.64.0.0/10), link-local (a cloud's metadata service), reserved, unspecified or multicast.
    An IPv6 address carrying an IPv4 one (mapped, NAT64 `64:ff9b::/96`, 6to4) is judged by the IPv4
    address it carries (the orchestrator's second review of L1.6). Python counts some reserved IPv6
    space as global, so reserved (`::/8`, which holds the deprecated IPv4-compatible `::/96`, such
    as `::7f00:1`) and site-local (`fec0::/10`) are refused by name (the orchestrator's review of
    Amendment 15, item 3)."""
    ip = _carried(ip)
    site_local = isinstance(ip, ipaddress.IPv6Address) and ip.is_site_local
    return not ip.is_global or ip.is_multicast or ip.is_reserved or site_local


#: The only ranges an operator's list may admit a connector to (ADR-140 Amendment 15): RFC 1918's
#: private networks, shared address space (RFC 6598) and unique local IPv6. Never loopback,
#: link-local (a cloud's metadata service), unspecified, multicast or reserved, whatever is listed.
ADMISSIBLE_PRIVATE = tuple(
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
)
#: Inside those ranges, the addresses no list admits (ADR-140 Amendment 15 decision 2): a cloud's
#: metadata services that are not link-local, AWS's IPv6 instance metadata service and resolver
#: (`fd00:ec2::254`, `fd00:ec2::253`) and Alibaba Cloud's metadata and internal services
#: (`100.100.100.200`). The deployment's own networks are refused beside these, by the Conduit
#: (`connector_reads.own_networks`), since only it can see them.
NEVER_ADMITTED = tuple(ipaddress.ip_network(n) for n in ("fd00:ec2::/32", "100.100.0.0/16"))
#: Names that are always the platform the deployment runs on, never a client's server: Docker's
#: names for this machine (`host.docker.internal`) and a cluster's own service names.
PLATFORM_SUFFIXES = (".localhost", ".docker.internal", ".svc", ".cluster.local")
_LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
_HOST_NAME = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(\.{_LABEL})+$")


def admissible_private(ip: IpAddress) -> bool:
    """Whether an address is one an operator's list may admit: in a private range, never this
    machine or the metadata service (ADR-140 Amendment 15)."""
    ip = _carried(ip)
    if any(ip.version == n.version and ip in n for n in NEVER_ADMITTED):
        return False
    return any(ip.version == n.version and ip in n for n in ADMISSIBLE_PRIVATE)


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def private_host_entry(entry: str) -> str | Network:
    """One entry of `osprey.yaml`'s `connectors.private_hosts` (ADR-140 Amendment 15): a host name
    in full (with a dot; never this machine or one of the deployment's own dotless services), or a
    network (or one address) wholly inside a private range. Anything else is refused in words."""
    bare = entry.strip().rstrip(".").lower()
    if "/" in bare or literal_ip(bare) is not None or ":" in bare:
        try:
            network = ipaddress.ip_network(bare.strip("[]"), strict=True)
        except ValueError as exc:
            raise ValueError(
                f"{entry!r} is neither a host name nor a network written as an address/length"
            ) from exc
        if not any(
            network.version == n.version and network.subnet_of(n)  # type: ignore[arg-type]
            for n in ADMISSIBLE_PRIVATE
        ):
            raise ValueError(
                f"{entry!r} is not wholly inside a private network (10.0.0.0/8, 172.16.0.0/12, "
                "192.168.0.0/16, 100.64.0.0/10 or fc00::/7): a connector is never admitted to "
                "this machine, a cloud's metadata service or a public address by this list"
            )
        if any(
            network.version == n.version and network.subnet_of(n)  # type: ignore[arg-type]
            for n in NEVER_ADMITTED
        ):
            raise ValueError(f"{entry!r} is a cloud's metadata service, which no list admits")
        return network
    if bare == "localhost" or bare.endswith(PLATFORM_SUFFIXES) or not _HOST_NAME.match(bare):
        raise ValueError(
            f"{entry!r} is not a host name in full (with a dot, no scheme, port or wildcard): "
            "the deployment's own services and this machine are never admitted"
        )
    return bare


def admitted_privately(host: str, ip: IpAddress, entries: Collection[str]) -> bool:
    """Whether the operator's list admits `host`, resolving to the private address `ip`: the host
    named in full, or `ip` inside a listed network; and `ip` always in a private range, so an entry
    that slipped past `osprey.yaml`'s check (a hand-edited `deployment.env`) admits nothing else.
    An entry that is not valid admits nothing."""
    if not admissible_private(ip):
        return False
    name = host.strip().rstrip(".").lower()
    carried = _carried(ip)
    for entry in entries:
        try:
            judged = private_host_entry(entry)
        except ValueError:
            continue
        if isinstance(judged, str):
            if judged == name:
                return True
        elif judged.version == carried.version and carried in judged:
            return True
    return False


def refuse_inside_host(host: str) -> str:
    """A connection's host as written, refused if it is this machine, a dotless name (one of the
    deployment's own services: `postgres`, `keycloak`), or an address that is loopback, private,
    link-local (a cloud's metadata service), reserved, unspecified or multicast (ADR-147 decision
    2a's rule, applied to connectors; the orchestrator's review of L1.6). What a name resolves to is
    checked by the Conduit when the connection is named and before every read."""
    bare = host.strip().rstrip(".").lower()
    if bare == "localhost" or bare.endswith(".localhost"):
        raise ValueError("the host is this machine; name the server's host in full")
    if bare.endswith(PLATFORM_SUFFIXES):
        raise ValueError(
            "the host is the platform this deployment runs on (Docker's or the cluster's own "
            "names), never a client's server"
        )
    ip = literal_ip(bare)
    if ip is not None:
        if address_is_inside(ip):
            raise ValueError("the host is inside this deployment or its network")
        return host
    if "." not in bare:
        raise ValueError("the host is a name with no dot, one of the deployment's own services")
    return host


#: The most a client's CA certificate may hold (a chain of a few certificates, in PEM).
MAX_CA_CERTIFICATE = 20_000


def check_ca_certificate(value: str | None) -> str | None:
    """A client's own CA certificate, in PEM, that a connection's server certificate is verified
    against beside the system's trust store (ADR-140 Amendment 15 decision 6): public, never a
    secret, and refused in words unless it loads as one or more certificates."""
    if value is None or not value.strip():
        return None
    pem = value.strip()
    if not pem.startswith("-----BEGIN CERTIFICATE-----") or "PRIVATE KEY" in pem:
        raise ValueError("a CA certificate is PEM text starting -----BEGIN CERTIFICATE-----")
    try:
        ssl.create_default_context(cadata=pem)
    except (ssl.SSLError, ValueError) as exc:
        raise ValueError("the CA certificate does not load as a certificate") from exc
    return pem


class SqlConnectionSettings(BaseModel):
    """A SQL database read through a **read-only** login over TLS (the redesign's phase 9). The
    login is checked read-only by *Test connection* and again before every read."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["sql"] = "sql"
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63, pattern=SQL_COLUMN)
    user: str = Field(min_length=1, max_length=63, pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,62}$")
    secret: str = Field(pattern=SECRET_NAME)
    #: TLS is always asked for, and by default the server's certificate and name are checked too
    #: (`require` alone would send the password to a server nobody verified).
    tls: Literal["require", "verify-full"] = "verify-full"
    #: A client's own CA, for a server whose certificate an internal CA signed (ADR-140 Amendment
    #: 15 decision 6); used only with `verify-full`.
    ca_certificate: str | None = Field(default=None, max_length=MAX_CA_CERTIFICATE)
    #: The schemas a source on this connection may read a table of; nothing else is read.
    schemas: list[Annotated[str, Field(pattern=SQL_COLUMN)]] = Field(
        default_factory=lambda: ["public"], min_length=1
    )

    @field_validator("host")
    @classmethod
    def _outside(cls, value: str) -> str:
        return refuse_inside_host(value)

    @field_validator("ca_certificate")
    @classmethod
    def _a_certificate(cls, value: str | None) -> str | None:
        return check_ca_certificate(value)

    @model_validator(mode="after")
    def _ca_only_to_verify(self) -> SqlConnectionSettings:
        if self.ca_certificate and self.tls != "verify-full":
            raise ValueError("a CA certificate is used only to verify: choose verify-full")
        return self

    @field_validator("schemas")
    @classmethod
    def _not_the_catalogue(cls, value: list[str]) -> list[str]:
        if SYSTEM_SCHEMAS & {v.lower() for v in value}:
            raise ValueError("a connection may not read the server's own catalogue")
        return value


class ApiConnectionSettings(BaseModel):
    """An HTTP API: its base URL (HTTPS only), how it is signed in to, and how it pages. Its host
    must be on the deployment's egress allow-list (`OSPREY_CONNECTOR_EGRESS`), which only an
    operator changes: a host not on it is refused in words that say whom to ask."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["api"] = "api"
    base_url: str = Field(
        max_length=500, pattern=r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[^\s?#]*)?$"
    )
    auth: Literal["none", "bearer"] = "none"
    secret: str | None = Field(default=None, pattern=SECRET_NAME)
    #: `page`: `?page=1, 2, …` until a page holds no records; `next_link`: each page names the next
    #: page's URL at `next_at`, which must stay on the same host.
    pagination: Literal["none", "page", "next_link"] = "none"
    page_param: str = Field(default="page", pattern=SQL_COLUMN)
    next_at: str | None = Field(default=None, pattern=RECORDS_PATH)
    #: A client's own CA, for an API whose certificate an internal CA signed (ADR-140 Amendment 15
    #: decision 6).
    ca_certificate: str | None = Field(default=None, max_length=MAX_CA_CERTIFICATE)

    @field_validator("ca_certificate")
    @classmethod
    def _a_certificate(cls, value: str | None) -> str | None:
        return check_ca_certificate(value)

    @field_validator("base_url")
    @classmethod
    def _outside(cls, value: str) -> str:
        from urllib.parse import urlsplit

        refuse_inside_host(urlsplit(value).hostname or "")
        return value

    @model_validator(mode="after")
    def _complete(self) -> ApiConnectionSettings:
        if self.auth == "bearer" and not self.secret:
            raise ValueError("a bearer sign-in needs the name of its secret")
        if self.pagination == "next_link" and not self.next_at:
            raise ValueError("next-link paging needs where each page names the next")
        return self


class JsonConnectionSettings(BaseModel):
    """JSON files in the ingest root: a source names its file pattern and where its records are."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["json"] = "json"


#: An AWS region's name (`eu-west-2`); the S3 and Athena hosts are made from it, never typed.
AWS_REGION = r"^[a-z]{2}(-gov)?-[a-z]+-[0-9]{1,2}$"
#: An S3 bucket's name, without a dot: a dotted name cannot be reached by its own host name over
#: verified TLS (`<bucket>.s3.<region>.amazonaws.com`), so it is refused, not reached another way.
S3_BUCKET = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"
#: A folder in a bucket: empty (the bucket's top), or names each ending in `/`. No `..`, no leading
#: `/`, no wildcard: a name, never a pattern or an expression (rule 8).
S3_FOLDER = r"^([A-Za-z0-9_][A-Za-z0-9_.=-]{0,199}/){0,20}$"
#: An Athena workgroup, catalog, database or table name.
ATHENA_NAME = r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"
ATHENA_TABLE = r"^[a-z0-9_]{1,128}\.[a-z0-9_]{1,128}$"
#: An `s3://bucket/folder/` location: a bucket's own name and a folder of names, never a pattern.
S3_LOCATION = r"^s3://" + S3_BUCKET[1:-1] + "/" + S3_FOLDER[1:]
#: A named query's id, as Athena makes them.
ATHENA_NAMED_QUERY = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def no_climbing(folder: str) -> str:
    """A folder refused if any of its names is `.` or `..`."""
    if any(part in {".", ".."} for part in folder.split("/")):
        raise ValueError("a folder may not climb out of the bucket")
    return folder


class S3ConnectionSettings(BaseModel):
    """An S3 bucket, read-only (L1.9; ADR-148 decisions 4 and 7). **No key and no secret**: the read
    signs in as the deployment's own cloud identity (on the `cloud-platform` profile, the
    namespace's IAM role), so nothing here could hold a credential. The host is made from the
    region and the bucket, never typed, and must be on the deployment's egress allow-list."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["s3"] = "s3"
    region: str = Field(pattern=AWS_REGION)
    bucket: str = Field(pattern=S3_BUCKET)
    #: The folder of the bucket a source on this connection may read under; the top when empty.
    prefix: str = Field(default="", max_length=1024, pattern=S3_FOLDER)

    @field_validator("prefix")
    @classmethod
    def _inside(cls, value: str) -> str:
        return no_climbing(value)

    @field_validator("bucket")
    @classmethod
    def _not_an_address(cls, value: str) -> str:
        if value.startswith("xn--") or value.endswith("-s3alias"):
            raise ValueError("a bucket's own name, not an access point's or an encoded one")
        return value

    def host(self) -> str:
        """The one host a read of this bucket reaches (virtual-hosted, as the SDK sends it)."""
        return f"{self.bucket}.s3.{self.region}.amazonaws.com"


class AthenaConnectionSettings(BaseModel):
    """Amazon Athena, read-only (L1.9): a workgroup, the catalog and the databases its sources may
    read. **No key and no secret**, as for S3. Athena writes each query's results to S3 itself: to
    the workgroup's own location, or to `results_location` when the workgroup names none."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["athena"] = "athena"
    region: str = Field(pattern=AWS_REGION)
    workgroup: str = Field(default="primary", pattern=ATHENA_NAME)
    catalog: str = Field(default="AwsDataCatalog", pattern=ATHENA_NAME)
    databases: list[Annotated[str, Field(pattern=r"^[a-z0-9_]{1,128}$")]] = Field(min_length=1)
    results_location: str | None = Field(
        default=None, max_length=1024, pattern=S3_LOCATION
    )

    def host(self) -> str:
        return f"athena.{self.region}.amazonaws.com"


ConnectionSettings = Annotated[
    SqlConnectionSettings
    | ApiConnectionSettings
    | JsonConnectionSettings
    | S3ConnectionSettings
    | AthenaConnectionSettings,
    Field(discriminator="kind"),
]


class Connection(BaseModel):
    id: str
    kind: ConnectionKind
    name: str
    created_by: str
    created_at: datetime
    #: `None` for `files`; the kind's own settings otherwise. Never a secret, only its name.
    settings: ConnectionSettings | None = None
    #: The datasets whose sources may read through it, by id, named by the administrator who made
    #: it (the orchestrator's ruling on L1.6, rule 3); empty for `files`, whose sources are each
    #: confined to their own dataset's folder instead.
    datasets: list[str] = Field(default_factory=list)


class ConnectionInput(BaseModel):
    kind: ConnectionKind = "files"
    name: str = Field(min_length=1, max_length=200)
    settings: ConnectionSettings | None = None
    datasets: list[Annotated[str, Field(pattern=DATASET_ID)]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _settings_of_its_kind(self) -> ConnectionInput:
        if self.kind == "files" and self.settings is not None:
            raise ValueError("a files connection has no settings: it is the ingest root")
        if self.kind != "files" and (self.settings is None or self.settings.kind != self.kind):
            raise ValueError(f"a {self.kind} connection needs its own settings")
        if self.kind == "files" and self.datasets:
            raise ValueError("a files connection names no dataset: each source keeps to its own")
        if self.kind != "files" and not self.datasets:
            raise ValueError(
                f"a {self.kind} connection names the datasets that may read through it"
            )
        return self


class ConnectionTest(BaseModel):
    """*Test connection*: whether it could be read, in words; nothing read is returned."""

    ok: bool
    words: str


class SqlRead(BaseModel):
    """A table (or view) of a SQL connection; the columns named, or all of them."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["sql"] = "sql"
    table: str = Field(pattern=SQL_NAME)
    columns: list[Annotated[str, Field(pattern=SQL_COLUMN)]] = Field(default_factory=list)

    @field_validator("table")
    @classmethod
    def _not_the_catalogue(cls, value: str) -> str:
        if value.split(".")[0].lower() in SYSTEM_SCHEMAS:
            raise ValueError("a source may not read the server's own catalogue")
        return value


class ApiRead(BaseModel):
    """A path under the connection's base URL, and where each page's records are."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["api"] = "api"
    path: str = Field(max_length=300, pattern=r"^/[A-Za-z0-9_./~-]*$")
    records_at: str | None = Field(default=None, pattern=RECORDS_PATH)

    @field_validator("path")
    @classmethod
    def _no_climbing(cls, value: str) -> str:
        if ".." in value.split("/"):
            raise ValueError("a path may not climb out of the base URL")
        return value


class JsonRead(BaseModel):
    """JSON files of the dataset's folder whose names match `pattern`, records at `records_at`."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["json"] = "json"
    pattern: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.*?\[\]-]+$")
    records_at: str | None = Field(default=None, pattern=RECORDS_PATH)

    @field_validator("pattern")
    @classmethod
    def _no_climbing(cls, value: str) -> str:
        if ".." in value or value.startswith("."):
            raise ValueError("a file pattern may not climb out of the folder or match hidden files")
        return value


class S3Read(BaseModel):
    """The CSV or Parquet objects in a folder of the connection's bucket, and every folder under it,
    read in key order. The folder is under the connection's own prefix (checked at the read)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["s3"] = "s3"
    folder: str = Field(default="", max_length=1024, pattern=S3_FOLDER)
    format: Literal["csv", "parquet"] = "csv"

    @field_validator("folder")
    @classmethod
    def _inside(cls, value: str) -> str:
        return no_climbing(value)


class AthenaRead(BaseModel):
    """A table of one of the connection's databases, read whole, or a named query saved in the
    connection's workgroup (a SELECT, checked before it runs); never a query written here
    (rule 8)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["athena"] = "athena"
    table: str | None = Field(default=None, pattern=ATHENA_TABLE)
    named_query: str | None = Field(default=None, pattern=ATHENA_NAMED_QUERY)

    @model_validator(mode="after")
    def _one_of_the_two(self) -> AthenaRead:
        if (self.table is None) == (self.named_query is None):
            raise ValueError("an Athena source reads a table or a named query, one of the two")
        return self


SourceRead = Annotated[
    SqlRead | ApiRead | JsonRead | S3Read | AthenaRead, Field(discriminator="kind")
]


class ConnectorRead(BaseModel):
    """One read of a non-file source (*Refresh now*, or its schedule): the rows it found and the
    file of the dataset's folder they were written to, which the source's pipelines then run on;
    or, when nothing new was found, no file, in words."""

    source_id: str
    file: str | None = None
    rows: int = 0
    #: For an incremental source: the highest watermark value read so far.
    cursor: str | None = None
    words: str


class SourceRefresh(BaseModel):
    """When the source is read again (ADR-140 decision 15). A file source's watch takes each new
    file whose whole name matches `pattern` (`*`, `?` and `[…]`, nothing else; ADR-110 Amendment
    4)."""

    trigger: RefreshTrigger = "manual"
    pattern: str | None = None
    mode: RefreshMode = "snapshot"
    dropped_rows: DroppedRows = "keep"
    #: For `incremental`: the column whose values only grow; rows at or below the highest value a
    #: run has kept for the source are not read.
    watermark_column: str | None = None
    #: Set by the Conduit, never by the body: the person who set the policy, whom a refresh runs
    #: as (ADR-110 Amendment 5 item 4), and whether it is paused, with why (Amendment 6 point 6).
    owner: str | None = None
    #: When the policy was set: a watched file counts only if it arrived after (Amendment 4).
    set_at: datetime | None = None
    paused: bool = False
    paused_reason: str | None = None

    @model_validator(mode="after")
    def _complete(self) -> SourceRefresh:
        if self.trigger == "watch" and not (self.pattern or "").strip():
            raise ValueError("a folder watch needs a filename pattern to watch for")
        if self.mode == "incremental" and not (self.watermark_column or "").strip():
            raise ValueError("an incremental refresh needs its watermark column")
        return self

    def policy(self) -> tuple[object, ...]:
        """What the person chose: an edit that changes it takes a new owner."""
        return (self.trigger, self.pattern, self.mode, self.dropped_rows, self.watermark_column)


class SourceTable(BaseModel):
    id: str
    dataset_id: str
    connection_id: str
    name: str
    #: For a `files` connection, the file's location as the ingest-root listing names it.
    location: str
    connector_profile: str
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    refresh: SourceRefresh = Field(default_factory=SourceRefresh)
    #: How a non-file connection's source is read (ADR-140 Amendment 13); `None` for a file.
    read: SourceRead | None = None
    #: A governance edit is a new version (`edit_governance`); the first is 1.
    version: int = 1
    created_by: str
    created_at: datetime
    updated_by: str | None = None
    updated_at: datetime | None = None
    #: ADR-140 Amendment 19: the classification this source's rows carry before a join when its
    #: table has no marking column of its own; `None` leaves such a table unmarked, never joined
    #: to a marked one. Set by a source approver (`SourceDefaultMarkingInput`), audited.
    default_marking: str | None = None
    default_marking_set_by: str | None = None
    default_marking_set_at: datetime | None = None


class SourceDefaultMarkingInput(BaseModel):
    """Declaring, changing or clearing (`None`) a source's default marking (ADR-140 Amendment 19):
    one of the handling scheme's classifications, never above the declarer's clearance or the
    deployment's highest marking, never below the source's own marking."""

    model_config = ConfigDict(extra="forbid")

    default_marking: str | None = Field(default=None, min_length=1, max_length=64)


class RegisterSourceInput(BaseModel):
    connection_id: str
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1)
    connector_profile: str = "generic-csv"
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    refresh: SourceRefresh = Field(default_factory=SourceRefresh)
    #: For a `sql`, `api` or `json` connection: what is read. `location` is then the source's own
    #: name for its files in the dataset's folder, where each read lands (ADR-140 Amendment 13).
    read: SourceRead | None = None

    @field_validator("handling")
    @classmethod
    def _declarations(cls, value: dict[str, Any]) -> dict[str, Any]:
        return check_source_declarations(value)


class SourceGovernanceInput(BaseModel):
    """An edit of a source's governance, audited; a new version of the source."""

    handling: dict[str, Any]
    legal_basis: str | None = None
    refresh: SourceRefresh | None = None

    @field_validator("handling")
    @classmethod
    def _declarations(cls, value: dict[str, Any]) -> dict[str, Any]:
        return check_source_declarations(value)


class PauseRefreshInput(BaseModel):
    """Pausing a source's refresh (ADR-110 Amendment 13): why, in words; none says who paused it."""

    reason: str | None = Field(default=None, max_length=500)


class SourceLineage(BaseModel):
    """A pipeline that uses a source: what the source page lists under *Lineage*."""

    recipe_id: str
    label: str
    version: int
    status: str


class GovernanceEdited(BaseModel):
    source: SourceTable
    #: The deployed pipelines now needing attention, by label.
    needs_attention: list[str] = Field(default_factory=list)


ALL_MODELS: list[type[BaseModel]] = [
    SqlConnectionSettings, ApiConnectionSettings, JsonConnectionSettings, ConnectionTest,
    S3ConnectionSettings, AthenaConnectionSettings,
    SqlRead, ApiRead, JsonRead, S3Read, AthenaRead, ConnectorRead,
    Connection, ConnectionInput, SourceRefresh, SourceTable, RegisterSourceInput,
    SourceGovernanceInput, SourceLineage, GovernanceEdited, SourceDefaultMarkingInput,
]  # fmt: skip
