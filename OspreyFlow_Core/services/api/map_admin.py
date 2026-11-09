"""*Admin › Maps*' service (`06_DECISIONS.md` ADR-147): the basemap providers, their keys, the local
basemap's state, and the prefetch areas run on a schedule. Behind `manage_geospatial` in every
route.

**Where things are kept** (ADR-147 decision 1). `osprey.yaml`'s `map:` is where a deployment starts.
The first change made in *Admin › Maps* writes the **maps file** (`maps.yaml`, in the Conduit's own
`map-settings` volume, `600`), which then replaces `osprey.yaml`'s `map:` whole, with the prefetch
areas, their schedule and each area's last run beside it. A provider's key typed in Admin goes to
the **map key file** beside it (`map-keys.yaml`, `600`), read by the tile proxy and by nothing else;
it is never in `osprey.yaml`, the maps file, a response, a log record, an audit row or a backup
(ADR-135 Amendment 2's rule, the owner's of 8 November: map keys follow the model keys' rule).

**One change at a time** across replicas and the command line (`_Exclusive`, an advisory lock on a
file beside the maps file), each change reading the file afresh under it, as *Models* does.

    python -m services.api.map_admin list                 # each provider, its tier and state
    python -m services.api.map_admin verify --by <who>
    python -m services.api.map_admin prefetch --by <who>
    python -m services.api.map_admin build <region> --by <who>

These are what `ospreyflow map list|verify|prefetch|build` run inside the Conduit's container, so
the command line, the set-up console and *Admin › Maps* are one code. Every answer is in fixed
words; the exit status is 0 on success, 1 when refused.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import asyncpg
import yaml
from pydantic import BaseModel, SecretStr, ValidationError

from schemas.deployment import TILES_CONTAINER_PATH
from schemas.map_admin import (
    MAX_AREA_TILES,
    AdminMapProvider,
    BasemapState,
    LocalBasemap,
    MapAdminAction,
    MapAdminEntry,
    MapKeyState,
    MapsAdminView,
    MapTier,
    PrefetchArea,
    PrefetchAreaView,
    PrefetchRun,
    PrefetchSchedule,
)
from schemas.mapconfig import MapConfig, MapProvider

from .model_admin import _Exclusive
from .tile_math import tile_range_for_bbox, tiles_in_range

log = logging.getLogger(__name__)

SETTINGS_FILE = "maps.yaml"
KEY_FILE = "map-keys.yaml"
DEFAULT_SETTINGS_DIR = "/run/osprey/map-settings"
#: The planetiler jar the build runs, in the deployment's tiles folder (placed there by
#: `ospreyflow map build --planetiler-jar`), so the Conduit image carries Java and no third-party
#: jar.
PLANETILER_JAR = "planetiler/planetiler.jar"
#: ADR-147 decision 3: the one writable folder in the Conduit's read-only tiles folder, where a
#: basemap built here and its extract are written (`harness/render.py`'s `TILES_BUILT_SUBDIR`).
BUILT_FOLDER = "built"
#: The fonts the bundled style names (`scripts/fetch_basemap_glyphs.STYLE_FONTS`).
GLYPH_FONTS: tuple[str, ...] = ("Noto Sans Regular",)


class MapAdminRefused(Exception):
    """A change *Maps* will not make, in fixed words that name no key and no address."""

    def __init__(self, words: str, status: int = 409) -> None:
        self.words = words
        self.status = status
        super().__init__(words)


# --- the files ----------------------------------------------------------------------------------


class MapSettings(BaseModel):
    """The maps file. `map` is `None` until *Admin › Maps* changes a provider or the default."""

    map: MapConfig | None = None
    areas: list[PrefetchArea] = []
    schedule: PrefetchSchedule = PrefetchSchedule()
    runs: list[PrefetchRun] = []
    #: The providers whose key is set in Admin, by id alone, so a restore can name each key to
    #: enter again (the key file is in no backup).
    keys_held: list[str] = []


def _write_private(path: Path, text: str, prefix: str) -> None:
    """Atomic, and `600` from the moment it exists (a temporary file renamed over the old)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=prefix, suffix=".yaml")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class MapSettingsFile:
    def __init__(self, folder: Path) -> None:
        self.path = folder / SETTINGS_FILE

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> MapSettingsFile:
        return cls(Path(environ.get("OSPREY_MAP_SETTINGS_DIR", DEFAULT_SETTINGS_DIR)))

    def stamp(self) -> float | None:
        try:
            return self.path.stat().st_mtime_ns / 1e9
        except FileNotFoundError:
            return None

    def load(self) -> MapSettings:
        if not self.path.is_file():
            return MapSettings()
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return MapSettings.model_validate(raw)

    def save(self, settings: MapSettings) -> None:
        text = yaml.safe_dump(settings.model_dump(mode="json", exclude_none=True), sort_keys=False)
        _write_private(self.path, text, ".maps-")


@dataclass(frozen=True)
class KeyRecord:
    key: SecretStr
    at: datetime
    by: str
    #: The address the key was entered for (`address_of`); a key is given to that address alone.
    address: str = ""


def address_of(provider: MapProvider) -> str:
    """Everything a tile URL is made from, so a key entered for one address is never given to
    another (ADR-147 decision 2): the source or endpoint, the service and layer, the variables the
    template is filled with and the WMTS key's parameter."""
    return json.dumps(
        [provider.source, provider.endpoint, provider.service, provider.layer,
         sorted(provider.variables.items()), provider.credential_param],
        sort_keys=True,
    )  # fmt: skip


class MapKeyFile:
    """Each provider's key, by its id. Read only by `MapAdmin.key_for` (the tile proxy's) and the
    view's `key_state`; never printed, logged or returned. Its `repr` is the provider ids alone."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / KEY_FILE

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> MapKeyFile:
        return cls(Path(environ.get("OSPREY_MAP_SETTINGS_DIR", DEFAULT_SETTINGS_DIR)))

    def load(self) -> dict[str, KeyRecord]:
        if not self.path.is_file():
            return {}
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return {
            str(pid): KeyRecord(
                key=SecretStr(str(r["key"])),
                at=datetime.fromisoformat(str(r["at"])),
                by=str(r["by"]),
                address=str(r.get("address", "")),
            )  # fmt: skip
            for pid, r in dict(raw).items()
        }

    def save(self, keys: Mapping[str, KeyRecord]) -> None:
        raw = {
            pid: {
                "key": r.key.get_secret_value(),
                "at": r.at.isoformat(),
                "by": r.by,
                "address": r.address,
            }  # fmt: skip
            for pid, r in keys.items()
        }
        _write_private(self.path, yaml.safe_dump(raw, sort_keys=True), ".map-keys-")


# --- the tile cache, as prefetch sees it -------------------------------------------------------


class TileStore(Protocol):
    def read(self, object_key: str, ttl_days: int) -> bytes | None: ...

    def write(self, object_key: str, data: bytes) -> None: ...


class ObjectTileStore:
    """The tile proxy's own cache in object storage (`tile_cache.py`)."""

    def __init__(self) -> None:
        from .tile_cache import tile_cache_storage_config

        self._storage = tile_cache_storage_config()

    def read(self, object_key: str, ttl_days: int) -> bytes | None:
        from .tile_cache import read_cached_tile

        return read_cached_tile(storage=self._storage, object_key=object_key, ttl_days=ttl_days)

    def write(self, object_key: str, data: bytes) -> None:
        from .tile_cache import write_cached_tile

        write_cached_tile(data, storage=self._storage, object_key=object_key)


# --- the audit ----------------------------------------------------------------------------------


class MapAdminAudit(Protocol):
    async def record(self, entry: MapAdminEntry) -> None: ...

    async def recent(self, limit: int = 200) -> list[MapAdminEntry]: ...


@dataclass
class InMemoryMapAdminAudit:
    entries: list[MapAdminEntry] = field(default_factory=list)

    async def record(self, entry: MapAdminEntry) -> None:
        self.entries.append(entry)

    async def recent(self, limit: int = 200) -> list[MapAdminEntry]:
        return list(reversed(self.entries))[:limit]


_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS map_admin_audit (
    id BIGSERIAL PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL,
    by TEXT NOT NULL,
    action TEXT NOT NULL,
    provider TEXT,
    changes JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome TEXT NOT NULL
);
"""


class PostgresMapAdminAudit:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresMapAdminAudit:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            await conn.execute(_AUDIT_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def record(self, entry: MapAdminEntry) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO map_admin_audit (at, by, action, provider, changes, outcome) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6)",
                entry.at, entry.by, entry.action, entry.provider, json.dumps(entry.changes),
                entry.outcome,
            )  # fmt: skip

    async def recent(self, limit: int = 200) -> list[MapAdminEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT at, by, action, provider, changes, outcome FROM map_admin_audit "
                "ORDER BY id DESC LIMIT $1",
                limit,
            )
        return [
            MapAdminEntry(
                at=r["at"],
                by=r["by"],
                action=r["action"],
                provider=r["provider"],
                changes=json.loads(r["changes"]),
                outcome=r["outcome"],
            )  # fmt: skip
            for r in rows
        ]


# --- words that never carry what was sent -------------------------------------------------------

#: A value that may be named in a refusal: shaped like a provider id, never like a key.
_NAMEABLE = re.compile(r"[a-z][a-z0-9_-]{0,47}")


def sent_values(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        return set().union(*(sent_values(v) for v in value.values()), set())
    if isinstance(value, (list, tuple, set)):
        return set().union(*(sent_values(v) for v in value), set())
    if isinstance(value, BaseModel):
        return sent_values(value.model_dump(mode="json"))
    return set()


def redacted(words: str, values: set[str]) -> str:
    """`words` with every sent value not shaped like an id replaced by "…", longest first."""
    for value in sorted(values, key=len, reverse=True):
        if value and not _NAMEABLE.fullmatch(value):
            words = words.replace(value, "…")
    return words


def refusal_words(invalid: ValidationError, sent: set[str]) -> str:
    words = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: "
        + str(e.get("msg", "")).removeprefix("Value error, ")
        for e in invalid.errors(include_input=False, include_context=False, include_url=False)
    )
    return redacted(words, sent)


# --- what a provider is -------------------------------------------------------------------------


def tier_of(provider: MapProvider) -> MapTier:
    """`00_ARCHITECTURE.md` §1.2's tiers, read off the provider: an OGC service is 4; a local file
    under the OSM licence is 1, any other local file 2; anything hosted (a provider's address or a
    profile) 3."""
    if provider.service is not None:
        return 4
    source = provider.source or ""
    if source.startswith("file://"):
        return 1 if provider.licence.id.upper().startswith("ODBL") else 2
    return 3


def area_tiles(area: PrefetchArea) -> int:
    """Every tile the area covers, every zoom counted."""
    total = 0
    for zoom in range(area.zoom_min, area.zoom_max + 1):
        x_min, x_max, y_min, y_max = tile_range_for_bbox(
            area.west, area.south, area.east, area.north, zoom
        )
        total += (x_max - x_min + 1) * (y_max - y_min + 1)
    return total


def _refused(words: str) -> MapAdminRefused:
    return MapAdminRefused(words, status=422)


def resolve_host(host: str) -> list[str]:
    """Every address `host` resolves to now, or none where it does not resolve (a test stands
    in)."""
    import socket

    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None)})
    except (OSError, UnicodeError):
        return []


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """`host` read as an IP address in any form a resolver takes: dotted, IPv6, and the short,
    hexadecimal and whole-number IPv4 forms (`127.1`, `0x7f.1`, `2130706433`)."""
    import socket

    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except OSError:
        return None


def _is_inside(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any((ip.is_loopback, ip.is_link_local, ip.is_private, ip.is_reserved,
                ip.is_unspecified, ip.is_multicast))  # fmt: skip


def host_inside(host: str) -> bool:
    """Whether `host` is, or now resolves to, an address inside the deployment or its network."""
    ip = _literal_ip(host)
    if ip is not None:
        return _is_inside(ip)
    resolved = [_literal_ip(a) for a in resolve_host(host)]
    return any(_is_inside(r) for r in resolved if r is not None)


def _checked_address(provider_id: str, address: str, *, resolve: bool = True) -> None:
    """An address *Admin › Maps* may give the Conduit (ADR-147 decision 2a): `file://` under the
    tiles folder, or `http(s)` to a host name outside the deployment — never a host or port the
    template fills in, `localhost`, an IP address in any form that is loopback, link-local (a
    cloud's metadata service), private or reserved, a name with no dot once a trailing one is
    dropped (a service of the deployment's own: `postgres.`, `keycloak`), a name that resolves to
    any of those now, credentials in the address, or a key typed into it. The host is looked up
    again before every fetch of a provider not exactly as `osprey.yaml` gives it (`host_inside`),
    since DNS can change in between."""
    from urllib.parse import parse_qsl, urlsplit

    where = f"The provider {_shown(provider_id)}'s address"
    if address.startswith("file://"):
        path = address.removeprefix("file://")
        if ".." in Path(path).parts or not path.startswith(f"{TILES_CONTAINER_PATH}/"):
            raise _refused(
                f"{where} is a local file outside the tiles folder ({TILES_CONTAINER_PATH})."
            )
        return
    raw = urlsplit(address)
    if raw.scheme not in ("http", "https"):
        raise _refused(f"{where} must be an https or http address, or a file in the tiles folder.")
    if "{" in raw.netloc or "}" in raw.netloc:
        raise _refused(f"{where} fills its host or port from the template; write them out.")
    if "{credential}" in raw.path or "{credential}" in raw.fragment:
        raise _refused(
            f"{where} carries its key outside the query; put {{credential}} in the query."
        )
    if raw.username or raw.password:
        raise _refused(
            f"{where} carries a user name or password; set a key in Admin › Maps instead."
        )
    for name, value in parse_qsl(raw.query, keep_blank_values=True):
        if re.search(r"key|token|secret|sig|password|auth", name, re.I) and value != "{credential}":
            raise _refused(
                f"{where} has a key typed into it ({_shown(name)}); write {{credential}} there and "
                "set the key with Enter key, so it is kept out of the address."
            )
    host = (raw.hostname or "").rstrip(".")
    try:
        raw.port
    except ValueError:
        raise _refused(f"{where} has a port that is not a number.") from None
    if host == "localhost" or host.endswith(".localhost"):
        raise _refused(f"{where} names this machine; name the provider's host in full.")
    if _literal_ip(host) is not None:
        if host_inside(host):
            raise _refused(
                f"{where} is inside this deployment or its network; name a host outside it."
            )
        return
    if "." not in host:
        raise _refused(
            f"{where} names a host inside this deployment (a name with no dot); name the "
            "provider's host in full."
        )
    if resolve and host_inside(host):
        raise _refused(
            f"{where} names a host that resolves inside this deployment or its network; name a "
            "host outside it."
        )


def admissible(provider: MapProvider, before: MapProvider | None) -> None:
    """What *Admin › Maps* may set (ADR-147 decision 2a). **An `env:` reference is the installer's
    alone**: one added or changed here would let a holder of `manage_geospatial` send any of the
    Conduit's own secrets (its database password, its token-exchange secret) to an address of their
    choosing, so a provider added here has none, and an edit keeps the one `osprey.yaml` gave. Its
    addresses are held to `_checked_address`. A key goes only to a provider the Conduit fetches."""
    kept = before.credential if before is not None else None
    if provider.credential != kept:
        raise _refused(
            "A provider's key is set in Admin › Maps with Enter key, never by naming one of the "
            "Conduit's settings here; an installer's reference in osprey.yaml stays as it is."
        )
    if kept is not None and before is not None and address_of(provider) != address_of(before):
        # The independent review's blocker: the installer's key is bound to the installer's
        # address as an Admin key is to its own (decision 2), so the edit is refused.
        raise _refused(
            "This provider's key comes from the installer's settings, so its address is changed "
            "in osprey.yaml, not here; or add a provider of your own and enter its key."
        )
    for address in (provider.source, provider.endpoint):
        if address is not None:
            _checked_address(provider.id, address)
    if provider.profile is not None:
        raise _refused("A ready-made provider profile is set in osprey.yaml, not here.")
    if provider.needs_key and provider.proxy == "none":
        raise _refused(
            "A provider that takes a key must be fetched by the Conduit: fetched by the browser, "
            "its key would be in every analyst's browser."
        )


def _container_file(source: str | None) -> Path | None:
    if source is None or not source.startswith("file://"):
        return None
    return Path(source.removeprefix("file://"))


def _now() -> datetime:
    return datetime.now(UTC)


# --- the service --------------------------------------------------------------------------------


class MapAdmin:
    def __init__(
        self,
        *,
        installed: MapConfig,
        settings_file: MapSettingsFile,
        key_file: MapKeyFile,
        audit: MapAdminAudit,
        tiles_root: Path = Path(TILES_CONTAINER_PATH),
        tile_store: Callable[[], TileStore] = ObjectTileStore,
        http_get: Callable[[str], Awaitable[bytes]] | None = None,
        now: Callable[[], datetime] = _now,
        java: Callable[[str], str | None] = shutil.which,
        tiles_per_second: float = 10.0,
    ) -> None:
        self._installed = installed
        self._file = settings_file
        self._keys = key_file
        self._audit = audit
        self._tiles_root = tiles_root
        self._tile_store = tile_store
        self._http_get = http_get
        self._now = now
        self._java = java
        #: ADR-147 decision 5: a run fetches at most this many tiles a second from a provider.
        self._pause = 1 / tiles_per_second
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self._stamp: float | None = None
        self._settings = MapSettings()
        self._exclusive = _Exclusive(settings_file.path.parent, ".maps.lock")
        self._running = asyncio.Lock()
        self._fresh()

    # --- reading --------------------------------------------------------------------------

    @property
    def tiles_root(self) -> Path:
        return self._tiles_root

    def _fresh(self) -> None:
        stamp = self._file.stamp()
        if stamp != self._stamp or stamp is None:
            try:
                self._settings = self._file.load()
            except (ValidationError, ValueError, OSError) as unreadable:
                # A restored or hand-edited maps file that does not validate must not take the map
                # away from every analyst: `osprey.yaml`'s is served, and the log says why.
                log.warning(
                    "the maps file %s cannot be read (%s); serving osprey.yaml's map",
                    self._file.path,
                    type(unreadable).__name__,
                )
                self._settings = MapSettings()
            self._stamp = stamp

    @property
    def settings(self) -> MapSettings:
        self._fresh()
        return self._settings

    def config(self) -> MapConfig:
        """What the map serves: the maps file's once *Admin › Maps* has changed it, else
        `osprey.yaml`'s; the maps file vetted as it is read (`_vetted`), whoever wrote it."""
        held = self.settings.map
        return self._vetted(held) if held is not None else self._installed

    def _vetted(self, held: MapConfig) -> MapConfig:
        """A maps file held to what *Admin › Maps* may name (ADR-147 decision 2a), since one
        restored or edited by hand never passed `admissible`. A provider exactly as `osprey.yaml`
        gives it is the installer's and stands. Any other: an `env:` reference stands only where
        `osprey.yaml` gives the same provider the same reference at the same address, and is
        otherwise removed; an address `admissible` would refuse leaves the provider out. Each is
        logged by its id."""
        installed = {p.id: p for p in self._installed.providers}
        kept: list[MapProvider] = []
        for provider in held.providers:
            theirs = installed.get(provider.id)
            if theirs is not None and theirs == provider:
                kept.append(provider)
                continue
            if provider.credential is not None and not (
                theirs is not None
                and theirs.credential == provider.credential
                and address_of(theirs) == address_of(provider)
            ):
                log.warning("maps file: provider %s's env: reference removed", provider.id)
                provider = provider.model_copy(update={"credential": None})
            try:
                for address in (provider.source, provider.endpoint):
                    if address is not None:
                        # No lookup here (every request reads the map); the fetch looks it up.
                        _checked_address(provider.id, address, resolve=False)
            except MapAdminRefused:
                log.warning("maps file: provider %s left out, its address refused", provider.id)
                continue
            kept.append(provider)
        if not kept:
            return self._installed
        ids = {p.id for p in kept}
        default = held.default if held.default in ids else kept[0].id
        return MapConfig(default=default, providers=kept)

    def installers(self, provider: MapProvider) -> bool:
        """Whether a provider is exactly as `osprey.yaml` gives it: the installer's choice, which
        may name an address inside its own network (a corporate WMTS), and is not looked up
        again."""
        return any(p == provider for p in self._installed.providers)

    def refuse_inside(self, provider: MapProvider) -> None:
        """Before a fetch for a provider *Admin › Maps* gave: its host looked up again, and refused
        in words if it now resolves inside the deployment (ADR-147 decision 2a)."""
        from urllib.parse import urlsplit

        if self.installers(provider):
            return
        for address in (provider.source, provider.endpoint):
            if address is None or address.startswith("file://"):
                continue
            host = (urlsplit(address).hostname or "").rstrip(".")
            if host_inside(host):
                raise MapAdminRefused(
                    f"The map provider {_shown(provider.id)}'s host is inside this deployment or "
                    "its network now, so its tiles are not fetched.",
                    status=502,
                )

    def provider(self, provider_id: str) -> MapProvider:
        found = next((p for p in self.config().providers if p.id == provider_id), None)
        if found is None:
            raise MapAdminRefused(f"There is no map provider {_shown(provider_id)}.", status=404)
        return found

    def key_for(self, provider_id: str) -> str | None:
        """The key set in *Admin › Maps* for a provider, for the tile proxy alone, and only while
        the provider's address is the one it was entered for."""
        record = self._keys.load().get(provider_id)
        if record is None:
            return None
        provider = next((p for p in self.config().providers if p.id == provider_id), None)
        if provider is None or record.address != address_of(provider):
            return None
        return record.key.get_secret_value()

    def _key_state(self, provider: MapProvider, keys: Mapping[str, KeyRecord]) -> MapKeyState:
        record = keys.get(provider.id)
        if record is not None and record.address == address_of(provider):
            return "set"
        if provider.credential is not None:
            return "env" if os.environ.get(provider.credential.removeprefix("env:")) else "none"
        return "none"

    def _state(
        self, provider: MapProvider, key_state: MapKeyState, moved: bool = False
    ) -> tuple[str, bool]:
        if provider.profile is not None:
            return (
                "A ready-made provider profile: the tile proxy does not serve profiles yet.",
                False,
            )
        local = _container_file(provider.source)
        if local is not None and provider.proxy == "none":
            if not local.is_file():
                return "Its local file is not built yet.", False
            return "Ready: a local file on this deployment.", True
        if provider.needs_key and key_state == "none":
            if moved:
                return "Its key was entered for another address: enter it again.", False
            return "Needs a key: none is set.", False
        if provider.proxy != "none":
            cached = " and cached" if provider.cache is not None else ""
            return f"Ready: fetched through the Conduit{cached}.", True
        return "Ready: fetched by the browser.", True

    def basemap(self) -> BasemapState:
        from scripts.build_local_basemap import GEOFABRIK_REGIONS

        basemaps: list[LocalBasemap] = []
        for provider in self.config().providers:
            local = _container_file(provider.source)
            if local is None:
                continue
            try:
                info = local.stat()
                basemaps.append(LocalBasemap(
                    provider_id=provider.id, file=local.name, built=True,
                    size_bytes=info.st_size,
                    built_at=datetime.fromtimestamp(info.st_mtime, UTC),
                ))  # fmt: skip
            except OSError:
                basemaps.append(LocalBasemap(provider_id=provider.id, file=local.name, built=False))
        fonts = [f for f in GLYPH_FONTS if (self._tiles_root / "fonts" / f / "0-255.pbf").is_file()]
        java = self._java("java") is not None
        jar = (self._tiles_root / PLANETILER_JAR).is_file()
        if java and jar:
            builder = "Ready: Java and the map builder are installed."
        elif not java:
            builder = "Java is not installed in the Conduit, so the map cannot be built here."
        else:
            builder = (
                "The map builder (planetiler) is not in the tiles folder. Run `ospreyflow map "
                "build <region> --planetiler-jar <path>` once to place it."
            )
        return BasemapState(
            basemaps=basemaps, glyphs_installed=len(fonts) == len(GLYPH_FONTS),
            glyph_fonts=list(GLYPH_FONTS), builder_ready=java and jar, builder_state=builder,
            regions=sorted(GEOFABRIK_REGIONS),
        )  # fmt: skip

    def next_run_at(self) -> datetime | None:
        settings = self.settings
        every = settings.schedule.every_hours
        if every is None or not settings.areas:
            return None
        last = max((r.at for r in settings.runs), default=None)
        return self._now() if last is None else last + timedelta(hours=every)

    def due(self) -> bool:
        at = self.next_run_at()
        return at is not None and at <= self._now()

    def view(self) -> MapsAdminView:
        config = self.config()
        keys = self._keys.load()
        providers = []
        for p in config.providers:
            key_state = self._key_state(p, keys)
            record = keys.get(p.id)
            words, ready = self._state(
                p, key_state, moved=record is not None and key_state != "set"
            )
            record = record if key_state == "set" else None
            providers.append(AdminMapProvider(
                provider=p, tier=tier_of(p), key_state=key_state, needs_key=p.needs_key,
                key_set_at=record.at if record else None, key_set_by=record.by if record else None,
                state=words, ready=ready,
            ))  # fmt: skip
        settings = self.settings
        runs = {r.area: r for r in settings.runs}
        return MapsAdminView(
            default=config.default,
            providers=providers,
            changed_in_admin=settings.map is not None,
            basemap=self.basemap(),
            areas=[
                PrefetchAreaView(area=a, tiles=area_tiles(a), last_run=runs.get(a.name))
                for a in settings.areas
            ],
            schedule=settings.schedule,
            next_run_at=self.next_run_at(),
        )

    async def history(self) -> list[MapAdminEntry]:
        return await self._audit.recent()

    # --- changing -------------------------------------------------------------------------

    async def _record(
        self, by: str, action: MapAdminAction, provider: str | None,
        changes: dict[str, dict[str, object]] | None = None, outcome: str = "done",
    ) -> None:  # fmt: skip
        await self._audit.record(MapAdminEntry(
            at=self._now(), by=by, action=action, provider=provider, changes=changes or {},
            outcome=outcome,
        ))  # fmt: skip

    def _note_keys(self, keys: Mapping[str, KeyRecord]) -> None:
        settings = self._file.load()
        self._file.save(settings.model_copy(update={"keys_held": sorted(keys)}))
        self._fresh()

    def _save_map(self, config: MapConfig) -> None:
        settings = self._file.load()
        self._file.save(settings.model_copy(update={"map": config}))
        self._fresh()

    def _validated(self, default: str, providers: list[MapProvider]) -> MapConfig:
        try:
            return MapConfig(default=default, providers=providers)
        except ValidationError as invalid:
            raise MapAdminRefused(refusal_words(invalid, set()), status=422) from None

    async def add_provider(self, by: str, provider: MapProvider) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            config = self.config()
            if any(p.id == provider.id for p in config.providers):
                raise MapAdminRefused(f"There is already a map provider {_shown(provider.id)}.")
            await asyncio.to_thread(admissible, provider, None)  # looks hosts up: off the loop
            self._save_map(self._validated(config.default, [*config.providers, provider]))
            fields = provider.model_dump(mode="json", exclude_none=True)
            await self._record(by, "provider_added", provider.id, {
                "tier": {"old": None, "new": tier_of(provider)},
                **{k: {"old": None, "new": v} for k, v in sorted(fields.items())},
            })  # fmt: skip
        return self.view()

    async def edit_provider(
        self, by: str, provider_id: str, provider: MapProvider
    ) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            config = self.config()
            old = self.provider(provider_id)
            if provider.id != provider_id:
                raise MapAdminRefused("A provider's id cannot be changed; add a new provider.")
            await asyncio.to_thread(admissible, provider, old)  # looks hosts up: off the loop
            providers = [provider if p.id == provider_id else p for p in config.providers]
            self._save_map(self._validated(config.default, providers))
            before, after = old.model_dump(mode="json"), provider.model_dump(mode="json")
            changes = {
                k: {"old": before.get(k), "new": after.get(k)}
                for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)
            }  # fmt: skip
            # A changed address never receives the key held for the old one (as *Models* does).
            moved = address_of(old) != address_of(provider)
            keys = self._keys.load()
            if moved and provider_id in keys:
                del keys[provider_id]
                self._keys.save(keys)
                self._note_keys(keys)
                changes["key"] = {"old": "set", "new": "removed: the address changed"}
            await self._record(by, "provider_edited", provider_id, changes)
        return self.view()

    async def remove_provider(self, by: str, provider_id: str) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            config = self.config()
            self.provider(provider_id)
            if provider_id == config.default:
                raise MapAdminRefused(
                    "The map opens on this provider. Choose another default before removing it."
                )
            if any(a.provider_id == provider_id for a in self.settings.areas):
                raise MapAdminRefused(
                    "A prefetch area uses this provider. Remove the area before the provider."
                )
            keys = self._keys.load()
            if provider_id in keys:
                del keys[provider_id]
                self._keys.save(keys)
                self._note_keys(keys)
            self._save_map(
                self._validated(
                    config.default, [p for p in config.providers if p.id != provider_id]
                )
            )
            await self._record(by, "provider_removed", provider_id)
        return self.view()

    async def set_default(self, by: str, default: str) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            config = self.config()
            self.provider(default)
            self._save_map(self._validated(default, list(config.providers)))
            await self._record(by, "default_changed", default, {
                "default": {"old": config.default, "new": default},
            })  # fmt: skip
        return self.view()

    async def set_key(self, by: str, provider_id: str, key: SecretStr) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            provider = self.provider(provider_id)
            if not provider.needs_key:
                raise MapAdminRefused(
                    "This provider takes no key: its address has no {credential}, and it names "
                    "no credential or credential_param. Edit it first if it should."
                )
            if provider.profile is not None or provider.proxy == "none":
                raise MapAdminRefused(
                    "Only a provider the Conduit fetches takes a key here: this one is fetched by "
                    "the browser, or comes from a ready-made profile, so a key would never be used."
                )
            keys = self._keys.load()
            replaced = provider_id in keys
            keys[provider_id] = KeyRecord(
                key=key, at=self._now(), by=by, address=address_of(provider)
            )
            self._keys.save(keys)
            self._note_keys(keys)
            await self._record(by, "key_set", provider_id, {
                "key": {"old": "set" if replaced else "none", "new": "set"},
            })  # fmt: skip
        return self.view()

    async def remove_key(self, by: str, provider_id: str) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            self.provider(provider_id)
            keys = self._keys.load()
            if provider_id not in keys:
                raise MapAdminRefused("No key is set for this provider in Admin.", status=404)
            del keys[provider_id]
            self._keys.save(keys)
            self._note_keys(keys)
            await self._record(by, "key_removed", provider_id, {
                "key": {"old": "set", "new": "none"},
            })  # fmt: skip
        return self.view()

    def _checked_area(self, area: PrefetchArea) -> None:
        provider = self.provider(area.provider_id)
        if provider.proxy == "none" or provider.cache is None:
            raise MapAdminRefused(
                f"The area {_shown(area.name)} names a provider whose tiles are not fetched and "
                "cached by the Conduit, so there is nothing to fetch ahead for it."
            )
        tiles = area_tiles(area)
        if tiles > MAX_AREA_TILES:
            raise MapAdminRefused(
                f"The area {_shown(area.name)} covers {tiles:,} tiles over its zooms; at most "
                f"{MAX_AREA_TILES:,} are fetched for one area. Make it smaller or lower its "
                "highest zoom.",
                status=422,
            )

    async def set_areas(self, by: str, areas: Sequence[PrefetchArea]) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            names = [a.name for a in areas]
            if len(set(names)) != len(names):
                raise MapAdminRefused("Two prefetch areas have the same name.", status=422)
            for area in areas:
                self._checked_area(area)
            settings = self._file.load()
            old = {a.name for a in settings.areas}
            kept = [r for r in settings.runs if r.area in names]
            self._file.save(settings.model_copy(update={"areas": list(areas), "runs": kept}))
            self._fresh()
            await self._record(by, "areas_changed", None, {
                "areas": {"old": sorted(old), "new": sorted(names)},
            })  # fmt: skip
        return self.view()

    async def set_schedule(self, by: str, schedule: PrefetchSchedule) -> MapsAdminView:
        async with self._exclusive:
            self._fresh()
            settings = self._file.load()
            old = settings.schedule.every_hours
            self._file.save(settings.model_copy(update={"schedule": schedule}))
            self._fresh()
            await self._record(by, "schedule_changed", None, {
                "every_hours": {"old": old, "new": schedule.every_hours},
            })  # fmt: skip
        return self.view()

    async def register_local(self, by: str, provider_id: str, label: str, file: str) -> None:
        """A built basemap's provider, in the maps file (`osprey.yaml` is read-only in the Conduit):
        added, or its source pointed at the new file."""
        source = f"file://{TILES_CONTAINER_PATH}/{BUILT_FOLDER}/{file}"
        async with self._exclusive:
            self._fresh()
            config = self.config()
            existing = next((p for p in config.providers if p.id == provider_id), None)
            if existing is not None:
                provider = existing.model_copy(update={"source": source})
                providers = [provider if p.id == provider_id else p for p in config.providers]
            else:
                provider = MapProvider.model_validate({
                    "id": provider_id, "label": label, "kind": "vector", "source": source,
                    "style": "bundled:osprey-dark", "attribution": "© OpenStreetMap contributors",
                    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
                })  # fmt: skip
                providers = [*config.providers, provider]
            self._save_map(self._validated(config.default, providers))
            await self._record(
                by, "basemap_built", provider_id, {"file": {"old": None, "new": file}}
            )

    async def record_verify(self, by: str, issues: int) -> None:
        await self._record(by, "basemap_verified", None, outcome=f"{issues} issues")

    # --- prefetch -------------------------------------------------------------------------

    async def run_prefetch(self, by: str) -> list[PrefetchRun]:
        """Every area once, one run at a time in this process. A failure is said in fixed words on
        its own area's run and the next area goes on; the provider's own words and address are
        never kept (a tile URL may carry a key)."""
        from .tile_cache import cache_key_for
        from .tile_proxy import build_upstream_url, fetch_tile

        if self._running.locked():
            raise MapAdminRefused("Prefetch is already running.")
        async with self._running:
            areas = list(self.settings.areas)
            store = self._tile_store()
            runs: list[PrefetchRun] = []
            for area in areas:
                fetched = cached = 0
                failed: str | None = None
                try:
                    self._checked_area(area)
                    provider = self.provider(area.provider_id)
                    assert provider.cache is not None  # `_checked_area`
                    await asyncio.to_thread(self.refuse_inside, provider)  # off the loop
                    key = self.key_for(provider.id)
                    for zoom in range(area.zoom_min, area.zoom_max + 1):
                        x0, x1, y0, y1 = tile_range_for_bbox(
                            area.west, area.south, area.east, area.north, zoom
                        )
                        for x, y in tiles_in_range(x0, x1, y0, y1):
                            object_key = cache_key_for(provider.id, zoom, x, y)
                            # The object store is called synchronously: off the event loop.
                            held = await asyncio.to_thread(
                                store.read, object_key, provider.cache.ttl_days
                            )
                            if held is not None:
                                cached += 1
                                continue
                            if fetched:
                                await self._sleep(self._pause)
                            url = build_upstream_url(provider, zoom, x, y, key=key)
                            data = (
                                await fetch_tile(url) if self._http_get is None
                                else await fetch_tile(url, http_get=self._http_get)
                            )  # fmt: skip
                            await asyncio.to_thread(store.write, object_key, data)
                            fetched += 1
                except MapAdminRefused as refused:
                    failed = refused.words
                except Exception as error:  # noqa: BLE001 - said in fixed words, next area goes on
                    failed = _failure_words(error)
                    log.warning("prefetch of an area stopped: %s", type(error).__name__)
                runs.append(PrefetchRun(
                    area=area.name, provider_id=area.provider_id, at=self._now(),
                    tiles_fetched=fetched, tiles_already_cached=cached, failed=failed,
                ))  # fmt: skip
            async with self._exclusive:
                settings = self._file.load()
                done = {r.area for r in runs}
                kept = [r for r in settings.runs if r.area not in done]
                self._file.save(settings.model_copy(update={"runs": [*kept, *runs]}))
                self._fresh()
            await self._record(by, "prefetch_run", None, {
                "tiles_fetched": {"old": None, "new": sum(r.tiles_fetched for r in runs)},
            }, outcome="done" if all(r.failed is None for r in runs)
               else "some areas failed")  # fmt: skip
            return runs


def _failure_words(error: BaseException) -> str:
    from .credentials import MissingCredentialError
    from .tile_proxy import MissingMapKeyError, TileFetchFailed

    if isinstance(error, (MissingMapKeyError, MissingCredentialError)):
        return "The provider needs a key and none is set."
    if isinstance(error, TileFetchFailed):
        if error.too_large:
            return "The provider answered with something larger than any tile; nothing was kept."
        if error.status:
            return f"The provider refused a tile (HTTP {error.status})."
        return "The provider could not be reached."
    if isinstance(error, OSError):
        return "The provider could not be reached."
    import httpx

    if isinstance(error, httpx.HTTPStatusError):
        return f"The provider refused a tile (HTTP {error.response.status_code})."
    if isinstance(error, httpx.HTTPError):
        return "The provider could not be reached."
    return "The prefetch stopped on an unexpected answer; the Conduit's log names its kind."


def _shown(value: str) -> str:
    return repr(value) if _NAMEABLE.fullmatch(value) else "(that name)"


class PrefetchScheduler:
    """Runs every area when the schedule says it is due, checked once a minute, in the Conduit
    (ADR-147 decision 5). Two replicas may both run an area: the cache makes the second's fetches
    hits, so nothing is fetched twice for long."""

    def __init__(self, admin: MapAdmin, check_seconds: float = 60.0) -> None:
        self._admin = admin
        self._check = check_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._check)
            try:
                if self._admin.due():
                    await self._admin.run_prefetch("schedule")
            except MapAdminRefused:
                pass  # already running
            except Exception as error:  # noqa: BLE001 - the schedule never stops unsaid
                log.warning("scheduled prefetch failed: %s", type(error).__name__)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown goes on
                pass
            self._task = None


# --- the build, in the Conduit ------------------------------------------------------------------


async def build_basemap(
    admin: MapAdmin,
    *,
    by: str,
    region: str,
    load_places: Callable[[Path], Awaitable[tuple[int, int, int]]],
    progress: Callable[[str], None] = print,
    downloader: Callable[[str, Path], Path] | None = None,
    planetiler_runner: Callable[..., Path] | None = None,
    tiles_root: Path = Path(TILES_CONTAINER_PATH),
    settle: Callable[[], Awaitable[None]] | None = None,
) -> tuple[str, int, int, int]:
    """The tier-1 build (`00_ARCHITECTURE.md` §1.2's one button): the region's extract, planetiler
    into the tiles folder, the OSM gazetteer loaded (`load_places`, which the caller runs in a
    graph transaction), and the provider registered in the maps file. Returns the file's name and
    the gazetteer's created, referenced and rejected counts. A region not in the list is refused
    by name; the jar is the tiles folder's own."""
    from scripts.build_local_basemap import (
        GEOFABRIK_REGIONS,
        download_extract,
        resolve_extract,
        run_planetiler,
    )

    if region not in GEOFABRIK_REGIONS:
        raise MapAdminRefused(
            f"{_shown(region)} is not a region the map can be built for. "
            f"Known regions: {', '.join(sorted(GEOFABRIK_REGIONS))}.",
            status=422,
        )
    builder = admin.basemap()
    if not builder.builder_ready:
        # Said before anything is fetched: the Conduit's image carries no Java while the owner rules
        # on its licence (ADR-147 decision 3), and the jar is placed by the command line.
        raise MapAdminRefused(builder.builder_state, status=409)
    jar = tiles_root / PLANETILER_JAR
    built = tiles_root / BUILT_FOLDER
    pmtiles = built / f"{region}.pmtiles"
    # The download and planetiler are blocking and long: each runs in a worker thread, so the
    # Conduit goes on answering, and the progress lines reach the stream as they are said.
    extract = await asyncio.to_thread(
        resolve_extract, region, built / "extracts", existing=None,
        downloader=downloader or download_extract, progress=progress,
    )  # fmt: skip
    progress("Running planetiler...")
    await asyncio.to_thread(planetiler_runner or run_planetiler, extract, pmtiles, jar_path=jar)
    progress("Loading the OSM-derived gazetteer...")
    created, referenced, rejected = await load_places(extract)
    if settle is not None:
        # The places committed before the provider is registered, so the map never points at a
        # basemap whose gazetteer a failed commit lost (the independent review's minor 9).
        await settle()
    progress(
        f"Gazetteer: {created} places created, {referenced} already known, {rejected} rejected."
    )
    provider_id = f"osm-local-{region}"
    progress(f"Registering provider {provider_id}...")
    await admin.register_local(by, provider_id, f"OpenStreetMap ({region})", pmtiles.name)
    return pmtiles.name, created, referenced, rejected


# --- the command line, inside the Conduit's container -------------------------------------------


async def open_admin(
    environ: Mapping[str, str] = os.environ,
) -> tuple[MapAdmin, Callable[[], Awaitable[None]]]:
    """The admin as the Conduit makes it, for the command line: `osprey.yaml`'s map, the maps and
    key files, the Postgres audit."""
    from .config import PostgresConfig
    from .mapconfig_loader import load_map_config

    installed = load_map_config(environ.get("OSPREY_CONFIG_PATH", "/app/osprey.yaml"))
    audit = await PostgresMapAdminAudit.connect(PostgresConfig.from_env().dsn)
    admin = MapAdmin(
        installed=installed, settings_file=MapSettingsFile.from_env(environ),
        key_file=MapKeyFile.from_env(environ), audit=audit,
    )  # fmt: skip
    return admin, audit.close


def list_lines(view: MapsAdminView) -> list[str]:
    """`list`'s lines: each provider's id, tier, key state and state, the default marked; the local
    basemaps and glyphs; the areas. Never a key, never an address."""
    lines = []
    for p in view.providers:
        mark = " (default)" if p.provider.id == view.default else ""
        lines.append(f"{p.provider.id}{mark}  tier {p.tier}  key: {p.key_state}  {p.state}")
    for b in view.basemap.basemaps:
        lines.append(f"basemap {b.file}: {'built' if b.built else 'not built'}")
    lines.append(f"glyphs: {'installed' if view.basemap.glyphs_installed else 'not installed'}")
    lines.append(f"builder: {view.basemap.builder_state}")
    for a in view.areas:
        last = a.last_run
        ran = "never run" if last is None else (
            f"last run {last.at:%Y-%m-%d %H:%M} UTC, {last.tiles_fetched} fetched"
            + (f", {last.failed}" if last.failed else "")
        )  # fmt: skip
        lines.append(f"area {a.area.name}: {a.tiles} tiles, {ran}")
    return lines


async def _main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.api.map_admin")
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("list")
    for verb in ("verify", "prefetch"):
        sub.add_parser(verb).add_argument("--by", required=True)
    build = sub.add_parser("build")
    build.add_argument("region")
    build.add_argument("--by", required=True)
    build.add_argument("--unit", required=True)
    args = parser.parse_args(argv)
    admin, close = await open_admin()
    try:
        if args.verb == "list":
            print("\n".join(list_lines(admin.view())))
            return 0
        if args.verb == "prefetch":
            runs = await admin.run_prefetch(args.by)
            for run in runs:
                print(f"{run.area}: {run.tiles_fetched} fetched, {run.tiles_already_cached} "
                      f"already cached" + (f"; {run.failed}" if run.failed else ""))  # fmt: skip
            return 0 if all(r.failed is None for r in runs) else 1
        if args.verb == "verify":
            from scripts.verify_map import verify_map

            report = await verify_map(admin.config())
            await admin.record_verify(args.by, len(report.issues))
            for issue in report.issues:
                print(f"{issue.provider_id}: {issue.check}: {issue.detail}")
            print("Verify passed." if report.passed else "Verify found issues.")
            return 0 if report.passed else 1
        if args.verb == "build":
            return await _build_here(admin, args.by, args.region, args.unit)
    except MapAdminRefused as refused:
        print(refused.words, file=sys.stderr)
        return 1
    finally:
        await close()
    return 1


async def _build_here(admin: MapAdmin, by: str, region: str, unit: str) -> int:
    """`build` from the command line: the gazetteer loaded through the Conduit's own graph, held by
    `unit` (ADR-147 Amendment 2, the owner's ruling 8), which is checked before anything runs."""
    from services.api.map_places import DatasetsUnreachable, UnknownUnit, check_unit_from_env

    try:
        await check_unit_from_env(unit)
    except (UnknownUnit, DatasetsUnreachable) as refused:
        print(str(refused), file=sys.stderr)
        return 1
    from scripts.build_local_basemap import load_gazetteer
    from services.resolve.trigger import service_principal

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology

    scheme = load_uk_le_scheme()
    # The Conduit's own system principal, as its other reference-data loads use; the person is the
    # maps' history's `by`.
    principal = service_principal(scheme)
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    graph = GraphArcadeDBAdapter(client, scheme)
    ontology = load_default_ontology()
    await graph.apply_schema(ontology)

    held: dict[str, str] = {}

    async def load_places(extract: Path) -> tuple[int, int, int]:
        # ADR-147 Amendment 1: into the region's gazetteer dataset, as the Admin route's build.
        from services.api.map_places import gazetteer_dataset_id

        tx = await graph.begin_transaction()
        held["tx"] = tx
        report = await load_gazetteer(
            extract, graph=graph, ontology=ontology, tx=tx, principal=principal,
            load_id=f"load-osm-gazetteer-{region}", dataset=gazetteer_dataset_id(region),
            unit=unit,
        )  # fmt: skip
        return report.nodes_created, report.nodes_referenced, len(report.rejections)

    async def settle() -> None:
        # ADR-147 Amendment 1, decision 2: the dataset registered once the places are committed (a
        # failed build leaves none), and the words about the points said after the load.
        from services.api.map_places import (
            NO_POINTS_HERE,
            DatasetsUnreachable,
            gazetteer_dataset_id,
            refresh_case_copies_from_env,
            register_gazetteer_dataset_from_env,
        )

        await graph.commit_transaction(held.pop("tx"))
        print(NO_POINTS_HERE)
        try:
            await register_gazetteer_dataset_from_env(region, by=by, unit=unit)
            # ADR-147 Amendment 2: every case that added the gazetteer given its places again.
            cases = await refresh_case_copies_from_env(graph, scheme, gazetteer_dataset_id(region))
            print(f"Cases given the places again: {cases}.")
        except DatasetsUnreachable as unreachable:
            # The places are committed; the build goes on, and says how to register them.
            print(str(unreachable), file=sys.stderr)

    try:
        name, created, referenced, rejected = await build_basemap(
            admin, by=by, region=region, load_places=load_places, settle=settle
        )
    except Exception as error:  # noqa: BLE001 - said in words, exit 1
        if "tx" in held:
            await graph.rollback_transaction(held["tx"])
        print(f"The build stopped ({type(error).__name__}): {error}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()
    print(
        f"Built {name}: {created} places created, {referenced} already known, {rejected} rejected."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(list(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())


__all__: list[str] = [
    "MapAdmin",
    "MapAdminRefused",
    "MapSettingsFile",
    "MapKeyFile",
    "InMemoryMapAdminAudit",
    "PostgresMapAdminAudit",
    "PrefetchScheduler",
    "build_basemap",
    "tier_of",
    "area_tiles",
]
