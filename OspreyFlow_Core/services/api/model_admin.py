"""*Admin › Models* (`06_DECISIONS.md` ADR-135 Amendment 2; ADR-112 Amendment 7): engines, each
job's default engine and their keys, managed from the Glass.

Three places, each holding only its own part:

- **the models file** (`ModelSettingsFile`, decision 2): the engines and defaults once *Models* has
  changed them, and each key's record (when, by whom) — never a key. When it is absent, the
  engines are `osprey.yaml`'s, as the render told the Conduit (`OSPREY_MODEL_ENGINES`, …);
- **the gateway's database** (`GatewayAdmin`, decision 3): each engine's model entries, and its key
  as one credential, `osprey-<provider>`, that the entries name. Reached through LiteLLM's admin
  API with the master key the Conduit already holds;
- **the audit** (`ModelAdminAudit`, decision 7): who changed what, never the key.

**Limits** (ADR-135 Amendment 3): each hosted engine's calls go with its own gateway key
(`usage.engine_key`, derived from the master key, never stored), and the engine's limits are that
key's (`rpm_limit`, `tpm_limit`, and a token budget as `max_budget` per `1d` or `30d`, every hosted
entry priced at one unit a token so the gateway's spend is the tokens used). They are kept in the
models file beside the engines, made equal in the gateway with the entries, and audited
(`limits_changed`). The key-admin answers are discarded: `/key/update`'s carries the key.

**A key passes through and is kept by nothing here** (decision 4): it arrives as a `SecretStr`, is
revealed once, inside the request body sent to the gateway, and is never logged, returned or
written. The gateway's answers are never passed on: they can carry part of a key (measured), so a
failure is reported in fixed words with its HTTP status alone. And the Conduit never reads
credentials back (`GET /credentials` answers with two characters at each end of the key).
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import asyncpg
import httpx
import yaml
from pydantic import BaseModel, Field, SecretStr, ValidationError

from adapters.model_litellm.connection import check_connection
from adapters.model_litellm.usage import engine_key, usage_tag
from schemas.deployment import ModelProviderConfig, ModelsConfig
from schemas.model_admin import (
    AdminEngine,
    ConnectionTestResult,
    EngineLimits,
    KeyState,
    ModelAdminAction,
    ModelAdminEntry,
    ModelsAdminView,
)

from .config import DeploymentModels
from .model_routing import LOCAL, ROLES, Engine, ModelRoutes, Role

log = logging.getLogger(__name__)

#: Where the Conduit's container mounts the models file's folder (ADR-135 Amendment 2 decision 2).
DEFAULT_SETTINGS_DIR = "/run/osprey/model-settings"
SETTINGS_FILE = "models.yaml"


class ModelAdminRefused(Exception):
    """A change refused, in words that are safe to show (never a key, never the gateway's words)."""

    def __init__(self, words: str, *, status: int = 422) -> None:
        super().__init__(words)
        self.words = words
        self.status = status


class KeyRemovedNotReplaced(ModelAdminRefused):
    """The old credential was removed and the gateway refused the new one: the engine has no key
    now, and is recorded so (`ModelAdmin.set_key`)."""


# --- the models file ---------------------------------------------------------------------------


class KeyRecord(BaseModel):
    set_at: datetime
    set_by: str
    #: The gateway no longer holds it (decision 9: a restore from another deployment, or its
    #: encryption key changed). Kept here, so every process and replica, and the command line,
    #: says the same until it is entered again.
    lost: bool = False


class ModelSettings(BaseModel):
    """What the models file holds. `providers` and `defaults` replace `osprey.yaml`'s whole."""

    providers: list[ModelProviderConfig] = Field(default_factory=list)
    defaults: dict[str, str] = Field(default_factory=dict)
    keys: dict[str, KeyRecord] = Field(default_factory=dict)
    #: Each engine's limits (ADR-135 Amendment 3); an engine not here has none.
    limits: dict[str, EngineLimits] = Field(default_factory=dict)


class ModelSettingsFile:
    def __init__(self, folder: Path) -> None:
        self.path = folder / SETTINGS_FILE

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> ModelSettingsFile:
        return cls(Path(environ.get("OSPREY_MODEL_SETTINGS_DIR", DEFAULT_SETTINGS_DIR)))

    def stamp(self) -> float | None:
        """When the file last changed, or None where there is none: a Conduit replica reads it again
        when this moves, so a change made through another replica reaches it."""
        try:
            return self.path.stat().st_mtime_ns / 1e9
        except FileNotFoundError:
            return None

    def load(self) -> ModelSettings | None:
        if not self.path.is_file():
            return None
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return ModelSettings.model_validate(raw)

    def save(self, settings: ModelSettings) -> None:
        """Atomic, and `600` from the moment it exists (a temporary file renamed over the old)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(settings.model_dump(mode="json"), sort_keys=False)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".models-", suffix=".yaml")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


@dataclass(frozen=True)
class Installed:
    """What `osprey.yaml` says, as the render told the Conduit: the starting engines and defaults,
    and the installer's own declarations (`local_only`, the sendable codes), which *Models* only
    shows."""

    providers: list[ModelProviderConfig]
    defaults: dict[str, str]
    #: Whether each engine's key is present, as Compose told the Conduit (before the models file).
    key_present: dict[str, bool]
    local_only: bool
    sendable: list[str]
    locals: dict[str, str | None]

    @classmethod
    def from_env(cls, local: DeploymentModels, environ: Mapping[str, str]) -> Installed:
        def _json(name: str, empty: object) -> object:
            text = environ.get(name, "").strip()
            return json.loads(text) if text else empty

        providers: list[ModelProviderConfig] = []
        present: dict[str, bool] = {}
        for raw in cast(list[dict[str, Any]], _json("OSPREY_MODEL_ENGINES", [])):
            name = str(raw["name"])
            roles = {
                r: str(m).removeprefix(f"{name}/") for r, m in dict(raw.get("roles") or {}).items()
            }
            providers.append(
                ModelProviderConfig(
                    name=name,
                    label=raw.get("label"),
                    roles=roles,
                    api_base=raw.get("api_base"),
                    privacy_contract=raw.get("privacy_contract") is True,
                    contract_reference=raw.get("contract_reference"),
                )
            )
            present[name] = environ.get(f"OSPREY_MODEL_KEY_PRESENT_{name.upper()}", "") == "yes"
        return cls(
            providers=providers,
            defaults=dict(cast(dict[str, str], _json("OSPREY_MODEL_DEFAULTS", {}))),
            key_present=present,
            local_only=environ.get("OSPREY_MODELS_LOCAL_ONLY", "true").lower() != "false",
            sendable=[
                c.strip()
                for c in environ.get("OSPREY_SENDABLE_HANDLING_CODES", "").split(",")
                if c.strip()
            ],
            locals={
                "extraction": local.extraction,
                "vision": local.vision,
                "transcription": local.transcription,
                "embedding": local.embedding,
            },
        )


# --- the gateway --------------------------------------------------------------------------------


def credential_name(provider: str) -> str:
    return f"osprey-{provider}"


def entry_id(provider: str, model: str) -> str:
    return f"osprey-{provider}-" + re.sub(r"[^A-Za-z0-9._-]", "-", model)


def gateway_model_name(provider: str, model: str) -> str:
    return f"{provider}/{model}"


#: Every hosted entry's price: one unit a token, prompt and completion alike, so the gateway's spend
#: on an engine's key is the tokens it used and a budget is set in tokens (ADR-135 Amendment 3).
TOKEN_PRICE = 1
#: A budget's period as the gateway takes it (measured: `1d` resets at midnight UTC, `30d` on the
#: first of the next month).
BUDGET_DURATION = {"day": "1d", "month": "30d"}


def key_limits(limits: EngineLimits) -> dict[str, object]:
    """An engine's limits as its gateway key's fields; `None` clears one (measured)."""
    return {
        "rpm_limit": limits.requests_per_minute,
        "tpm_limit": limits.tokens_per_minute,
        "max_budget": limits.budget_tokens * TOKEN_PRICE if limits.budget_tokens else None,
        "budget_duration": BUDGET_DURATION[limits.budget_period] if limits.budget_period else None,
    }


#: `/key/list`'s page (measured: at most 100) and how many pages are read before refusing.
_KEY_PAGE = 100
_MAX_KEY_PAGES = 100


class GatewayAdmin:
    """LiteLLM's admin API, as measured (ADR-135 Amendments 2 and 3). Every failure becomes a
    `ModelAdminRefused` with fixed words and the status alone."""

    def __init__(self, http: httpx.AsyncClient, *, master: str | None = None) -> None:
        self._http = http
        # The master key the client already carries; each engine's key is derived from it.
        self._master = master or str(http.headers.get("authorization", "")).removeprefix("Bearer ")

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    async def _call(self, method: str, path: str, body: object | None = None) -> httpx.Response:
        try:
            resp = await self._http.request(method, path, json=body, timeout=30.0)
        except httpx.HTTPError:
            raise ModelAdminRefused(
                "The model gateway could not be reached; the change was not saved.", status=502
            ) from None
        return resp

    def _refused(self, resp: httpx.Response, what: str) -> ModelAdminRefused:
        return ModelAdminRefused(
            f"The model gateway refused {what} (HTTP {resp.status_code}); the change was not "
            "saved. Run ospreyflow doctor.",
            status=502,
        )

    async def stored_entries(self) -> set[str]:
        return set(await self.entries())

    async def entries(self) -> dict[str, bool]:
        """Each entry the Conduit made, and whether it is priced a unit a token (an entry made
        before ADR-135 Amendment 3 is not, so its engine's budget would never be reached)."""
        resp = await self._call("GET", "/v2/model/info")
        if resp.status_code != 200:
            raise self._refused(resp, "the list of engines")
        held: dict[str, bool] = {}
        for row in resp.json().get("data", []):
            model_id = str(dict(row.get("model_info") or {}).get("id") or "")
            if model_id.startswith("osprey-"):
                params = dict(row.get("litellm_params") or {})
                held[model_id] = all(
                    _number(params.get(f)) == TOKEN_PRICE
                    for f in ("input_cost_per_token", "output_cost_per_token")
                )
        return held

    async def add_entry(self, provider: ModelProviderConfig, model: str) -> None:
        """`POST /model/new` (measured). An entry is never patched: an edited engine's entries are
        deleted and made again, so no unmeasured partial update is relied on, and a cleared
        address leaves nothing of the old one behind."""
        params: dict[str, object] = {
            "model": gateway_model_name(provider.name, model),
            "litellm_credential_name": credential_name(provider.name),
            "input_cost_per_token": TOKEN_PRICE,
            "output_cost_per_token": TOKEN_PRICE,
        }
        if provider.api_base:
            params["api_base"] = provider.api_base
        resp = await self._call(
            "POST",
            "/model/new",
            {
                "model_name": gateway_model_name(provider.name, model),
                "litellm_params": params,
                "model_info": {"id": entry_id(provider.name, model)},
            },
        )
        if resp.status_code != 200:
            raise self._refused(resp, f"the model {model}")

    async def delete_entry(self, model_id: str) -> None:
        resp = await self._call("POST", "/model/delete", {"id": model_id})
        if resp.status_code not in (200, 400):  # 400: already gone (measured)
            raise self._refused(resp, "a model's removal")

    async def put_credential(self, provider: str, key: SecretStr) -> None:
        """The engine's key, as its one credential: any held is removed (`DELETE`, 404 when none,
        both measured) and the new one made (`POST`, measured), so neither a `PATCH` of one that
        is not there nor a `POST` over one that is is ever asked of the gateway."""
        await self.delete_credential(provider)
        body = {
            "credential_name": credential_name(provider),
            "credential_values": {"api_key": key.get_secret_value()},
            "credential_info": {},
        }
        try:
            resp = await self._call("POST", "/credentials", body)
        except ModelAdminRefused:
            resp = None
        if resp is None or resp.status_code != 200:
            status = "" if resp is None else f" (HTTP {resp.status_code})"
            raise KeyRemovedNotReplaced(
                f"The model gateway refused the new key{status} after the old one was removed: "
                "the engine has no key now and is offered to no analyst. Enter the key again; "
                "run ospreyflow doctor if it is refused again.",
                status=502,
            )

    async def delete_credential(self, provider: str) -> None:
        resp = await self._call("DELETE", f"/credentials/{credential_name(provider)}")
        if resp.status_code not in (200, 404):  # 404: none was held (measured)
            raise self._refused(resp, "the key's removal")

    def _engine_key(self, provider: str) -> str:
        """The engine's key, derived from the master key; **refused when there is no master key**,
        from which anyone could derive every engine's key (P2's independent review)."""
        if not self._master.strip():
            raise ModelAdminRefused(
                "The model gateway's master key is not set, so no engine's own key can be made. "
                "Run ospreyflow doctor.",
                status=502,
            )
        return engine_key(self._master, provider)

    async def put_engine_key(self, provider: ModelProviderConfig, limits: EngineLimits) -> None:
        """The engine's own gateway key with its limits and **its own models alone** (`models`,
        measured: any other model is refused 403 `key_model_access_denied`, so one engine's key
        cannot spend another's budget): updated where the gateway holds it (`/key/update`,
        measured to change them at once, `None` clearing one), made where it does not (the
        update's 404, measured; then `/key/generate`). Never deleted to change it, which would lose
        the budget's spend so far. **The key is only ever in a request's body**, never its address:
        the HTTP client logs every address, so `GET /key/info?key=…` is never asked. Every answer
        is discarded: the update's carries the key."""
        key = self._engine_key(provider.name)
        # Never empty: an empty `models` is every model (measured); a provider takes at least one
        # role (`ModelProviderConfig`), so there is always one.
        roles = dict.fromkeys(provider.roles.values())
        models = [gateway_model_name(provider.name, m) for m in roles]
        fields = {**key_limits(limits), "models": models}
        resp = await self._call("POST", "/key/update", {"key": key, **fields})
        if resp.status_code == 404:
            # No alias: a key's alias must be unique (measured, 400), and a key derived under
            # another master key would then collide with the old one and stop every change.
            resp = await self._call("POST", "/key/generate", {
                "key": key, **fields, "metadata": {"osprey_engine": provider.name},
            })  # fmt: skip
        if resp.status_code != 200:
            raise self._refused(resp, "the engine's limits")

    async def delete_engine_key(self, provider: str) -> None:
        resp = await self._call("POST", "/key/delete", {"keys": [self._engine_key(provider)]})
        if resp.status_code not in (200, 404):  # 404: none was held (measured)
            raise self._refused(resp, "the engine's limits' removal")

    async def revoke_stale_engine_keys(self, engines: Sequence[str]) -> int:
        """Every key the gateway holds tagged `metadata.osprey_engine` that the current master key
        would not derive for one of `engines` is deleted (ADR-135 Amendment 3, "As built in P3"):
        after a master-key rotation the old engine keys would otherwise stay valid for whoever
        holds the old master key. Every page of `/key/list` is read before anything is deleted
        (measured: at most 100 a page, newest first, so deleting while reading would skip keys),
        and each stale key is named by its SHA-256 alone (measured: `/key/delete` takes it), so no
        old key travels anywhere. A key without the tag is someone else's and is left alone."""
        current = {
            hashlib.sha256(self._engine_key(e).encode()).hexdigest() for e in engines
        }
        stale: list[str] = []
        page, pages = 1, 1
        while page <= pages:
            if page > _MAX_KEY_PAGES:
                raise ModelAdminRefused(
                    f"The model gateway holds more than {_MAX_KEY_PAGES * _KEY_PAGE} keys, so the "
                    "engines' old keys were not looked for. Run ospreyflow doctor.",
                    status=502,
                )
            resp = await self._call(
                "GET", f"/key/list?return_full_object=true&page={page}&size={_KEY_PAGE}"
            )
            if resp.status_code != 200:
                raise self._refused(resp, "the list of keys")
            body = resp.json()
            pages = int(body.get("total_pages") or 1)
            for row in body.get("keys") or []:
                token = str(dict(row).get("token") or "")
                tagged = dict(dict(row).get("metadata") or {}).get("osprey_engine")
                if tagged is not None and token and token not in current:
                    stale.append(token)
            page += 1
        for token in stale:
            resp = await self._call("POST", "/key/delete", {"keys": [token]})
            if resp.status_code not in (200, 404):
                raise self._refused(resp, "an old engine key's removal")
        if stale:
            log.info("revoked %d engine keys the current master key does not derive", len(stale))
        return len(stale)


# --- the audit ----------------------------------------------------------------------------------


class ModelAdminAudit(Protocol):
    async def record(self, entry: ModelAdminEntry) -> None: ...

    async def recent(self, limit: int = 200) -> list[ModelAdminEntry]: ...


@dataclass
class InMemoryModelAdminAudit:
    entries: list[ModelAdminEntry] = field(default_factory=list)

    async def record(self, entry: ModelAdminEntry) -> None:
        self.entries.append(entry)

    async def recent(self, limit: int = 200) -> list[ModelAdminEntry]:
        return list(reversed(self.entries))[:limit]


_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS model_admin_audit (
    id BIGSERIAL PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL,
    by TEXT NOT NULL,
    action TEXT NOT NULL,
    engine TEXT,
    changes JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome TEXT NOT NULL
);
"""


class PostgresModelAdminAudit:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresModelAdminAudit:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            await conn.execute(_AUDIT_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def record(self, entry: ModelAdminEntry) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO model_admin_audit (at, by, action, engine, changes, outcome) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6)",
                entry.at, entry.by, entry.action, entry.engine, json.dumps(entry.changes),
                entry.outcome,
            )  # fmt: skip

    async def recent(self, limit: int = 200) -> list[ModelAdminEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT at, by, action, engine, changes, outcome FROM model_admin_audit "
                "ORDER BY id DESC LIMIT $1",
                limit,
            )
        return [
            ModelAdminEntry(
                at=r["at"],
                by=r["by"],
                action=r["action"],
                engine=r["engine"],
                changes=json.loads(r["changes"]),
                outcome=r["outcome"],
            )  # fmt: skip
            for r in rows
        ]


# --- the service --------------------------------------------------------------------------------

_EDITABLE = ("label", "roles", "api_base", "privacy_contract", "contract_reference")


#: A value that may be named in a refusal: shaped like a provider or a job (lower-case, short),
#: never like a key. Everything else a person sent is replaced by "…" in what the Conduit says back.
_NAMEABLE = re.compile(r"[a-z][a-z0-9_]{0,23}")


def sent_values(value: object) -> set[str]:
    """Every string a request carried, wherever it sits."""
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
    """`words` with every sent value not shaped like a name replaced: a validator's message may
    quote what it refused (`schemas.deployment`'s do), and that may be a key pasted into the wrong
    field. Longest first, so a value inside another is not left half-shown."""
    for value in sorted(values, key=len, reverse=True):
        if value and not _NAMEABLE.fullmatch(value):
            words = words.replace(value, "…")
    return words


class _Exclusive:
    """One change at a time: within the process (an `asyncio.Lock`) and across processes and
    replicas sharing the models file (an advisory lock on a file beside it, `fcntl.flock`), so two
    administrators, two replicas or the command line never write over each other's change."""

    def __init__(self, folder: Path, name: str = ".models.lock") -> None:
        self._lock = asyncio.Lock()
        self._path = folder / name
        self._fd: int | None = None

    async def __aenter__(self) -> None:
        await self._lock.acquire()
        fd: int | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
            await asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_EX)
            self._fd = fd
        except BaseException:
            # Cancelled while waiting: the thread may still take the lock later, on this fd, so
            # the fd is closed, which releases whatever it holds.
            if fd is not None:
                os.close(fd)
            self._lock.release()
            raise

    async def __aexit__(self, *_exc: object) -> None:
        try:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                self._fd = None
        finally:
            self._lock.release()


class ModelAdmin:
    """*Models*' service. **The gateway is changed first, the models file only once it has
    answered**; a refusal, or a file that cannot be written, puts the gateway back as the file
    says, so the file, the gateway and routing never disagree for long, and the refusal is said in
    words. Every change holds `_Exclusive` and reads the file afresh under it."""

    def __init__(
        self,
        *,
        installed: Installed,
        settings_file: ModelSettingsFile,
        gateway: GatewayAdmin,
        audit: ModelAdminAudit,
        on_change: Callable[[ModelRoutes], None] = lambda _routes: None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        retry_seconds: float = 30.0,
    ) -> None:
        self._retry_seconds = retry_seconds
        self._retrying: asyncio.Task[None] | None = None
        self._installed = installed
        self._file = settings_file
        self._gateway = gateway
        self._audit = audit
        self._on_change = on_change
        self._now = now
        self._settings = settings_file.load()
        self._stamp = settings_file.stamp()
        self._exclusive = _Exclusive(settings_file.path.parent)

    # --- reading --------------------------------------------------------------------------

    def _fresh(self) -> None:
        stamp = self._file.stamp()
        if stamp != self._stamp:
            self._settings = self._file.load()
            self._stamp = stamp

    @property
    def settings(self) -> ModelSettings:
        self._fresh()
        if self._settings is not None:
            return self._settings
        return ModelSettings(
            providers=list(self._installed.providers),
            defaults=dict(self._installed.defaults),
        )

    def key_state(self, name: str) -> KeyState:
        self._fresh()
        if self._settings is None:
            return "set" if self._installed.key_present.get(name) else "none"
        record = self._settings.keys.get(name)
        if record is None:
            return "none"
        return "lost" if record.lost else "set"

    def routes(self) -> ModelRoutes:
        """The routing's view (`model_routing.ModelRoutes`), from what *Models* holds now. While
        `osprey.yaml` declares the deployment local only, no engine is offered, whatever the models
        file holds (decision 1: that declaration is the installer's)."""
        current = self.settings
        engines = {
            p.name: Engine(
                name=p.name,
                label=p.label or p.name,
                models={r: gateway_model_name(p.name, m) for r, m in p.roles.items() if r in ROLES},
                key_present=self.key_state(p.name) == "set",
                privacy_contract=p.privacy_contract,
                contract_reference=p.contract_reference,
                budget_period=current.limits.get(p.name, EngineLimits()).budget_period,
            )
            for p in current.providers
        }
        if self._installed.local_only:
            engines = {}
        return ModelRoutes(
            locals=cast(dict[Role, str | None], dict(self._installed.locals)),
            engines=engines,
            defaults={r: e for r, e in current.defaults.items() if r in ROLES and engines},
            sendable=frozenset(self._installed.sendable),
        )

    def view(self) -> ModelsAdminView:
        current = self.settings
        records = current.keys if self._settings is not None else {}
        return ModelsAdminView(
            engines=[
                AdminEngine(
                    provider=p,
                    key_state=self.key_state(p.name),
                    key_set_at=records[p.name].set_at if p.name in records else None,
                    key_set_by=records[p.name].set_by if p.name in records else None,
                    default_for=[r for r, e in current.defaults.items() if e == p.name],
                    limits=current.limits.get(p.name, EngineLimits()),
                )
                for p in current.providers
            ],
            defaults=dict(current.defaults),
            local_models=dict(self._installed.locals),
            local_only=self._installed.local_only,
            sendable_handling_codes=list(self._installed.sendable),
            source="models file" if self._settings is not None else "osprey.yaml",
        )

    @property
    def gateway_http(self) -> httpx.AsyncClient:
        """The gateway client with the master key: the only token that may read its usage."""
        return self._gateway.http

    async def history(self) -> list[ModelAdminEntry]:
        return await self._audit.recent()

    # --- the gateway, kept equal to the settings --------------------------------------------

    async def start(self) -> None:
        """At start: mark in the models file each engine whose key the gateway lost (its entries
        gone though the file says a key was set), then make the gateway's entries and each
        engine's own key equal the file. A local-only deployment keeps no hosted entry. **A gateway
        that cannot be reached is tried again in the background** (`retry_seconds`) until it
        answers (ADR-135 Amendment 3): until then a hosted engine's key may not exist there, and
        its calls would be refused."""
        try:
            done = await self._start_once()
        except Exception as failed:  # noqa: BLE001 - a garbled answer never stops the Conduit
            log.warning("model engines not reconciled with the gateway: %s",
                        type(failed).__name__)  # fmt: skip
            done = False
        if not done:
            self._retrying = asyncio.create_task(self._keep_trying())
        self._on_change(self.routes())

    async def _keep_trying(self) -> None:
        """Until the gateway answers: each failure waits twice as long as the last, up to ten
        minutes, and nothing it raises ends the retry unsaid."""
        wait = self._retry_seconds
        while True:
            await asyncio.sleep(wait)
            try:
                done = await self._start_once()
            except Exception as failed:  # noqa: BLE001 - logged in words, then tried again
                log.warning("model engines not reconciled with the gateway: %s",
                            type(failed).__name__)  # fmt: skip
                done = False
            if done:
                log.info("model engines reconciled with the gateway after a retry")
                self._on_change(self.routes())
                return
            wait = min(wait * 2, 600.0)

    async def close(self) -> None:
        """Stops the background retry, if one is running."""
        if self._retrying is not None:
            self._retrying.cancel()
            try:
                await self._retrying
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown goes on
                pass
            self._retrying = None

    async def _start_once(self) -> bool:
        if self._settings is None:
            return True
        try:
            async with self._exclusive:
                self._fresh()
                entries = await self._gateway.entries()
                held = set(entries)
                current = self.settings
                keys = dict(current.keys)
                for p in current.providers:
                    record = keys.get(p.name)
                    wanted = {entry_id(p.name, m) for m in p.roles.values()}
                    if record is not None and not record.lost and not wanted & held:
                        keys[p.name] = record.model_copy(update={"lost": True})
                if keys != current.keys:
                    self._save(current.model_copy(update={"keys": keys}, deep=True))
                unpriced = frozenset(
                    p.name for p in current.providers
                    if any(not entries.get(entry_id(p.name, m), True) for m in p.roles.values())
                )  # fmt: skip
                await self._reconcile(self.settings, held, rebuilt=unpriced)
            return True
        except (ModelAdminRefused, OSError) as failed:
            log.warning("model engines not reconciled with the gateway: %s", _said(failed))
            return False

    def _hosted(self, settings: ModelSettings) -> ModelSettings:
        """What the gateway should hold: nothing hosted while the deployment is local only."""
        if self._installed.local_only:
            return settings.model_copy(update={"providers": []})
        return settings

    async def _reconcile(
        self,
        settings: ModelSettings,
        held: set[str] | None = None,
        rebuilt: frozenset[str] = frozenset(),
    ) -> None:
        """The gateway's entries made equal to `settings`: stale ones deleted, missing ones made,
        and every entry of an engine in `rebuilt` (just edited) deleted and made again."""
        settings = self._hosted(settings)
        held = await self._gateway.stored_entries() if held is None else held
        wanted: dict[str, tuple[ModelProviderConfig, str]] = {}
        for p in settings.providers:
            for model in dict.fromkeys(p.roles.values()):
                wanted[entry_id(p.name, model)] = (p, model)
        for model_id in sorted(held):
            stale = model_id not in wanted
            if stale or wanted[model_id][0].name in rebuilt:
                await self._gateway.delete_entry(model_id)
                held = held - {model_id}
        for model_id, (p, model) in wanted.items():
            if model_id not in held:
                await self._gateway.add_entry(p, model)
        for p in settings.providers:
            await self._gateway.put_engine_key(p, settings.limits.get(p.name, EngineLimits()))
        await self._gateway.revoke_stale_engine_keys([p.name for p in settings.providers])

    async def _put_back(self, settings: ModelSettings, rebuilt: frozenset[str]) -> None:
        """After a change failed part-way: the gateway made equal to the file again, best effort;
        what cannot be put back now is put back at the next start."""
        try:
            await self._reconcile(settings, rebuilt=rebuilt)
        except ModelAdminRefused as refused:
            log.warning("model engines not put back after a failed change: %s", refused.words)

    # --- changing -------------------------------------------------------------------------

    def _validated(self, settings: ModelSettings, sent: set[str]) -> ModelSettings:
        if settings.providers and self._installed.local_only:
            raise ModelAdminRefused(
                "This deployment's osprey.yaml declares local_only: true, so no engine outside it "
                "may be added or changed here. The installer changes that declaration "
                "(local_only: false, then ospreyflow apply)."
            )
        try:
            ModelsConfig(
                local_only=not settings.providers,
                providers=settings.providers,
                defaults=settings.defaults,  # type: ignore[arg-type]
                sendable_handling_codes=self._installed.sendable if settings.providers else [],
            )
        except ValidationError as invalid:
            words = "; ".join(str(e.get("msg", "")).removeprefix("Value error, ")
                              for e in invalid.errors(include_input=False))  # fmt: skip
            raise ModelAdminRefused(redacted(words, sent)) from None
        return settings

    def _save(self, settings: ModelSettings) -> None:
        self._file.save(settings)
        self._settings = settings
        self._stamp = self._file.stamp()
        self._on_change(self.routes())

    async def _audited(
        self,
        by: str,
        action: ModelAdminAction,
        engine: str | None,
        changes: dict[str, dict[str, object]] | None = None,
        outcome: str = "done",
    ) -> None:
        await self._audit.record(
            ModelAdminEntry(
                at=self._now(),
                by=by,
                action=action,
                engine=engine,
                changes=changes or {},
                outcome=outcome,
            )  # fmt: skip
        )

    def _provider(self, name: str) -> ModelProviderConfig:
        for p in self.settings.providers:
            if p.name == name:
                return p
        shown = name if _NAMEABLE.fullmatch(name) else "of that name"
        raise ModelAdminRefused(f"There is no engine {shown} on this deployment.", status=404)

    async def _refusing(
        self, by: str, action: ModelAdminAction, engine: str | None, refused: ModelAdminRefused
    ) -> ModelAdminRefused:
        shown = engine if engine is None or _NAMEABLE.fullmatch(engine) else "…"
        await self._audited(by, action, shown, outcome=f"refused: {refused.words}")
        return refused

    async def _change(
        self,
        by: str,
        action: ModelAdminAction,
        engine: str | None,
        work: Callable[[ModelSettings], Any],
        *,
        rebuilt: frozenset[str] = frozenset(),
    ) -> Any:
        """One change, held exclusively against the file read afresh: `work` changes the gateway
        and returns what to save. A refusal, or a file that cannot be written, puts the gateway
        back as the file still says, is audited and is said in words."""
        async with self._exclusive:
            self._fresh()
            current = self.settings
            try:
                result = await work(current)
            except ModelAdminRefused as refused:
                await self._put_back(current, rebuilt)
                raise await self._refusing(by, action, engine, refused) from None
            except OSError:
                await self._put_back(current, rebuilt)
                unsaved = ModelAdminRefused(
                    "The models file could not be written; the change was not saved.", status=500
                )
                raise await self._refusing(by, action, engine, unsaved) from None
            return result

    async def add_engine(self, by: str, provider: ModelProviderConfig) -> None:
        sent = sent_values(provider)

        async def work(current: ModelSettings) -> None:
            if any(p.name == provider.name for p in current.providers):
                raise ModelAdminRefused(f"An engine named {provider.name} already exists.")
            proposed = self._validated(current.model_copy(
                update={"providers": [*current.providers, provider]}, deep=True), sent)  # fmt: skip
            await self._reconcile(proposed)
            self._save(proposed)

        await self._change(by, "engine_added", provider.name, work)
        await self._audited(
            by, "engine_added", provider.name,
            {f: {"from": None, "to": _plain(getattr(provider, f))} for f in _EDITABLE},
        )  # fmt: skip

    async def edit_engine(self, by: str, name: str, provider: ModelProviderConfig) -> str | None:
        """Save an edited engine. **Changing its address removes its key** (the owner's ruling,
        decision 1): the address decides where the key is sent, so a key entered for one address
        is never sent to another; it is asked for again, in words. Returns those words, if so."""
        sent = sent_values(provider)
        moved: list[bool] = []

        async def work(current: ModelSettings) -> ModelProviderConfig:
            if provider.name != name:
                raise ModelAdminRefused("An engine's provider name cannot change; add a new one.")
            before = next((p for p in current.providers if p.name == name), None)
            if before is None:
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            proposed = self._validated(current.model_copy(
                update={"providers": [provider if p.name == name else p
                                      for p in current.providers]}, deep=True), sent)  # fmt: skip
            if (before.api_base or None) != (provider.api_base or None):
                await self._gateway.delete_credential(name)
                moved.append(True)
                kept = {k: v for k, v in proposed.keys.items() if k != name}
                proposed = proposed.model_copy(update={"keys": kept}, deep=True)
            await self._reconcile(proposed, rebuilt=frozenset({name}))
            self._save(proposed)
            return before

        before = await self._change(by, "engine_edited", name, work, rebuilt=frozenset({name}))
        changes = {
            f: {"from": _plain(getattr(before, f)), "to": _plain(getattr(provider, f))}
            for f in _EDITABLE
            if getattr(before, f) != getattr(provider, f)
        }
        await self._audited(by, "engine_edited", name, changes)
        if moved:
            await self._audited(
                by, "key_removed", name, outcome="done: the engine's address changed"
            )
            return (
                f"{provider.label or name}'s address changed, so its key was removed: the key "
                "is never sent to an address it was not entered for. Enter it again."
            )
        return None

    async def remove_engine(self, by: str, name: str) -> None:
        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            roles = sorted(r for r, e in current.defaults.items() if e == name)
            if roles:
                raise ModelAdminRefused(
                    f"{name} is the default engine for {', '.join(roles)}; choose another default "
                    "first."
                )
            keys = {k: v for k, v in current.keys.items() if k != name}
            limits = {k: v for k, v in current.limits.items() if k != name}
            proposed = current.model_copy(update={
                "providers": [p for p in current.providers if p.name != name], "keys": keys,
                "limits": limits,
            }, deep=True)  # fmt: skip
            # Removing is always allowed, local only or not: it can only narrow what leaves.
            await self._reconcile(proposed)
            # The engine's own key first: if its removal is refused, the credential is still there,
            # so the entries put back answer and the file's "key set" stays true.
            await self._gateway.delete_engine_key(name)
            await self._gateway.delete_credential(name)
            self._save(proposed)

        await self._change(by, "engine_removed", name, work)
        await self._audited(by, "engine_removed", name)

    async def set_defaults(self, by: str, defaults: Mapping[str, str]) -> None:
        sent = sent_values(dict(defaults))
        before: dict[str, str] = {}

        async def work(current: ModelSettings) -> None:
            before.update(current.defaults)
            proposed = self._validated(
                current.model_copy(update={"defaults": dict(defaults)}, deep=True), sent
            )
            self._save(proposed)

        await self._change(by, "default_changed", None, work)
        changes: dict[str, dict[str, object]] = {
            r: {"from": before.get(r, LOCAL), "to": defaults.get(r, LOCAL)}
            for r in ROLES
            if before.get(r, LOCAL) != defaults.get(r, LOCAL)
        }
        await self._audited(by, "default_changed", None, changes)

    async def set_key(
        self, by: str, name: str, key: SecretStr, *, action: ModelAdminAction | None = None
    ) -> None:
        """Set, rotate or enter again `name`'s key. `action` names it otherwise in the audit
        (`key_moved`, from `deployment.env`, ADR-135 Amendment 2 decision 3). **A rotation the
        gateway refuses after the old key was removed is recorded truthfully**: the engine's key
        is then lost, and it is offered to no analyst until a key is entered again."""
        said: list[ModelAdminAction] = [action or "key_set"]
        text = key.get_secret_value()

        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            if self._installed.local_only:
                raise ModelAdminRefused(
                    "This deployment's osprey.yaml declares local_only: true, so no key for an "
                    "engine outside it is taken here."
                )
            if not text.strip() or any(ch.isspace() for ch in text):
                raise ModelAdminRefused(
                    "A key has no spaces or line breaks in it; nothing was changed."
                )
            record = current.keys.get(name)
            said[0] = action or ("key_rotated" if record and not record.lost else "key_set")
            try:
                await self._gateway.put_credential(name, key)
            except KeyRemovedNotReplaced as gone:
                if record is not None:
                    keys = {**current.keys, name: record.model_copy(update={"lost": True})}
                    self._save(current.model_copy(update={"keys": keys}, deep=True))
                raise ModelAdminRefused(gone.words, status=gone.status) from None
            await self._reconcile(current)
            keys = {**current.keys, name: KeyRecord(set_at=self._now(), set_by=by)}
            self._save(current.model_copy(update={"keys": keys}, deep=True))

        await self._change(by, said[0], name, work)
        await self._audited(by, said[0], name)

    async def remove_key(self, by: str, name: str) -> None:
        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            await self._gateway.delete_credential(name)
            keys = {k: v for k, v in current.keys.items() if k != name}
            self._save(current.model_copy(update={"keys": keys}, deep=True))

        await self._change(by, "key_removed", name, work)
        await self._audited(by, "key_removed", name)

    async def set_limits(self, by: str, name: str, limits: EngineLimits) -> None:
        """An engine's limits (ADR-135 Amendment 3), applied by the gateway to the engine's key at
        once, then kept in the models file and audited with each changed value."""
        before: list[EngineLimits] = []

        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            if self._installed.local_only:
                raise ModelAdminRefused(
                    "This deployment's osprey.yaml declares local_only: true, so no engine outside "
                    "it is asked anything and there is nothing to limit."
                )
            before.append(current.limits.get(name, EngineLimits()))
            provider = next(p for p in current.providers if p.name == name)
            await self._gateway.put_engine_key(provider, limits)
            kept = {**current.limits, name: limits}
            self._save(current.model_copy(update={"limits": kept}, deep=True))

        await self._change(by, "limits_changed", name, work)
        old, new = before[0].model_dump(), limits.model_dump()
        changes: dict[str, dict[str, object]] = {
            f: {"from": old[f], "to": new[f]} for f in new if old[f] != new[f]
        }
        await self._audited(by, "limits_changed", name, changes)

    async def test(self, by: str, name: str) -> ConnectionTestResult:
        try:
            provider = self._provider(name)
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "connection_tested", name, refused) from None
        state = self.key_state(name)
        if self._installed.local_only:
            result = ConnectionTestResult(
                engine=name, outcome="not_routed", ok=False,
                words="This deployment is local only: no engine outside it is asked anything.",
            )  # fmt: skip
        elif state != "set":
            words = (
                "The gateway no longer holds this engine's key. Enter it again first."
                if state == "lost"
                else "This engine has no key on this deployment. Enter one first."
            )
            result = ConnectionTestResult(engine=name, outcome="key_refused", ok=False, words=words)
        else:
            model = next(iter(provider.roles.values()))
            # Tagged as the engine's `test` job, so the usage counts it apart (P2's review).
            check = await check_connection(
                self._gateway.http, gateway_model_name(provider.name, model),
                tag=usage_tag(provider.name, "test"),
            )
            result = ConnectionTestResult(
                engine=name, outcome=check.outcome, ok=check.ok, words=check.words
            )
        await self._audited(by, "connection_tested", name, outcome=result.outcome)
        return result


def _said(failed: BaseException) -> str:
    return failed.words if isinstance(failed, ModelAdminRefused) else type(failed).__name__


def _number(value: object) -> float | None:
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return value
