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
import contextlib
import fcntl
import json
import logging
import os
import re
import secrets
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlsplit

import asyncpg
import httpx
import yaml
from pydantic import BaseModel, Field, SecretStr, ValidationError

from adapters.model_litellm.connection import WORDS, check_connection
from adapters.model_litellm.usage import engine_key, usage_tag
from schemas.deployment import (
    BEDROCK_REGION,
    MODEL_ROUTE_PROFILE,
    ModelProviderConfig,
    ModelsConfig,
    engine_kinds_offered,
    engine_refusal,
    label_looks_like_a_key,
    model_looks_like_a_key,
)
from schemas.model_admin import (
    AdminEngine,
    CatalogueEntry,
    ConnectionOutcome,
    ConnectionTestResult,
    EngineCheckResult,
    EngineLimits,
    HeldCheck,
    KeyState,
    ModelAdminAction,
    ModelAdminEntry,
    ModelCheck,
    ModelsAdminView,
)

from . import model_catalogue
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


class GatewayUnanswered(ModelAdminRefused):
    """The gateway gave no answer (a transport failure): the request may have landed, and the code
    cannot tell. A refusal the gateway *answered* is a plain `ModelAdminRefused`: that write did not
    land (ADR-135 Amendment 14 point 9)."""


@dataclass(frozen=True)
class Undone:
    """What an undo did: `restored` is true only when the gateway was made equal to the saved
    settings **and** no engine's credential may still hold a key it was not given for; `held` names
    the engines whose credential the gateway would not remove."""

    restored: bool
    held: frozenset[str] = frozenset()


# --- the models file ---------------------------------------------------------------------------


class KeyRecord(BaseModel):
    set_at: datetime
    set_by: str
    #: The gateway no longer holds it (decision 9: a restore from another deployment, or its
    #: encryption key changed). Kept here, so every process and replica, and the command line,
    #: says the same until it is entered again.
    lost: bool = False


class Intent(BaseModel):
    """A **note of intent** (ADR-135 Amendment 14 point 9, the owner's ruling of 20 November 2026):
    saved before a credential is deleted or stored, cleared when the change is complete. A note
    still there means the credential's state may not be the record's: a change was cut short (the
    process stopped, the task was cancelled, an answer was lost, a save failed). It holds no key."""

    at: datetime
    by: str


#: How long a passed check waits for **Add** (ADR-135 Amendment 14 point 2).
CHECK_LIFE = timedelta(minutes=15)


class PendingCheck(BaseModel):
    """A passed check, waiting for **Add**: the engine as it was checked, who checked it and when.
    Its key is the gateway's own credential, never here. Kept in the models file, so **Add** on
    another Conduit replica finds it."""

    provider: ModelProviderConfig
    by: str
    at: datetime
    #: False from before the key goes to the gateway until every model has answered (the owner's
    #: ruling 25): a Conduit stopped between the two leaves this record, which the sweep removes
    #: with its credential after `CHECK_LIFE`, so no credential is ever read back to find it.
    passed: bool = True


class ModelSettings(BaseModel):
    """What the models file holds. `providers` and `defaults` replace `osprey.yaml`'s whole."""

    providers: list[ModelProviderConfig] = Field(default_factory=list)
    defaults: dict[str, str] = Field(default_factory=dict)
    keys: dict[str, KeyRecord] = Field(default_factory=dict)
    #: Each engine's limits (ADR-135 Amendment 3); an engine not here has none.
    limits: dict[str, EngineLimits] = Field(default_factory=dict)
    #: Passed checks waiting for **Add**, by their id (ADR-135 Amendment 14). An engine here is not
    #: an engine: it is offered to nobody and routed nowhere.
    checks: dict[str, PendingCheck] = Field(default_factory=dict)
    #: Notes of intent, by the name of the credential's holder: an engine's name for its own
    #: credential, `probe_name(engine)` for a check's probe, a new engine's name for a check's key.
    #: Start-up marks every engine with a note unavailable and settles the note (`_resolve`); it
    #: reads no credential, because the gateway's listing returns part of each key.
    intents: dict[str, Intent] = Field(default_factory=dict)


#: The fields Amendment 4 added to an engine. Off `cloud-platform` every engine is a plain provider
#: and they are not written, so the models file and the Conduit's environment there are as before.
_KIND_FIELDS = ("kind", "auth", "region")


def plain_dump(provider: ModelProviderConfig) -> dict[str, Any]:
    """An engine as written down: Amendment 4's fields left out for a plain provider by its key."""
    dumped = provider.model_dump(mode="json")
    if provider.plain:
        for name in _KIND_FIELDS:
            dumped.pop(name, None)
    return dumped


def refused_on(providers: Sequence[ModelProviderConfig], profile: str) -> str | None:
    """The first engine `profile` refuses, in words naming it (ADR-135 Amendment 7 decision 1)."""
    for provider in providers:
        if refused := engine_refusal(provider, profile):
            return f"{provider.name}: {refused}"
    return None


class ModelSettingsFile:
    def __init__(self, folder: Path, *, profile: str = "") -> None:
        self.path = folder / SETTINGS_FILE
        #: The deployment's profile (`OSPREY_PROFILE`, rendered into `deployment.env` for every
        #: profile), which decides which engines the file may hold (ADR-135 Amendment 7).
        self.profile = profile

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> ModelSettingsFile:
        return cls(
            Path(environ.get("OSPREY_MODEL_SETTINGS_DIR", DEFAULT_SETTINGS_DIR)),
            profile=environ.get("OSPREY_PROFILE", ""),
        )

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
        settings = ModelSettings.model_validate(raw)
        if refused := refused_on(settings.providers, self.profile):
            raise ValueError(f"the models file {self.path} holds an engine refused here: {refused}")
        return settings

    def save(self, settings: ModelSettings) -> None:
        """Atomic, and `600` from the moment it exists (a temporary file renamed over the old)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        dumped = settings.model_dump(mode="json")
        dumped["providers"] = [plain_dump(p) for p in settings.providers]
        text = yaml.safe_dump(dumped, sort_keys=False)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".models-", suffix=".yaml")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


#: The words for an engine the cloud-platform render did not make a way out (or, for Bedrock, an
#: identity) for (the orchestrator's ruling on P11 part 2, round 1).
NOT_MADE = (
    "On this deployment an engine is reached only once the render has made its way out of the "
    "namespace{identity}, and it made none for this engine{name}. Declare it in osprey.yaml, "
    "re-render, and have the platform team apply the Terraform; then it can be enabled here."
)


@dataclass(frozen=True)
class RoutesMade:
    """What the cloud-platform render made for the model route (`OSPREY_MODEL_ROUTES_MADE`): the
    engine hosts the namespace may reach, the rules that place an engine's host, and whether the
    gateway's own IAM role (Bedrock's) exists."""

    hosts: frozenset[str]
    provider_hosts: dict[str, str]
    kind_hosts: dict[str, str]
    gateway_identity: bool

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> RoutesMade | None:
        text = environ.get("OSPREY_MODEL_ROUTES_MADE", "").strip()
        if not text:
            return None
        raw = json.loads(text)
        return cls(
            hosts=frozenset(str(h) for h in raw.get("hosts") or []),
            provider_hosts={str(k): str(v) for k, v in (raw.get("provider_hosts") or {}).items()},
            kind_hosts={str(k): str(v) for k, v in (raw.get("kind_hosts") or {}).items()},
            gateway_identity=raw.get("gateway_identity") is True,
        )

    def host_of(self, provider: ModelProviderConfig) -> str | None:
        """The engine's one host, as the render places it (`harness.cloud_platform.engine_host`)."""
        if provider.api_base:
            return urlsplit(provider.api_base).hostname
        if provider.kind in self.kind_hosts:
            return self.kind_hosts[provider.kind].format(region=provider.region or BEDROCK_REGION)
        return self.provider_hosts.get(provider.name)

    def refusal(self, provider: ModelProviderConfig) -> str | None:
        """Why `provider` cannot be enabled here, in words naming no value, or None."""
        host = self.host_of(provider)
        identity = provider.kind == "bedrock" and not self.gateway_identity
        if host in self.hosts and not identity:
            return None
        return NOT_MADE.format(
            identity=" (and, for Bedrock, the gateway's own IAM role)" if identity else "",
            name=f" ({provider.name})" if re.fullmatch(r"[a-z0-9_]{1,40}", provider.name) else "",
        )


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
    #: What the cloud-platform render made (None on every other profile, which allows any host).
    made: RoutesMade | None = None
    #: ADR-135 Amendment 9: the extraction engine the render chose (`OSPREY_EXTRACTION_ENGINE`).
    extraction_engine: Literal["deep_read", "laurium"] = "deep_read"

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
                    # ADR-135 Amendment 4: what the engine is and how it signs in.
                    kind=raw.get("kind") or "provider",
                    auth=raw.get("auth"),
                    region=raw.get("region"),
                )
            )
            present[name] = environ.get(f"OSPREY_MODEL_KEY_PRESENT_{name.upper()}", "") == "yes"
        if refused := refused_on(providers, environ.get("OSPREY_PROFILE", "")):
            raise ValueError(f"OSPREY_MODEL_ENGINES names an engine refused here: {refused}")
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
            made=RoutesMade.from_env(environ),
            extraction_engine=(
                "laurium" if environ.get("OSPREY_EXTRACTION_ENGINE") == "laurium" else "deep_read"
            ),
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


_PROBE_SUFFIX = ".check"


def probe_name(provider: str) -> str:
    """An edit's check's own credential (the owner's ruling 19; ADR-135 Amendment 14), beside the
    live engine's, which it never touches. No engine can be named so: an engine's name has no dot
    (`schemas.deployment`)."""
    return f"{provider}{_PROBE_SUFFIX}"


def probe_entries(provider: str) -> str:
    """The name one check's entries are made and asked under, used once: the gateway cools a refused
    entry down for about a minute, its name with it even once deleted (measured on 8 November), so
    a check under a name used again would hold back the next check, or the engine itself."""
    return f"{probe_name(provider)}-{secrets.token_hex(4)}"


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


@dataclass(frozen=True)
class HeldEntry:
    """A model entry the gateway holds: whether it is priced a unit a token, and **the address it
    carries** (`api_base`; None where it carries none or the gateway shows none). An entry names its
    engine's one credential and is sent there, so its address is where that key goes."""

    priced: bool
    api_base: str | None


def _same_address(held: HeldEntry, provider: ModelProviderConfig) -> bool:
    """Whether the entry is at the address the record gives the engine. An address the gateway does
    not show reads as none, so an engine with an address and an entry showing none disagree: the
    check fails closed, never open."""
    return (held.api_base or None) == (provider.api_base or None)


class GatewayAdmin:
    """LiteLLM's admin API, as measured (ADR-135 Amendments 2 and 3). Every failure becomes a
    `ModelAdminRefused` with fixed words and the status alone."""

    def __init__(self, http: httpx.AsyncClient, *, master: str | None = None) -> None:
        self._http = http
        # The master key the client already carries; each engine's key is derived from it.
        self._master = master or str(http.headers.get("authorization", "")).removeprefix("Bearer ")
        #: How many requests that may change the gateway have been sent (answered or not), so a
        #: change that failed can say whether it had begun to change anything.
        self.writes = 0
        self._probing = 0

    @contextlib.contextmanager
    def probing(self) -> Iterator[None]:
        """Writes to a check's own credential and entries (`probe_name`) are not counted: they are
        never the live engine's, so a change that wrote only those has nothing to put back."""
        self._probing += 1
        try:
            yield
        finally:
            self._probing -= 1

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    async def _call(self, method: str, path: str, body: object | None = None) -> httpx.Response:
        if method != "GET" and not self._probing:
            self.writes += 1
        try:
            resp = await self._http.request(method, path, json=body, timeout=30.0)
        except httpx.HTTPError:
            raise GatewayUnanswered(
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
        return set(await self.held_entries())

    async def entries(self) -> dict[str, bool]:
        """Each entry the Conduit made, and whether it is priced a unit a token (an entry made
        before ADR-135 Amendment 3 is not, so its engine's budget would never be reached)."""
        return {i: held.priced for i, held in (await self.held_entries()).items()}

    async def held_entries(self) -> dict[str, HeldEntry]:
        """Each entry the Conduit made, with whether it is priced a unit a token and the address
        it carries (read from `/v2/model/info`, which shows an entry's parameters, never its
        key)."""
        resp = await self._call("GET", "/v2/model/info")
        if resp.status_code != 200:
            raise self._refused(resp, "the list of engines")
        held: dict[str, HeldEntry] = {}
        for row in resp.json().get("data", []):
            model_id = str(dict(row.get("model_info") or {}).get("id") or "")
            if model_id.startswith("osprey-"):
                params = dict(row.get("litellm_params") or {})
                held[model_id] = HeldEntry(
                    priced=all(
                        _number(params.get(f)) == TOKEN_PRICE
                        for f in ("input_cost_per_token", "output_cost_per_token")
                    ),
                    api_base=str(params["api_base"]) if params.get("api_base") else None,
                )
        return held

    async def add_entry(
        self,
        provider: ModelProviderConfig,
        model: str,
        *,
        named: str | None = None,
        credential: str | None = None,
    ) -> None:
        """`POST /model/new` (measured). An entry is never patched: an edited engine's entries are
        deleted and made again, so no unmeasured partial update is relied on, and a cleared
        address leaves nothing of the old one behind. `named` and `credential` are an edit's check's
        (`probe_name`): its entry under its own name, using its own key or the engine's."""
        named = named or provider.name
        params: dict[str, object] = {
            "model": provider.route(model),
            "input_cost_per_token": TOKEN_PRICE,
            "output_cost_per_token": TOKEN_PRICE,
        }
        if not provider.keyless:
            params["litellm_credential_name"] = credential_name(credential or provider.name)
        # An IAM-role engine names no credential and carries no key of any kind (ADR-135
        # Amendment 4): Bedrock's calls are signed by the gateway pod's own identity, in London.
        if provider.region:
            params["aws_region_name"] = provider.region
        if provider.api_base:
            params["api_base"] = provider.api_base
        resp = await self._call(
            "POST",
            "/model/new",
            {
                "model_name": gateway_model_name(named, model),
                "litellm_params": params,
                "model_info": {"id": entry_id(named, model)},
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

_EDITABLE = (
    "label", "roles", "api_base", "privacy_contract", "contract_reference",
    "kind", "auth", "region",  # ADR-135 Amendment 4
)  # fmt: skip


#: A value that may be named in a refusal: shaped like a provider or a job (lower-case, short),
#: never like a key. Everything else a person sent is replaced by "…" in what the Conduit says back.
_NAMEABLE = re.compile(r"[a-z][a-z0-9_]{0,23}")

#: Each job as the screen names it (`Models.tsx`'s `ALL_JOBS`): a refusal says the job, never the
#: model name typed there (the owner's ruling 22).
JOB_WORDS = {
    "extraction": "Extraction and Ask",
    "vision": "Image description",
    "transcription": "Transcription",
    "embedding": "Embeddings",
}
#: What a model name looks like, generously (the owner's ruling 23): letters, digits and
#: . _ - : / @, up to 128 characters. It is not a key detector (an Azure deployment's or a client
#: gateway's model is named freely, so a lower-case hyphenated key has a model's shape); a refused
#: name is never echoed (ruling 22), and one the provider answers for is a model, not a key.
_MODEL_NAME = re.compile(r"[A-Za-z0-9._\-:/@]{1,128}")
#: A UUID is a key's shape and never a model's (the owner's review, Fix A).
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
#: Each field a refusal may name, in fixed words (the owner's review, Fix C): a validator's own
#: words may quote what it refused in another form (`repr` escapes a quote), which redaction
#: cannot find.
FIELD_WORDS = {
    "provider.name": "The engine's name is lower-case letters, digits and _, such as openai, and "
    "not local.",
    "provider.label": "The label is the words analysts see, on one line.",
    "provider.roles": "a model name is letters, digits and . _ - : / @, with no spaces, up to 128 "
    "characters.",
    "provider.api_base": "The address must be https://, so case content is encrypted.",
    "provider.contract_reference": "The agreement's reference is one line of letters, digits, "
    "spaces and . , ; : / ( ) & ' _ + -, and not a key.",
    "provider.privacy_contract": "The privacy contract is ticked or not.",
    "provider.kind": "This kind of engine is not one this form takes.",
    "provider.auth": "This way of signing in is not one this form takes.",
    "provider.region": "This region is not one this form takes.",
    "provider": "This engine's kind, sign-in and address do not fit together.",
    "key": "Give the key as text, with no spaces, at most 4096 characters.",
}
JOBS_ARE = "The jobs are extraction, vision, transcription and embedding."


def model_name_refusal(role: str, name: str) -> str | None:
    """Fixed words refusing `name` for `role`'s job, or None when it looks like a model name and not
    like a key. Never quotes the name."""
    job = JOB_WORDS.get(role, role)
    if not _MODEL_NAME.fullmatch(name):
        return f"{job}: {FIELD_WORDS['provider.roles']}"
    # Judged part by part between `:`, `/` and `@`, as a model's own tags are written
    # (`moondream:1.8b-v2-q4_K_M`); a key prefix starts the first part, a JWT has no such separator.
    parts = re.split(r"[:/@]", name)
    if any(model_looks_like_a_key(part) for part in parts) or _UUID.fullmatch(name):
        return (
            f"{job}: the model name looks like a key. Type the model's name in its job's field, "
            "and the key in the key field"
        )
    return None


def refused_field(loc: Sequence[object], words: str) -> tuple[str, str] | None:
    """The field a validation error names, and its fixed words, from `FIELD_WORDS` alone; None for a
    field not on the list (a name that was sent is never echoed: the owner's review, Fix B)."""
    parts = [str(p) for p in loc]
    words = words.removeprefix("Value error, ")
    if parts[:2] == ["provider", "roles"]:
        job: str | None = None
        if len(parts) > 2:
            if parts[2] not in JOB_WORDS:
                return "provider.roles", JOBS_ARE
            job = parts[2]
        elif found := re.match(r"the (\w+) model ", words):
            # The roles' rule names the job it refuses ("the vision model … is not a model name").
            job = found.group(1) if found.group(1) in JOB_WORDS else None
        if job is None:
            return "provider.roles", JOBS_ARE
        return f"provider.roles.{job}", f"{JOB_WORDS[job]}: {FIELD_WORDS['provider.roles']}"
    field = ".".join(parts[:2]) if parts[:1] == ["provider"] else ".".join(parts[:1])
    return (field, FIELD_WORDS[field]) if field in FIELD_WORDS and len(parts) <= 2 else None


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


#: *Test the connection*'s words for the two kinds of the `cloud-platform` profile (ADR-135
#: Amendment 7 decision 5), by kind and outcome; any other is `connection.WORDS`'. Bedrock has no
#: key to enter again, so its words name the role, the model's access or the credentials' renewal;
#: the client's gateway may refuse by its token or by its own policy, which the status cannot tell
#: apart, so its words name both.
KIND_WORDS: dict[tuple[str, str], str] = {
    ("bedrock", "key_refused"): (
        "Bedrock refused the gateway's own IAM role: the model gateway runs under no such role, "
        "or the role may not use this model in London. Ask your platform team to check the "
        "gateway's role (terraform/gateway.tf) and its service account, not the namespace's "
        "bucket role."
    ),
    ("bedrock", "model_not_enabled"): (
        "Bedrock accepted the gateway's own IAM role but has not enabled this model for the "
        "account: access is granted model by model (Bedrock's Model access, in London, "
        "eu-west-2). Ask your platform team to enable it; this is the model's access, not the "
        "role's permissions."
    ),
    ("bedrock", "sign_in_expired"): (
        "Bedrock refused the gateway's own IAM role's credentials as expired: the model gateway's "
        "pod did not renew them. Ask your platform team to check the gateway's service account, "
        "then restart the gateway."
    ),
    ("bedrock", "model_not_offered"): (
        "Bedrock does not offer this model on demand in London (eu-west-2) by this id. A "
        "cross-region inference profile is not used, as it may send the call outside London: "
        "choose a model Bedrock offers on demand in London."
    ),
    ("gateway", "key_refused"): (
        "Your organisation's AI gateway refused the call: its token may be wrong, or its own "
        "policy may not allow this model. Check both with the gateway's owners; enter the token "
        "again only if it has changed."
    ),
    ("gateway", "model_not_offered"): (
        "Your organisation's AI gateway does not offer this model to this token. Check the model "
        "name with the gateway's owners."
    ),
    ("gateway", "rate_limited"): (
        "Your organisation's AI gateway is limiting these calls (rate or quota). Try again later, "
        "or ask the gateway's owners about its limits."
    ),
    ("gateway", "request_refused"): (
        "Your organisation's AI gateway refused the request in a form OspreyFlow does not read "
        "(not an OpenAI-compatible answer): something in front of it may have refused it. Check "
        "the address and the model name with the gateway's owners."
    ),
}


def _without_note(settings: ModelSettings, name: str) -> ModelSettings:
    intents = {k: v for k, v in settings.intents.items() if k != name}
    return settings.model_copy(update={"intents": intents}, deep=True)


def _with_key(settings: ModelSettings, name: str, record: KeyRecord) -> ModelSettings:
    """`settings` with `name`'s key recorded as `record` and its note of intent cleared: the change
    is complete, and the record and the credential agree."""
    keys = {**settings.keys, name: record}
    intents = {k: v for k, v in settings.intents.items() if k != name}
    return settings.model_copy(update={"keys": keys, "intents": intents}, deep=True)


def _settled(settings: ModelSettings, name: str) -> ModelSettings:
    """`settings` once `name`'s credential has been removed: the note cleared, an engine's key
    recorded lost (it was removed, never restored), and the passed check of an engine not yet added
    taken away (its key is gone, so it must never be added). A probe's note names no engine."""
    keys, checks = dict(settings.keys), dict(settings.checks)
    if any(p.name == name for p in settings.providers):
        record = keys.get(name)
        if record is not None and not record.lost:
            keys[name] = record.model_copy(update={"lost": True})
    elif not name.endswith(_PROBE_SUFFIX):
        checks = {i: c for i, c in checks.items() if c.provider.name != name}
    intents = {k: v for k, v in settings.intents.items() if k != name}
    return settings.model_copy(
        update={"keys": keys, "checks": checks, "intents": intents}, deep=True
    )


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
        sweep_seconds: float = 60.0,
    ) -> None:
        self._retry_seconds = retry_seconds
        self._retrying: asyncio.Task[None] | None = None
        #: ADR-135 Amendment 14: how often a passed check past its 15 minutes is looked for.
        self._sweep_seconds = sweep_seconds
        self._sweeping: asyncio.Task[None] | None = None
        self._installed = installed
        self._file = settings_file
        self._gateway = gateway
        self._audit = audit
        self._on_change = on_change
        self._now = now
        self._settings = settings_file.load()
        self._stamp = settings_file.stamp()
        self._exclusive = _Exclusive(settings_file.path.parent)
        #: Engines whose gateway entries are known, or may be, not to agree with the record: a
        #: change that failed and could not be put back, or an entry at start that could not be
        #: withdrawn. Such an engine is offered to no analyst and its test says so, until a later
        #: reconcile makes the gateway equal to the record. Kept in this process: another process
        #: finds the same at its own start, and no key is ever held while an entry disagrees
        #: (`set_key` withdraws first; a moved address removes the key before anything is made).
        self._unavailable: set[str] = set()
        #: Engines whose credential the gateway would not remove while the record says their key is
        #: lost, so it may hold a key not given for the recorded address: they get no entry from any
        #: reconcile until a later one removes it. A subset of `_unavailable`.
        self._withheld: set[str] = set()

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
        state = self._recorded_key_state(name)
        if state == "set" and (name in self._unavailable or name in self.settings.intents):
            # A note outstanding is read from the file, so every replica says the same. To be
            # entered again: that is the repair (`set_key` makes it agree).
            return "lost"
        return state

    def _recorded_key_state(self, name: str) -> KeyState:
        self._fresh()
        if any(p.name == name and p.keyless for p in self.settings.providers):
            return "iam_role"
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
                # An IAM-role engine signs in with no key, so it is offered as a keyed one is.
                key_present=self.key_state(p.name) in ("set", "iam_role")
                and p.name not in self._unavailable,
                privacy_contract=p.privacy_contract,
                contract_reference=p.contract_reference,
                budget_period=current.limits.get(p.name, EngineLimits()).budget_period,
            )
            for p in current.providers
            if self._not_made(p) is None  # never offered unless the render made its way out
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
                    not_made=(
                        f"not made by the render: {refused}"
                        if (refused := self._not_made(p))
                        else None
                    ),
                )
                for p in current.providers
            ],
            defaults=dict(current.defaults),
            local_models=dict(self._installed.locals),
            local_only=self._installed.local_only,
            sendable_handling_codes=list(self._installed.sendable),
            source="models file" if self._settings is not None else "osprey.yaml",
            engine_kinds=engine_kinds_offered(self._file.profile),
            extraction_engine=self._installed.extraction_engine,
            providers=[
                CatalogueEntry(
                    id=e.id,
                    label=e.label,
                    kind=e.kind,
                    address=e.address,
                    address_asked=e.address_asked,
                    key=e.key,
                    example=e.example,
                    jobs=list(e.jobs),
                    prefix=e.prefix,
                    note=e.note,
                )
                for e in model_catalogue.providers(self._file.profile)
            ],
            # A check past its 15 minutes is not shown, though the next change removes it.
            checks=[
                HeldCheck(
                    id=i,
                    engine=c.provider.name,
                    label=c.provider.label or c.provider.name,
                    by=c.by,
                    at=c.at,
                    expires_at=c.at + CHECK_LIFE,
                )
                for i, c in current.checks.items()
                # One not yet passed is a check still running, or one stopped mid-way (ruling 25):
                # never offered for Add.
                if c.passed and self._now() - c.at <= CHECK_LIFE
            ],
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
        its calls would be refused.

        **Before anything is asked of the gateway, every engine with a note of intent outstanding
        is marked unavailable** (the owner's ruling of 20 November 2026): a change was cut short
        there, and what its credential holds is not known. Start then settles the note (`_resolve`)
        and reads no credential."""
        self._unavailable |= {
            p.name for p in self.settings.providers if p.name in self.settings.intents
        }
        try:
            done = await self._start_once()
        except Exception as failed:  # noqa: BLE001 - a garbled answer never stops the Conduit
            log.warning("model engines not reconciled with the gateway: %s",
                        type(failed).__name__)  # fmt: skip
            done = False
        if not done:
            self._retrying = asyncio.create_task(self._keep_trying())
        self._on_change(self.routes())
        # ADR-135 Amendment 14: a passed check not added is removed, key and all, within a sweep of
        # its 15 minutes, whether or not anyone asks anything of Models again.
        self._sweeping = asyncio.create_task(self._keep_sweeping())

    async def _keep_sweeping(self) -> None:
        while True:
            try:
                await self.sweep_checks()
            except Exception as failed:  # noqa: BLE001 - logged in words, then tried again
                log.warning("lapsed model checks not removed: %s", type(failed).__name__)
            await asyncio.sleep(self._sweep_seconds)

    async def sweep_checks(self) -> None:
        """Every passed check past `CHECK_LIFE` removed from the models file, its key from the
        gateway, each audited once as expired."""
        gone: list[str] = []
        async with self._exclusive:
            self._fresh()
            current = self.settings
            if not current.checks:
                return
            current, gone = await self._expired(current)
            if gone:
                self._save(current)
        await self._audit_expired(gone)

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
        """Stops the background retry and the checks' sweep, if they are running."""
        for task in (self._retrying, self._sweeping):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown goes on
                    pass
        self._retrying = None
        self._sweeping = None

    async def _start_once(self) -> bool:
        try:
            async with self._exclusive:
                self._fresh()
                held = await self._gateway.held_entries()
                # What a stopped change left: every note of intent settled first, so no entry is
                # made on a credential that may hold a key it was not given for (rows 15, 16, 36).
                outstanding = await self._resolve()
                current = self.settings
                await self._say_what_disagrees(current, held)
                # A check's own credential outlives a process stopped mid-check, with a models
                # file or none (a note cannot be written without taking `osprey.yaml`'s place), so
                # every engine's is removed here, before anything that can fail (row 21).
                await self._sweep_probes(current)
                if self._settings is None and not any(p.keyless for p in self._installed.providers):
                    # Before any change in *Models*, a keyed engine's entries are made when its key
                    # moves in. An IAM-role engine has no key to move (ADR-135 Amendment 4), so its
                    # entries and its own gateway key are made here, from `osprey.yaml`'s engines.
                    # Nothing is made here for a keyed one, but what disagrees with `osprey.yaml`
                    # (an engine it does not hold, an address it does not give) is withdrawn.
                    await self._withdraw_disagreeing(current, held)
                    self._unavailable.clear()
                    return True
                keys = dict(current.keys)
                for p in current.providers:
                    record = keys.get(p.name)
                    wanted = {entry_id(p.name, m) for m in p.roles.values()}
                    # An engine this process already knows is unavailable (a rebuild it began and
                    # could not finish) has no entries because of that, not because the gateway
                    # lost its state: its key is not marked lost on that account (row 37).
                    if (
                        record is not None
                        and not record.lost
                        and not wanted & set(held)
                        and p.name not in self._unavailable
                    ):
                        keys[p.name] = record.model_copy(update={"lost": True})
                if keys != current.keys:
                    self._save(current.model_copy(update={"keys": keys}, deep=True))
                unpriced = frozenset(
                    p.name for p in current.providers
                    if any(
                        entry_id(p.name, m) in held and not held[entry_id(p.name, m)].priced
                        for m in p.roles.values()
                    )
                )  # fmt: skip
                await self._reconcile(self.settings, held, rebuilt=unpriced)
            # An engine whose credential could not be removed is tried again by the retry, with
            # the others' work already done: it is withheld and unavailable meanwhile.
            return not self._withheld and not outstanding
        except (ModelAdminRefused, OSError) as failed:
            log.warning("model engines not reconciled with the gateway: %s", _said(failed))
            return False

    async def _sweep_probes(self, current: ModelSettings) -> None:
        """An edit's check removes its own credential whatever the answer; one cut short (the
        process stopped mid-check) is removed here, so no key outlives its check."""
        for p in current.providers:
            if not p.keyless:
                await self._gateway.delete_credential(probe_name(p.name))

    async def _say_what_disagrees(
        self, settings: ModelSettings, held: Mapping[str, HeldEntry]
    ) -> None:
        """At start, every entry's address is compared with the record. An engine whose entries are
        at another address is marked unavailable **before** a withdrawal is tried, so one that
        cannot be made leaves it so, and is said in words; an entry for an engine the record does
        not hold is said too. Both are then withdrawn by the reconcile that follows."""
        at_odds = self._disagreeing(self._hosted(settings), held)
        known = {p.name for p in settings.providers}
        engines = sorted({_owner(i) for i in at_odds} & known)
        for name in engines:
            self._unavailable.add(name)
            log.warning(
                "model engine %s: its gateway entries are at an address the saved settings do not "
                "give, so it is unavailable until they are withdrawn",
                name,
            )
        strays = [i for i in at_odds if _owner(i) not in known]
        if strays:
            log.warning(
                "the model gateway holds %d entries for an engine the saved settings do not hold; "
                "they are withdrawn",
                len(strays),
            )

    def _hosted(self, settings: ModelSettings) -> ModelSettings:
        """What the gateway should hold: nothing hosted while the deployment is local only, and on
        `cloud-platform` no engine the render did not make (a restored models file may name one;
        its stale entries are then deleted, never written; round 2's item 2)."""
        if self._installed.local_only:
            return settings.model_copy(update={"providers": []})
        made = [p for p in settings.providers if self._not_made(p) is None]
        if len(made) != len(settings.providers):
            return settings.model_copy(update={"providers": made})
        return settings

    def _wanted(self, settings: ModelSettings) -> dict[str, tuple[ModelProviderConfig, str]]:
        """The entries the record asks of the gateway, by id (`settings` already `_hosted`)."""
        wanted: dict[str, tuple[ModelProviderConfig, str]] = {}
        for p in settings.providers:
            for model in dict.fromkeys(p.roles.values()):
                wanted[entry_id(p.name, model)] = (p, model)
        return wanted

    def _disagreeing(self, settings: ModelSettings, held: Mapping[str, HeldEntry]) -> list[str]:
        """The held entries the record does not agree with: one for an engine it does not hold (or
        a model the engine no longer has), and one at **another address than the record gives its
        engine**. An entry names its engine's one credential and goes where its address says, so
        either could carry a key where it was not given (`settings` already `_hosted`)."""
        wanted = self._wanted(settings)
        return [
            i for i in sorted(held) if i not in wanted or not _same_address(held[i], wanted[i][0])
        ]

    async def _withdraw_disagreeing(
        self, settings: ModelSettings, held: Mapping[str, HeldEntry] | None = None
    ) -> None:
        """Every entry the record does not agree with deleted, and nothing made: what a key must
        wait for, so it never reaches an entry at an address the record does not give."""
        settings = self._hosted(settings)
        known = await self._gateway.held_entries() if held is None else held
        for model_id in self._disagreeing(settings, known):
            await self._gateway.delete_entry(model_id)

    async def _reconcile(
        self,
        settings: ModelSettings,
        held: Mapping[str, HeldEntry] | None = None,
        rebuilt: frozenset[str] = frozenset(),
    ) -> frozenset[str]:
        """The gateway's entries made equal to `settings`: stale ones, and ones at another address
        than the record gives, deleted; missing ones made; and every entry of an engine in `rebuilt`
        (just edited) deleted and made again. **An entry held under the right id at the wrong
        address is never kept**: it would send the engine's key there.

        **An engine with a note of intent outstanding is not given entries**: its credential may
        hold a key not given for the recorded address (a key typed for another address whose
        removal was refused or never finished; a process that stopped between the key and the
        record). It is *withheld*: no entry is made for it, those it has are deleted, and it is
        offered to no analyst until `_resolve` has removed the credential and cleared the note.
        This is a property of the record, so **every** caller (start, the retry, a key, a new
        engine, another engine's edit, the undo) keeps it. Returns the withheld engines. An engine
        is marked unavailable if this fails part-way for it, and the mark is cleared only for an
        engine this made whole."""
        settings = self._hosted(settings)
        known = await self._gateway.held_entries() if held is None else held
        withheld = {p.name for p in settings.providers if p.name in settings.intents}
        self._unavailable |= withheld
        self._withheld |= withheld
        live = settings.model_copy(
            update={"providers": [p for p in settings.providers if p.name not in withheld]}
        )
        wanted = self._wanted(live)
        at_odds = set(self._disagreeing(live, known))
        known_names = {p.name for p in live.providers}
        pending = (
            (rebuilt & known_names)
            | ({_owner(i) for i in at_odds} & known_names)
            | {wanted[i][0].name for i in wanted if i not in known}
        )
        try:
            remaining = set(known)
            for model_id in sorted(known):
                if model_id in at_odds or wanted[model_id][0].name in rebuilt:
                    await self._gateway.delete_entry(model_id)
                    remaining.discard(model_id)
            for model_id, (p, model) in wanted.items():
                if model_id not in remaining:
                    await self._gateway.add_entry(p, model)
            for p in live.providers:
                await self._gateway.put_engine_key(p, settings.limits.get(p.name, EngineLimits()))
            # No listing of the gateway's keys is asked for here or anywhere in the Conduit
            # (ADR-135 Amendment 14 point 9, the owner, 21 November 2026): it answers part of each
            # key (`key_name`), and the short form carries no tag to tell an engine's key apart.
        except BaseException:
            # Part-way: an engine whose entries were being changed is not whole, so none is
            # offered until a later reconcile finishes (never a log line alone: row 37).
            self._unavailable |= pending
            raise
        # Whole: the gateway holds what the record says for these. A mark stays on an engine this
        # did not make whole (withheld), and is dropped for one the record no longer holds.
        self._unavailable -= {p.name for p in live.providers}
        self._unavailable &= {p.name for p in settings.providers}
        self._withheld -= {p.name for p in live.providers}
        self._withheld &= {p.name for p in settings.providers}
        return frozenset(withheld)

    async def _put_back(self, rebuilt: frozenset[str]) -> Undone:
        """After a change failed part-way: every note of intent settled (a credential the change
        may have stored or deleted is removed, never restored: a key is never kept), then the
        gateway's entries made equal to the file again. `restored` only when both were. **Not
        restored is never only a log line**: the caller says it in words, marks the engine
        unavailable and audits it. Any failure counts, a named refusal or not; only a cancellation
        passes through."""
        try:
            outstanding = await self._resolve()
            await self._reconcile(self.settings, rebuilt=rebuilt)
        except asyncio.CancelledError:
            raise
        except Exception as failed:  # noqa: BLE001 - whatever stopped the undo is told, not lost
            log.error("model engines not put back after a failed change: %s", _said(failed))
            return Undone(False)
        return Undone(not self._withheld and not outstanding, frozenset(self._withheld))

    async def _undone(self, rebuilt: frozenset[str]) -> Undone:
        """`_put_back`, finished even when this task is cancelled meanwhile (the stop goes on once
        it is done), so an interrupted change never leaves what it made at a new address or a key
        in a credential."""
        task = asyncio.ensure_future(self._put_back(rebuilt))
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        return task.result()

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
        # ADR-135 Amendment 7 decision 1: what this deployment's profile takes.
        if refused := refused_on(settings.providers, self._file.profile):
            raise ModelAdminRefused(redacted(refused, sent))
        return settings

    def _made_by_the_render(self, provider: ModelProviderConfig) -> None:
        """On `cloud-platform`, an engine is enabled only where the render made its way out of the
        namespace and, for Bedrock, the gateway's own IAM role; anything else is refused in words
        before the gateway is asked (the orchestrator's ruling on P11 part 2, round 1). Every other
        profile reaches any host, as before."""
        if refused := self._not_made(provider):
            raise ModelAdminRefused(refused)

    def _not_made(self, provider: ModelProviderConfig) -> str | None:
        """Why `provider` is not one the render made, in words, or None (always None off
        `cloud-platform`). With no word from the render there, nothing is made (fails closed)."""
        if self._file.profile != MODEL_ROUTE_PROFILE:
            return None
        made = self._installed.made
        return made.refusal(provider) if made is not None else NOT_MADE.format(identity="", name="")

    def _save(self, settings: ModelSettings) -> None:
        self._file.save(settings)
        self._settings = settings
        self._stamp = self._file.stamp()
        self._on_change(self.routes())

    # --- the note of intent -------------------------------------------------------------------

    def _note(self, name: str, by: str) -> None:
        """Save a note of intent for the credential held under `name`, **before** it is deleted or
        stored. A file that cannot be written refuses the change here, with nothing done."""
        current = self.settings
        intents = {**current.intents, name: Intent(at=self._now(), by=by)}
        self._save(current.model_copy(update={"intents": intents}, deep=True))

    def _give_the_note_back(self, name: str) -> None:
        """Clear the note of a step that is known not to have begun (the gateway answered that it
        refused, or nothing was sent). A file that cannot be written leaves the note, which is the
        safe side: the next change or start settles it."""
        current = self.settings
        if name in current.intents:
            with contextlib.suppress(OSError):
                self._save(_without_note(current, name))

    @contextlib.asynccontextmanager
    async def _intending(self, name: str, by: str) -> AsyncIterator[None]:
        """Every place a credential is deleted or stored goes through here: the note is saved
        first, and stays unless the step is known not to have begun. It is cleared by the change's
        own final save, **when the change is complete** (the record and the credential agree).

        An answered refusal, or a step cut before any request was sent, changed nothing, so the
        note is given back; a refusal the gateway did not answer, a cancellation, a dropped
        connection, a garbled answer, any other exception, the removal of the old key with the new
        one refused, and a process that stops all leave it."""
        # A note that was already there (an earlier change left it, and the gateway would not let
        # its credential go) is not this step's to give back, whatever this step's own answer is.
        existed = name in self.settings.intents
        if not existed:
            self._note(name, by)
        sent = self._gateway.writes
        try:
            yield
        except (GatewayUnanswered, KeyRemovedNotReplaced):
            raise
        except ModelAdminRefused:
            if not existed:
                self._give_the_note_back(name)
            raise
        except BaseException:
            if not existed and self._gateway.writes == sent:
                self._give_the_note_back(name)
            raise

    async def _resolve(self) -> frozenset[str]:
        """Every note of intent outstanding **settled** (read from the file, under the lock): the
        credential removed (404: none was held), the engine's key recorded lost, a check made for
        a credential that is gone removed, the note cleared. **No credential is listed or read**:
        the gateway's listing returns part of each key, so the Conduit never asks. A removal the
        gateway refuses leaves the note, and the engine is withheld and unavailable until a later
        call settles it. Returns the notes still outstanding."""
        self._fresh()
        outstanding: set[str] = set()
        for name in sorted(self.settings.intents):
            try:
                await self._gateway.delete_credential(name)
            except ModelAdminRefused:
                outstanding.add(name)
                if any(p.name == name for p in self.settings.providers):
                    self._unavailable.add(name)
                    self._withheld.add(name)
                continue
            self._save(_settled(self.settings, name))
            self._withheld.discard(name)
        return frozenset(outstanding)

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
        action: ModelAdminAction | Callable[[], ModelAdminAction],
        engine: str | None,
        work: Callable[[ModelSettings], Any],
        *,
        rebuilt: frozenset[str] = frozenset(),
        key_action: Callable[[], ModelAdminAction | None] | None = None,
    ) -> Any:
        """One change, held exclusively against the file read afresh: `work` changes the gateway
        and returns what to save. **Whatever stops it**, a refusal, a file that cannot be written,
        an exception nobody named, a cancellation or anything else, takes **one** road out: when it
        had sent the gateway a write, the gateway is put back as the file *now* says (the last
        record saved, which names any key the change had removed or could not account for), shielded
        from cancellation; with none sent there is nothing to put back and no undo is sent. The
        answer and the audit then say, in the same words whichever way it stopped: that nothing was
        saved; **that the gateway was put back only if it was** (the entries and the credentials);
        that an engine's key was removed and the removal saved, with a `key_removed` audit; and that
        a key the gateway would not remove may still be held. An engine not put back is marked
        unavailable. Never a log line alone.

        `action` may be a function, read **when the change stops**, so a name `work` settles from
        the locked record is the one the failure is audited under (row 43: one change, one name
        however it ends). `key_action` names the key action a change that carried a key was
        making, when it got that far (an edit that keeps its address and carries a key: row 42):
        a failure then writes a row under it too, with the same outcome, naming the key action and
        never carrying a key."""
        async with self._exclusive:
            self._fresh()
            current = self.settings
            began = self._gateway.writes
            stopped: BaseException | None = None
            unnamed_failure = False
            try:
                # What a stopped change left is settled first (every note of intent), so this
                # change starts from a record and a gateway that agree about each credential.
                await self._resolve()
                current = self.settings
                began = self._gateway.writes
                return await work(current)
            except ModelAdminRefused as refused:
                failed = refused
            except OSError:
                failed = ModelAdminRefused(
                    "The models file could not be written; the change was not saved.", status=500
                )
            except Exception as bug:  # noqa: BLE001 - put back and said, never a bare 500
                log.error("a change to the model engines failed part-way: %s", type(bug).__name__)
                failed = ModelAdminRefused(
                    "The change failed part-way and was not saved.", status=500
                )
                unnamed_failure = True
            except BaseException as other:  # cancellation, and whatever else leaves the task
                stopped = other
                failed = ModelAdminRefused("The change was interrupted and was not saved.")
            # **No undo unless the change sent a write**: with none sent the gateway is as it was,
            # and an undo is only writes of its own that could fail half-way and break the engine.
            touched = self._gateway.writes != began
            # A note outstanding for this engine now means a credential was deleted or stored and
            # the change did not complete: the undo removes it and restores none (one function for
            # the words, `_why_it_stopped`).
            self._fresh()
            noted = engine is not None and engine in self.settings.intents
            undone = await self._undone(rebuilt) if touched else Undone(True)
            self._fresh()
            latest = self.settings  # after the undo: it settles every note of intent
            said = self._why_it_stopped(
                current, latest, engine, touched, undone, failed.words,
                say_the_gateway=stopped is not None or unnamed_failure, noted=noted,
            )  # fmt: skip
            if not undone.restored and not undone.held and engine is not None:
                self._unavailable.add(engine)
            key_removed = self._key_taken(current, latest, engine) and engine not in undone.held
            if callable(action):
                action = action()
            keyed = key_action() if key_action is not None else None
            shown = engine if engine and _NAMEABLE.fullmatch(engine) else None
            if stopped is not None:
                await self._audited(by, action, shown, outcome="interrupted: " + said)
                if keyed is not None:
                    await self._audited(by, keyed, shown, outcome="interrupted: " + said)
                if key_removed:
                    await self._key_removal_audited(by, engine, interrupted=True)
                raise stopped
            answer = ModelAdminRefused(said, status=failed.status)
            audited = await self._refusing(by, action, engine, answer)
            if keyed is not None:
                await self._refusing(by, keyed, engine, answer)
            if key_removed:
                await self._key_removal_audited(by, engine)
            raise audited from None

    def _why_it_stopped(
        self,
        current: ModelSettings,
        latest: ModelSettings,
        engine: str | None,
        touched: bool,
        undone: Undone,
        words: str,
        *,
        say_the_gateway: bool,
        noted: bool = False,
    ) -> str:
        """The one sentence for every way a change stops (decision 2 of the key paths): what failed,
        then what became of the gateway and of the key, **each said only when it is so**. "Put
        back" is said only when the undo restored the entries **and** the credential: an undo
        removes a credential it settles and never restores it (a key is never kept), so a change
        that took an engine's key, or stored one the undo then removed (`noted`: the note of intent
        was still outstanding, whatever the record said before: a key already lost, a rotation, an
        edit that keeps its address), says the entries are as the record says and the key is
        removed, never that anything was put back. Where nothing named the failure (an exception
        nobody named, an interruption) the gateway's own state is said too."""
        said = [words]
        # A key the gateway would not remove is not removed: it is said held, never removed.
        taken = self._key_taken(current, latest, engine) and engine not in undone.held
        is_engine = engine is not None and any(p.name == engine for p in latest.providers)
        # A credential this change stored or deleted, which the undo removed and did not restore:
        # a key already lost before the change is not "taken" by it, and is not put back either.
        removed = taken or (noted and is_engine and engine not in undone.held)
        if undone.held:
            names = ", ".join(sorted(undone.held))
            said.append(
                f"A key held for {names} could not be removed from the model gateway, so it may "
                f"still be held there: {names} is offered to no analyst and has no entries until "
                "it is removed (the Conduit tries again at every change and at each retry); run "
                "ospreyflow doctor."
            )
        elif not undone.restored and is_engine:
            said.append("The gateway was not put back. " + UNAVAILABLE_WORDS)
        elif not undone.restored:
            said.append(
                "A key this change had stored could not be removed from the model gateway yet: "
                "the Conduit removes it at the next change or start; run ospreyflow doctor."
            )
        elif say_the_gateway and touched and not removed:
            said.append("The model gateway was put back as the saved settings say.")
        elif say_the_gateway and touched:
            said.append("The model gateway's entries are as the saved settings say.")
        elif say_the_gateway:
            said.append("Nothing had been changed at the model gateway.")
        if taken and touched:
            said.append(
                f"{engine}'s key was removed by this change and the removal is saved: a key is "
                "never kept to restore, so enter it again."
            )
        elif removed and touched:
            said.append(
                f"The key typed with this change was removed from the model gateway and is not "
                f"kept: {engine} has no key, so enter it again."
            )
        elif taken:
            said.append(
                f"{engine}'s key was marked lost and the mark could not be taken back: enter it "
                "again."
            )
        return " ".join(said)

    @staticmethod
    def _key_taken(current: ModelSettings, latest: ModelSettings, engine: str | None) -> bool:
        """Whether this change left an engine's key set before it and removed or lost now: saved."""
        if engine is None:
            return False
        before, after = current.keys.get(engine), latest.keys.get(engine)
        return before is not None and not before.lost and (after is None or after.lost)

    async def _key_removal_audited(
        self, by: str, engine: str | None, *, interrupted: bool = False
    ) -> None:
        await self._audited(
            by, "key_removed", engine if engine and _NAMEABLE.fullmatch(engine) else None,
            outcome="done: the change " + ("was interrupted" if interrupted else "failed")
            + " after the key was removed, and the removal was saved",
        )  # fmt: skip

    async def edit_engine(
        self, by: str, name: str, provider: ModelProviderConfig, key: SecretStr | None = None
    ) -> None:
        """Save an edited engine. **A changed model name, address or key is checked first** (the
        owner's ruling 19; ADR-135 Amendment 14): each new model, or every model where the address
        or the key changed, is asked the check's one call under `probe_name`, and nothing is saved
        unless every one answers. **A changed address takes its key with it** (the owner's ruling,
        decision 1): a key entered for one address is never sent to another, so the new address is
        checked with a key typed for it, and the engine keeps its address and key until it passes.
        A label or an agreement changed alone asks nothing."""
        sent = sent_values(provider) | ({key.get_secret_value()} if key is not None else set())
        rotated: list[ModelAdminAction] = []

        async def work(current: ModelSettings) -> ModelProviderConfig:
            if provider.name != name:
                raise ModelAdminRefused("An engine's provider name cannot change; add a new one.")
            before = next((p for p in current.providers if p.name == name), None)
            if before is None:
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            if before.kind != provider.kind:
                # ADR-135 Amendment 2 decision 1: an engine's provider is fixed once added. Another
                # kind is another processor, whose contract mark and label this one's are not.
                raise ModelAdminRefused(
                    "An engine's kind cannot change; remove it and add one of the other kind."
                )
            _no_key_shown(provider, "nothing was changed")
            proposed = self._validated(current.model_copy(
                update={"providers": [provider if p.name == name else p
                                      for p in current.providers]}, deep=True), sent)  # fmt: skip
            self._made_by_the_render(provider)
            if provider.keyless and key is not None:
                raise ModelAdminRefused(
                    f"{name} signs in by the gateway's own IAM role, so no key is kept for it; "
                    "send none. Nothing was changed."
                )
            # Only the address decides where a key goes: the kind is fixed above, each kind has
            # one sign-in and Bedrock one region (ADR-135 Amendment 7 decision 4).
            moved = (before.api_base or None) != (provider.api_base or None)
            if moved and not provider.keyless and key is None:
                raise ModelAdminRefused(
                    f"{provider.label or name}'s address changed: give its key with it, so the key "
                    "is checked at the new address and never sent where it was not entered for. "
                    "Nothing was changed."
                )
            if key is not None:
                _plain_key(key)
            models = list(provider.roles.values())
            if not (moved or key is not None):
                models = [m for m in models if m not in set(before.roles.values())]
            if models:
                await self._checked(
                    provider, key, models, kept="its models, address and key", by=by
                )
            if key is not None:
                # Named from the saved record, as `set_key` names it (row 43): one name.
                rotated.append(
                    "key_rotated" if self._recorded_key_state(name) == "set" else "key_set"
                )
                # An entry names its engine's one credential and goes where its own address says,
                # and an analyst's call does not take the edit's lock. So no key is stored while an
                # entry stands at an address the record does not give (row 28: `set_key` does the
                # same), and the old address's entries go before anything is recorded or removed:
                # with the old entries live, the new key would be sent to the old address from the
                # moment it is the credential, and a withdrawal the gateway refuses must leave the
                # old key held and set (row 40), the engine briefly unavailable and never served
                # by the wrong key.
                await self._withdraw_disagreeing(current)
                if moved:
                    await self._withdraw_entries(current, name)
                # From here the key may be the engine's credential, and the code cannot always
                # tell: a read timeout after the gateway wrote it reads as "not stored". The note
                # of intent is saved first and **cleared only by the final save below**, moved or
                # not (round 8): whatever leaves this call, a refusal, a file that cannot be
                # written, a cancellation, a garbled answer or any other exception, takes one road
                # out: `_change` settles the note (the credential is removed before any entry is
                # made for the engine, the key recorded lost) and puts the entries back as the
                # file says, saying the key was removed. A process that dies here finds the same
                # note at its next start.
                fresh = await self._put_key(name, key, by)
                proposed = _with_key(proposed, name, fresh)
            await self._reconcile(proposed, rebuilt=frozenset({name}))
            self._save(proposed)
            return before

        before = await self._change(
            by, "engine_edited", name, work, rebuilt=frozenset({name}),
            key_action=lambda: rotated[0] if rotated else None,
        )  # fmt: skip
        changes = {
            f: {"from": _plain(getattr(before, f)), "to": _plain(getattr(provider, f))}
            for f in _EDITABLE
            if getattr(before, f) != getattr(provider, f)
        }
        await self._audited(by, "engine_edited", name, changes)
        if rotated:
            await self._audited(by, rotated[0], name)

    async def _withdraw_entries(self, current: ModelSettings, name: str) -> None:
        """Every entry the gateway holds for engine `name` deleted, those of the engines beside it
        left alone. An entry is `osprey-<name>-<model>` and an engine's name has no hyphen (the
        schema's rule, held by a test), so `osprey-<name>-` is that engine's own and `gemini_pro`'s
        entries are not `gemini`'s. `_change` puts them back as the file says if the edit fails."""
        for model_id in sorted(await self._gateway.stored_entries()):
            if model_id.startswith(f"osprey-{name}-"):
                await self._gateway.delete_entry(model_id)

    @staticmethod
    def _with_key_lost(current: ModelSettings, name: str, by: str) -> ModelSettings:
        record = current.keys.get(name) or KeyRecord(set_at=datetime.now(UTC), set_by=by)
        keys = {**current.keys, name: record.model_copy(update={"lost": True})}
        return current.model_copy(update={"keys": keys}, deep=True)

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
            intents = {k: v for k, v in current.intents.items() if k != name}
            proposed = current.model_copy(update={
                "providers": [p for p in current.providers if p.name != name], "keys": keys,
                "limits": limits, "intents": intents,
            }, deep=True)  # fmt: skip
            # Removing is always allowed, local only or not: it can only narrow what leaves.
            await self._reconcile(proposed)
            # The engine's own key first: if its removal is refused, the credential is still there,
            # so the entries put back answer and the file's "key set" stays true.
            await self._gateway.delete_engine_key(name)
            async with self._intending(name, by):
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
        is then lost, and it is offered to no analyst until a key is entered again. **Checked
        first** (the owner's ruling 19): a key the provider refuses replaces nothing."""
        # A rotation that fails is audited as a rotation (round 8), not as a first key, and **named
        # from the saved record** (`_recorded_key_state`), never `key_state`, which says "lost" for
        # an engine the record says is set but this process marked unavailable (row 43): one change
        # has one name however it ends. `work` settles it again from the locked record, and
        # `_change` reads it when the change stops.
        said: list[ModelAdminAction] = [
            action or ("key_rotated" if self._recorded_key_state(name) == "set" else "key_set")
        ]

        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            if refused := self._not_made(next(p for p in current.providers if p.name == name)):
                raise ModelAdminRefused(refused)  # never written into the gateway (round 2)
            if any(p.name == name and p.keyless for p in current.providers):
                # ADR-135 Amendment 4: no key is stored for an engine signed in by the role.
                raise ModelAdminRefused(
                    f"{name} signs in by the gateway's own IAM role, so no key is kept for it; "
                    "nothing was changed.",
                    status=409,
                )
            if self._installed.local_only:
                raise ModelAdminRefused(
                    "This deployment's osprey.yaml declares local_only: true, so no key for an "
                    "engine outside it is taken here."
                )
            _plain_key(key)
            record = current.keys.get(name)
            said[0] = action or (
                "key_rotated" if self._recorded_key_state(name) == "set" else "key_set"
            )
            if action != "key_moved":
                # The owner's ruling 19: a new key is proved against each of the engine's models
                # before it replaces the one held. A key moved out of `deployment.env` at install
                # is the installer's own, moved, not changed (ADR-135 Amendment 14's one exception).
                engine = next(p for p in current.providers if p.name == name)
                kept = "the key it holds" if record and not record.lost else "no key"
                await self._checked(engine, key, list(engine.roles.values()), kept=kept, by=by)
            # An entry names the engine's one credential and goes where its own address says, so no
            # key is stored while an entry stands at an address the record does not give: such
            # entries are withdrawn first, and a withdrawal the gateway refuses refuses the key.
            await self._withdraw_disagreeing(current)
            fresh = await self._put_key(name, key, by)
            proposed = _with_key(current, name, fresh)
            await self._reconcile(proposed)
            self._save(proposed)

        await self._change(by, lambda: said[0], name, work)
        await self._audited(by, said[0], name)

    async def remove_key(self, by: str, name: str) -> None:
        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            if any(p.name == name and p.keyless for p in current.providers):
                raise ModelAdminRefused(
                    f"{name} signs in by the gateway's own IAM role and keeps no key; there is "
                    "none to remove.",
                    status=409,
                )
            async with self._intending(name, by):
                await self._gateway.delete_credential(name)
            keys = {k: v for k, v in current.keys.items() if k != name}
            intents = {k: v for k, v in current.intents.items() if k != name}
            self._save(current.model_copy(update={"keys": keys, "intents": intents}, deep=True))

        await self._change(by, "key_removed", name, work)
        await self._audited(by, "key_removed", name)

    async def set_limits(self, by: str, name: str, limits: EngineLimits) -> None:
        """An engine's limits (ADR-135 Amendment 3), applied by the gateway to the engine's key at
        once, then kept in the models file and audited with each changed value."""
        before: list[EngineLimits] = []

        async def work(current: ModelSettings) -> None:
            if all(p.name != name for p in current.providers):
                raise ModelAdminRefused("There is no engine of that name.", status=404)
            if refused := self._not_made(next(p for p in current.providers if p.name == name)):
                raise ModelAdminRefused(refused)  # never written into the gateway (round 2)
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
        if name in self._unavailable and not self._installed.local_only:
            result = ConnectionTestResult(
                engine=name, outcome="not_routed", ok=False, words=UNAVAILABLE_WORDS
            )
        elif self._installed.local_only:
            result = ConnectionTestResult(
                engine=name, outcome="not_routed", ok=False,
                words="This deployment is local only: no engine outside it is asked anything.",
            )  # fmt: skip
        elif state not in ("set", "iam_role"):
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
                self._gateway.http,
                gateway_model_name(provider.name, model),
                tag=usage_tag(provider.name, "test"),
            )
            outcome = check.outcome
            if (
                provider.kind == "gateway"
                and outcome == "unreachable"
                and check.status is not None
                and 400 <= check.status < 500
            ):
                # The client's gateway answered with a 4xx the classifier does not read (not
                # OpenAI's shape): it was reached, and refused (Amendment 7 decision 5).
                outcome = "request_refused"
            words = KIND_WORDS.get((provider.kind, outcome), WORDS[outcome])
            result = ConnectionTestResult(engine=name, outcome=outcome, ok=check.ok, words=words)
        await self._audited(by, "connection_tested", name, outcome=result.outcome)
        return result

    # --- the check before Add (ADR-135 Amendment 14) --------------------------------------------

    async def _one_call(
        self, provider: ModelProviderConfig, model: str, *, named: str | None = None
    ) -> tuple[ConnectionOutcome, bool, str]:
        """Decision 5's call of at most one token to `model`, through the gateway (under `named`,
        an edit's probe, when given), and its outcome in fixed words."""
        check = await check_connection(
            self._gateway.http, gateway_model_name(named or provider.name, model),
            tag=usage_tag(provider.name, "test"),
        )  # fmt: skip
        outcome = check.outcome
        if (
            provider.kind == "gateway"
            and outcome == "unreachable"
            and check.status is not None
            and 400 <= check.status < 500
        ):
            outcome = "request_refused"  # the client's gateway was reached, and refused
        return outcome, check.ok, KIND_WORDS.get((provider.kind, outcome), WORDS[outcome])

    async def _prove(
        self, provider: ModelProviderConfig, models: Sequence[str], *, named: str, credential: str
    ) -> list[ModelCheck]:
        """Each of `models` given a passing entry under `named` that no route offers, using
        `credential`'s key, asked once, and the entry removed (decision 5's call)."""
        checked: list[ModelCheck] = []
        for model in dict.fromkeys(models):
            await self._gateway.add_entry(provider, model, named=named, credential=credential)
            try:
                outcome, ok, words = await self._one_call(provider, model, named=named)
            finally:
                await self._gateway.delete_entry(entry_id(named, model))
            roles: list[str] = [r for r, m in provider.roles.items() if m == model]
            # By job, never the typed name (the owner's ruling 22).
            jobs = ", ".join(JOB_WORDS.get(r, r) for r in roles)
            checked.append(
                ModelCheck(roles=roles, outcome=outcome, ok=ok, words=f"{jobs}: {words}")
            )
        return checked

    async def _checked(
        self,
        provider: ModelProviderConfig,
        key: SecretStr | None,
        models: Sequence[str],
        *,
        kept: str,
        by: str = "system",
    ) -> None:
        """The owner's ruling 19: an edit's or a new key's check, run under `probe_name` beside the
        live engine, which it never touches. A new key is the probe's own credential, removed
        whatever the answer; without one the engine's own key is used. Refused, in the check's
        words, unless every model answers: the engine then keeps `kept`."""
        if self._installed.local_only:
            raise ModelAdminRefused(
                "This deployment is local only: no engine outside it is asked anything, so the "
                "change cannot be checked. Nothing was changed."
            )
        if key is None and not provider.keyless and self.key_state(provider.name) != "set":
            # A check without a key uses the engine's own credential, and an engine whose key is
            # lost may have a credential that holds a key typed for another address (a removal the
            # gateway refused): it is never sent anywhere. Enter the key again with the change.
            raise ModelAdminRefused(
                f"{provider.label or provider.name} has no key to check with; enter its key "
                f"with the change. Nothing was changed: it keeps {kept}."
            )
        probe = probe_name(provider.name)
        own = key is not None and not provider.keyless
        # The check's own credential and entries are never the live engine's: their writes are not
        # the change's, so a check that fails has nothing to put back (`GatewayAdmin.probing`).
        with self._gateway.probing():
            # The probe's credential holds a typed key, and a note of intent is saved before it is
            # stored (start settles one a stopped process left). With no models file there is
            # nowhere to write one without taking `osprey.yaml`'s place, so start removes every
            # probe credential whether or not there is a file (row 21).
            if own and self._settings is not None:
                self._note(probe, by)
            try:
                if own:
                    assert key is not None
                    try:
                        await self._gateway.put_credential(probe, key)
                    except KeyRemovedNotReplaced:  # the probe held no key before: none is lost
                        raise ModelAdminRefused(
                            "The model gateway refused the key; nothing was changed. Run "
                            "ospreyflow doctor.",
                            status=502,
                        ) from None
                checked = await self._prove(
                    provider,
                    models,
                    named=probe_entries(provider.name),
                    credential=probe if own else provider.name,
                )
            finally:
                # Whatever the answer, and whatever stopped the store: a call lost after the
                # gateway wrote it leaves the key held, so the removal is always asked.
                if own:
                    await self._gateway.delete_credential(probe)
                    if probe in self.settings.intents:
                        with contextlib.suppress(OSError):  # the note stays: settled at start
                            self._save(_without_note(self.settings, probe))
        failed = [m for m in checked if not m.ok]
        if failed:
            said = " ".join(m.words for m in failed)
            raise ModelAdminRefused(
                f"{said} Nothing was changed: {provider.label or provider.name} keeps {kept}."
            )

    async def _put_key(self, name: str, key: SecretStr, by: str) -> KeyRecord:
        """A checked key as the engine's own credential, returning the record that will say so.

        **The note of intent is saved first** (`_intending`), so a record save that fails stops the
        change with nothing done, and a process that dies, a task that is cancelled or an answer
        that is lost after the gateway wrote never leaves "set" over a credential the code cannot
        account for. **It is cleared only by the change's own final save** (the caller puts the
        returned record in the settings it saves last), for a rotation and an edit that keeps its
        address as for a moved one: whatever then leaves the change, a refused update of the
        engine's limits, a garbled list of keys, a cancellation, the note stays and `_resolve`
        removes the credential before any entry is made for the engine, and the answer and the
        audit say the key was removed (`_why_it_stopped`). A removal the gateway *answered* with a
        refusal changed nothing, so the note is given back. A replacement the gateway refuses after
        the old key was removed leaves the note too, and the engine's key is then recorded lost."""
        async with self._intending(name, by):
            await self._gateway.put_credential(name, key)
        return KeyRecord(set_at=self._now(), set_by=by)

    async def _expired(self, current: ModelSettings) -> tuple[ModelSettings, list[str]]:
        """`current` without the checks older than `CHECK_LIFE`, their credentials removed.

        **A lapsed check's credential joins the one mechanism** (round 8, N1): the note of intent
        is saved before it is deleted and cleared with the record that drops the check (the
        settings returned here, which the caller saves). A removal that landed and whose record was
        never saved leaves the note, which the next change or start settles by removing the check
        with its credential; one the gateway answered with a refusal changed nothing, so the note is
        given back and the check stays until a later sweep."""
        now = self._now()
        late = {i: c for i, c in current.checks.items() if now - c.at > CHECK_LIFE}
        for pending in late.values():
            if not pending.provider.keyless:
                async with self._intending(pending.provider.name, "system"):
                    await self._gateway.delete_credential(pending.provider.name)
        kept = {i: c for i, c in current.checks.items() if i not in late}
        names = {c.provider.name for c in late.values()}
        intents = {k: v for k, v in current.intents.items() if k not in names}
        return current.model_copy(update={"checks": kept, "intents": intents}, deep=True), [
            c.provider.name for c in late.values()
        ]

    async def _audit_expired(self, engines: list[str]) -> None:
        for engine in engines:
            await self._audited("system", "engine_check_expired", engine)

    async def check(
        self, by: str, provider: ModelProviderConfig, key: SecretStr | None
    ) -> EngineCheckResult:
        """The key and each typed model proved by one call in the gateway, before the engine
        exists (ADR-135 Amendment 14 point 2; the owner's ruling 7). The key goes straight to the
        gateway as the engine's own credential and the Conduit keeps nothing; each model is given
        a passing entry that no route offers, asked once, and the entry removed. A refusal keeps
        nothing; a pass is held for **Add** for `CHECK_LIFE`."""
        sent = sent_values(provider) | ({key.get_secret_value()} if key is not None else set())
        expired: list[str] = []

        async def work(current: ModelSettings) -> EngineCheckResult:
            current, gone = await self._expired(current)
            expired.extend(gone)
            if gone:
                self._save(current)
            held = [c.provider.name for c in current.checks.values()]
            if any(p.name == provider.name for p in current.providers) or provider.name in held:
                raise ModelAdminRefused(
                    f"An engine named {provider.name} is already added or being checked; change "
                    "its key on the engine itself."
                )
            _no_key_shown(provider, "nothing was checked")
            self._validated(current.model_copy(
                update={"providers": [*current.providers, provider]}, deep=True), sent)  # fmt: skip
            self._made_by_the_render(provider)
            if provider.keyless and key is not None:
                raise ModelAdminRefused(
                    f"{provider.name} signs in by the gateway's own IAM role, so no key is kept "
                    "for it; send none."
                )
            if not provider.keyless:
                text = key.get_secret_value() if key is not None else ""
                if not text.strip() or any(ch.isspace() for ch in text):
                    raise ModelAdminRefused(
                        "Give the key, with no spaces or line breaks in it; nothing was checked."
                    )
            # The key is stored under the name's own credential, which an entry for that name (an
            # engine the record does not hold, left by an interrupted removal) would send to its
            # own address: such entries are withdrawn first, and a withdrawal the gateway refuses
            # refuses the check (row 28).
            await self._withdraw_disagreeing(current)
            # The owner's ruling 25: the check is on record before its key reaches the gateway, so a
            # Conduit stopped at any point after leaves a record the sweep removes, with its key.
            # The note of intent is in the same save (a credential is about to be stored), and the
            # next start or change settles it, removing the check with the key.
            check_id = secrets.token_urlsafe(12)
            record = PendingCheck(provider=provider, by=by, at=self._now(), passed=False)
            unchecked = current
            noted = {**current.intents, provider.name: Intent(at=self._now(), by=by)}
            current = current.model_copy(
                update={
                    "checks": {**current.checks, check_id: record},
                    "intents": noted if not provider.keyless else current.intents,
                },
                deep=True,
            )
            self._save(current)
            try:
                if not provider.keyless:
                    assert key is not None
                    await self._gateway.put_credential(provider.name, key)
                models = await self._prove(
                    provider, list(provider.roles.values()),
                    named=probe_entries(provider.name), credential=provider.name,
                )  # fmt: skip
                if not models or not all(m.ok for m in models):
                    if not provider.keyless:
                        await self._gateway.delete_credential(provider.name)
                    self._save(unchecked)
                    first = next((m for m in models if not m.ok), None)
                    return EngineCheckResult(
                        engine=provider.name, ok=False, check=None, models=models,
                        words=(first.words if first else "Name a model for at least one job.")
                        + " Nothing was kept: correct it and check again.",
                    )  # fmt: skip
                passed = record.model_copy(update={"passed": True})
                checks = {**current.checks, check_id: passed}
                self._save(
                    _without_note(current, provider.name).model_copy(
                        update={"checks": checks}, deep=True
                    )
                )
            except BaseException:
                # Its key goes with the refusal; the record too, where it can still be written
                # (else the sweep removes it, and nothing else of it is left).
                if not provider.keyless:
                    await self._gateway.delete_credential(provider.name)
                with contextlib.suppress(OSError):
                    self._save(unchecked)
                raise
            return EngineCheckResult(
                engine=provider.name, ok=True, check=check_id, models=models,
                words="The key and every model answered. Add the engine within 15 minutes to "
                "offer it to analysts.",
            )  # fmt: skip

        result: EngineCheckResult = await self._change(by, "engine_checked", provider.name, work)
        await self._audit_expired(expired)
        # Each job and its outcome, never the typed name (the owner's ruling 22).
        outcomes = ", ".join(f"{r}: {m.outcome}" for m in result.models for r in m.roles)
        await self._audited(
            by, "engine_checked", provider.name,
            outcome=("passed" if result.ok else "refused") + (f" ({outcomes})" if outcomes else ""),
        )  # fmt: skip
        return result

    async def add_checked(self, by: str, check_id: str) -> None:
        """**Add**: the engine made from a passed check, whose key the gateway already holds; the
        key is never sent again. Refused for a check that does not exist or is past `CHECK_LIFE`."""
        expired: list[str] = []
        added: list[ModelProviderConfig] = []
        checked_by: list[str] = []

        async def work(current: ModelSettings) -> None:
            pending = current.checks.get(check_id)
            if pending is not None and not pending.passed:
                pending = None  # still running, or stopped mid-way (ruling 25): nothing to add
            current, gone = await self._expired(current)
            expired.extend(gone)
            if pending is not None and check_id not in current.checks:
                self._save(current)
                raise ModelAdminRefused(
                    "This check is more than 15 minutes old, so its key was removed. Check the "
                    "key again, then add the engine.",
                    status=410,
                )
            if pending is None:
                if gone:
                    self._save(current)  # the lapsed ones swept here are not audited again
                raise ModelAdminRefused(
                    "There is no check of that name. Check the key first, then add the engine.",
                    status=404,
                )
            provider = pending.provider
            rest = {i: c for i, c in current.checks.items() if i != check_id}
            proposed = self._validated(current.model_copy(
                update={"providers": [*current.providers, provider], "checks": rest}, deep=True),
                sent_values(provider))  # fmt: skip
            self._made_by_the_render(provider)
            await self._reconcile(proposed)
            keys = dict(proposed.keys)
            if not provider.keyless:
                # The owner's key rule 3: who typed the key, and when, at the check.
                keys[provider.name] = KeyRecord(set_at=pending.at, set_by=pending.by)
            self._save(proposed.model_copy(update={"keys": keys}, deep=True))
            added.append(provider)
            checked_by.append(pending.by)

        try:
            await self._change(by, "engine_added", None, work)
        finally:
            await self._audit_expired(expired)
        provider = added[0]
        named = [f for f in _EDITABLE if not (provider.plain and f in _KIND_FIELDS)]
        await self._audited(
            by, "engine_added", provider.name,
            {f: {"from": None, "to": _plain(getattr(provider, f))} for f in named},
        )  # fmt: skip
        if not provider.keyless:
            await self._audited(checked_by[0], "key_set", provider.name)

    async def cancel_check(self, by: str, check_id: str) -> None:
        """**Cancel**: a passed check removed, and its key with it."""
        cancelled: list[str] = []

        async def work(current: ModelSettings) -> None:
            pending = current.checks.get(check_id)
            if pending is None:
                raise ModelAdminRefused("There is no check of that name.", status=404)
            if not pending.provider.keyless:
                # The note of intent first (row 41): a save that fails, or a process that stops,
                # after the credential is gone must never leave a passed check with no key behind
                # it, which **Add** would then record as a key set. Settling the note removes the
                # check with the credential.
                async with self._intending(pending.provider.name, by):
                    await self._gateway.delete_credential(pending.provider.name)
            rest = {i: c for i, c in current.checks.items() if i != check_id}
            intents = {k: v for k, v in current.intents.items() if k != pending.provider.name}
            self._save(current.model_copy(update={"checks": rest, "intents": intents}, deep=True))
            cancelled.append(pending.provider.name)

        await self._change(by, "engine_check_cancelled", None, work)
        await self._audited(by, "engine_check_cancelled", cancelled[0])


def _no_key_shown(provider: ModelProviderConfig, then: str) -> None:
    """The form's own rule, on every profile, for an engine checked or edited: what analysts are
    shown never holds a key, so a key pasted into a model name, the label or the agreement's
    reference is refused before anything is kept."""
    for role, model in provider.roles.items():
        if refused := model_name_refusal(role, model):
            raise ModelAdminRefused(f"{refused}; {then}.")
    for field_name, shown in (("label", provider.label),
                              ("agreement reference", provider.contract_reference)):  # fmt: skip
        if shown and label_looks_like_a_key(shown):
            raise ModelAdminRefused(
                f"The {field_name} looks like a key. It is shown to analysts, so give it in words, "
                f"and the key in the key field; {then}."
            )


def _plain_key(key: SecretStr) -> None:
    text = key.get_secret_value()
    if not text.strip() or any(ch.isspace() for ch in text):
        raise ModelAdminRefused("A key has no spaces or line breaks in it; nothing was changed.")


def _said(failed: BaseException) -> str:
    return failed.words if isinstance(failed, ModelAdminRefused) else type(failed).__name__


def _owner(model_id: str) -> str:
    """The engine an entry belongs to: `entry_id` is `osprey-<engine>-<model>`, and an engine's name
    has no hyphen (`schemas.deployment`'s name rule), so the first segment is exact."""
    return model_id.removeprefix("osprey-").partition("-")[0]


#: What a person is told while an engine's gateway entries may not agree with the saved settings.
UNAVAILABLE_WORDS = (
    "The gateway could not be put back as the saved settings say, so the engine is unavailable "
    "until it is repaired. Run ospreyflow doctor; once the gateway answers, restart the Conduit, "
    "or enter the engine's key again where it has one: either makes the gateway agree with the "
    "saved settings."
)


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
