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

**A key passes through and is kept by nothing here** (decision 4): it arrives as a `SecretStr`, is
revealed once, inside the request body sent to the gateway, and is never logged, returned or
written. The gateway's answers are never passed on: they can carry part of a key (measured), so a
failure is reported in fixed words with its HTTP status alone. And the Conduit never reads
credentials back (`GET /credentials` answers with two characters at each end of the key).
"""

from __future__ import annotations

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
from schemas.deployment import ModelProviderConfig, ModelsConfig
from schemas.model_admin import (
    AdminEngine,
    ConnectionTestResult,
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


# --- the models file ---------------------------------------------------------------------------


class KeyRecord(BaseModel):
    set_at: datetime
    set_by: str


class ModelSettings(BaseModel):
    """What the models file holds. `providers` and `defaults` replace `osprey.yaml`'s whole."""

    providers: list[ModelProviderConfig] = Field(default_factory=list)
    defaults: dict[str, str] = Field(default_factory=dict)
    keys: dict[str, KeyRecord] = Field(default_factory=dict)


class ModelSettingsFile:
    def __init__(self, folder: Path) -> None:
        self.path = folder / SETTINGS_FILE

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> ModelSettingsFile:
        return cls(Path(environ.get("OSPREY_MODEL_SETTINGS_DIR", DEFAULT_SETTINGS_DIR)))

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


class GatewayAdmin:
    """LiteLLM's admin API, as measured (ADR-135 Amendment 2). Every failure becomes a
    `ModelAdminRefused` with fixed words and the status alone."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    async def _call(self, method: str, path: str, body: object | None = None) -> httpx.Response:
        try:
            resp = await self._http.request(method, path, json=body, timeout=30.0)
        except httpx.HTTPError:
            raise ModelAdminRefused(
                "The model gateway could not be reached; nothing was changed.", status=502
            ) from None
        return resp

    def _refused(self, resp: httpx.Response, what: str) -> ModelAdminRefused:
        return ModelAdminRefused(
            f"The model gateway refused {what} (HTTP {resp.status_code}). Run ospreyflow doctor.",
            status=502,
        )

    async def stored_entries(self) -> set[str]:
        resp = await self._call("GET", "/v2/model/info")
        if resp.status_code != 200:
            raise self._refused(resp, "the list of engines")
        ids: set[str] = set()
        for row in resp.json().get("data", []):
            model_id = str(dict(row.get("model_info") or {}).get("id") or "")
            if model_id.startswith("osprey-"):
                ids.add(model_id)
        return ids

    async def put_entry(self, provider: ModelProviderConfig, model: str, exists: bool) -> None:
        params: dict[str, object] = {
            "model": gateway_model_name(provider.name, model),
            "litellm_credential_name": credential_name(provider.name),
        }
        if provider.api_base:
            params["api_base"] = provider.api_base
        model_id = entry_id(provider.name, model)
        if exists:
            resp = await self._call(
                "PATCH", f"/model/{model_id}/update", {"litellm_params": params}
            )
        else:
            resp = await self._call(
                "POST",
                "/model/new",
                {
                    "model_name": gateway_model_name(provider.name, model),
                    "litellm_params": params,
                    "model_info": {"id": model_id},
                },
            )
        if resp.status_code != 200:
            raise self._refused(resp, f"the model {model}")

    async def delete_entry(self, model_id: str) -> None:
        resp = await self._call("POST", "/model/delete", {"id": model_id})
        if resp.status_code not in (200, 400):  # 400: already gone (measured)
            raise self._refused(resp, "a model's removal")

    async def set_credential(self, provider: str, key: SecretStr, *, exists: bool) -> None:
        body = {
            "credential_name": credential_name(provider),
            "credential_values": {"api_key": key.get_secret_value()},
            "credential_info": {},
        }
        if exists:
            resp = await self._call("PATCH", f"/credentials/{credential_name(provider)}", body)
            if resp.status_code == 404:  # the record outlived the credential: make it again
                resp = await self._call("POST", "/credentials", body)
        else:
            resp = await self._call("POST", "/credentials", body)
        if resp.status_code != 200:
            raise self._refused(resp, "the key")

    async def delete_credential(self, provider: str) -> None:
        resp = await self._call("DELETE", f"/credentials/{credential_name(provider)}")
        if resp.status_code not in (200, 404):  # 404: none was held (measured)
            raise self._refused(resp, "the key's removal")


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


class ModelAdmin:
    def __init__(
        self,
        *,
        installed: Installed,
        settings_file: ModelSettingsFile,
        gateway: GatewayAdmin,
        audit: ModelAdminAudit,
        on_change: Callable[[ModelRoutes], None] = lambda _routes: None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._installed = installed
        self._file = settings_file
        self._gateway = gateway
        self._audit = audit
        self._on_change = on_change
        self._now = now
        self._settings = settings_file.load()
        #: Engines whose record says "key set" but the gateway no longer holds (decision 9).
        self.lost: set[str] = set()

    # --- reading --------------------------------------------------------------------------

    @property
    def settings(self) -> ModelSettings:
        if self._settings is not None:
            return self._settings
        return ModelSettings(
            providers=list(self._installed.providers),
            defaults=dict(self._installed.defaults),
        )

    def key_state(self, name: str) -> KeyState:
        if self._settings is None:
            return "set" if self._installed.key_present.get(name) else "none"
        if name in self.lost:
            return "lost"
        return "set" if name in self._settings.keys else "none"

    def routes(self) -> ModelRoutes:
        """The routing's view (`model_routing.ModelRoutes`), from what *Models* holds now."""
        current = self.settings
        engines = {
            p.name: Engine(
                name=p.name,
                label=p.label or p.name,
                models={r: gateway_model_name(p.name, m) for r, m in p.roles.items() if r in ROLES},
                key_present=self.key_state(p.name) == "set",
                privacy_contract=p.privacy_contract,
                contract_reference=p.contract_reference,
            )
            for p in current.providers
        }
        return ModelRoutes(
            locals=cast(dict[Role, str | None], dict(self._installed.locals)),
            engines=engines,
            defaults={r: e for r, e in current.defaults.items() if r in ROLES},
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
                )
                for p in current.providers
            ],
            defaults=dict(current.defaults),
            local_models=dict(self._installed.locals),
            local_only=self._installed.local_only,
            sendable_handling_codes=list(self._installed.sendable),
            source="models file" if self._settings is not None else "osprey.yaml",
        )

    async def history(self) -> list[ModelAdminEntry]:
        return await self._audit.recent()

    # --- the gateway, kept equal to the settings --------------------------------------------

    async def start(self) -> None:
        """At start: find engines whose key the gateway lost, then make its entries equal the
        settings. A gateway that cannot be reached is logged in words, and *Models* says so when it
        is next used."""
        if self._settings is None:
            return
        try:
            held = await self._gateway.stored_entries()
            for p in self._settings.providers:
                if p.name in self._settings.keys:
                    wanted = {entry_id(p.name, m) for m in p.roles.values()}
                    if not wanted & held:
                        self.lost.add(p.name)
            await self._reconcile(held)
        except ModelAdminRefused as refused:
            log.warning("model engines not reconciled with the gateway: %s", refused.words)
        self._on_change(self.routes())

    async def _reconcile(self, held: set[str] | None = None) -> None:
        held = await self._gateway.stored_entries() if held is None else held
        wanted: dict[str, tuple[ModelProviderConfig, str]] = {}
        for p in self.settings.providers:
            for model in dict.fromkeys(p.roles.values()):
                wanted[entry_id(p.name, model)] = (p, model)
        for model_id in sorted(held - set(wanted)):
            await self._gateway.delete_entry(model_id)
        for model_id, (p, model) in wanted.items():
            await self._gateway.put_entry(p, model, exists=model_id in held)

    # --- changing -------------------------------------------------------------------------

    def _validated(self, settings: ModelSettings) -> ModelSettings:
        if settings.providers and self._installed.local_only:
            raise ModelAdminRefused(
                "This deployment's osprey.yaml declares local_only: true, so no engine outside it "
                "may be added here. The installer changes that declaration (local_only: false, "
                "then ospreyflow apply)."
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
            raise ModelAdminRefused(words) from None
        return settings

    async def _commit(self, settings: ModelSettings) -> None:
        self._file.save(settings)
        self._settings = settings
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
        raise ModelAdminRefused(f"There is no engine named {name} on this deployment.", status=404)

    async def _refusing(
        self, by: str, action: ModelAdminAction, engine: str | None, refused: ModelAdminRefused
    ) -> ModelAdminRefused:
        await self._audited(by, action, engine, outcome=f"refused: {refused.words}")
        return refused

    async def add_engine(self, by: str, provider: ModelProviderConfig) -> None:
        try:
            if any(p.name == provider.name for p in self.settings.providers):
                raise ModelAdminRefused(f"An engine named {provider.name} already exists.")
            current = self.settings
            proposed = self._validated(current.model_copy(
                update={"providers": [*current.providers, provider]}, deep=True))  # fmt: skip
            await self._commit(proposed)
            await self._reconcile()
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "engine_added", provider.name, refused) from None
        await self._audited(
            by, "engine_added", provider.name,
            {f: {"from": None, "to": _plain(getattr(provider, f))} for f in _EDITABLE},
        )  # fmt: skip

    async def edit_engine(self, by: str, name: str, provider: ModelProviderConfig) -> None:
        try:
            if provider.name != name:
                raise ModelAdminRefused("An engine's provider name cannot change; add a new one.")
            before = self._provider(name)
            current = self.settings
            proposed = self._validated(current.model_copy(
                update={"providers": [provider if p.name == name else p
                                      for p in current.providers]}, deep=True))  # fmt: skip
            await self._commit(proposed)
            await self._reconcile()
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "engine_edited", name, refused) from None
        changes = {
            f: {"from": _plain(getattr(before, f)), "to": _plain(getattr(provider, f))}
            for f in _EDITABLE
            if getattr(before, f) != getattr(provider, f)
        }
        await self._audited(by, "engine_edited", name, changes)

    async def remove_engine(self, by: str, name: str) -> None:
        try:
            self._provider(name)
            current = self.settings
            roles = sorted(r for r, e in current.defaults.items() if e == name)
            if roles:
                raise ModelAdminRefused(
                    f"{name} is the default engine for {', '.join(roles)}; choose another default "
                    "first."
                )
            keys = {k: v for k, v in current.keys.items() if k != name}
            proposed = self._validated(current.model_copy(update={
                "providers": [p for p in current.providers if p.name != name], "keys": keys,
            }, deep=True))  # fmt: skip
            await self._commit(proposed)
            await self._reconcile()
            await self._gateway.delete_credential(name)
            self.lost.discard(name)
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "engine_removed", name, refused) from None
        await self._audited(by, "engine_removed", name)

    async def set_defaults(self, by: str, defaults: Mapping[str, str]) -> None:
        try:
            current = self.settings
            proposed = self._validated(
                current.model_copy(update={"defaults": dict(defaults)}, deep=True)
            )
            await self._commit(proposed)
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "default_changed", None, refused) from None
        changes: dict[str, dict[str, object]] = {
            r: {"from": current.defaults.get(r, LOCAL), "to": defaults.get(r, LOCAL)}
            for r in ROLES
            if current.defaults.get(r, LOCAL) != defaults.get(r, LOCAL)
        }
        await self._audited(by, "default_changed", None, changes)

    async def set_key(self, by: str, name: str, key: SecretStr) -> None:
        action: ModelAdminAction = "key_set"
        try:
            self._provider(name)
            current = self.settings
            had = name in current.keys and name not in self.lost
            action = "key_rotated" if had else "key_set"
            await self._gateway.set_credential(name, key, exists=name in current.keys)
            keys = {**current.keys, name: KeyRecord(set_at=self._now(), set_by=by)}
            await self._commit(current.model_copy(update={"keys": keys}, deep=True))
            self.lost.discard(name)
            await self._reconcile()
            self._on_change(self.routes())
        except ModelAdminRefused as refused:
            raise await self._refusing(by, action, name, refused) from None
        await self._audited(by, action, name)

    async def remove_key(self, by: str, name: str) -> None:
        try:
            self._provider(name)
            await self._gateway.delete_credential(name)
            current = self.settings
            keys = {k: v for k, v in current.keys.items() if k != name}
            await self._commit(current.model_copy(update={"keys": keys}, deep=True))
            self.lost.discard(name)
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "key_removed", name, refused) from None
        await self._audited(by, "key_removed", name)

    async def test(self, by: str, name: str) -> ConnectionTestResult:
        try:
            provider = self._provider(name)
        except ModelAdminRefused as refused:
            raise await self._refusing(by, "connection_tested", name, refused) from None
        if self.key_state(name) != "set":
            result = ConnectionTestResult(
                engine=name, outcome="key_refused", ok=False,
                words="This engine has no key on this deployment. Enter one first.",
            )  # fmt: skip
        else:
            model = next(iter(provider.roles.values()))
            check = await check_connection(
                self._gateway.http, gateway_model_name(provider.name, model)
            )
            result = ConnectionTestResult(
                engine=name, outcome=check.outcome, ok=check.ok, words=check.words
            )
        await self._audited(by, "connection_tested", name, outcome=result.outcome)
        return result


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return value
