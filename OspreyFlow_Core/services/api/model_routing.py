"""Which model each request reaches (`06_DECISIONS.md` ADR-135 decision 4, amending ADR-114
decision 11 and Amendment 6 point 4; `04_VAULT_BACKEND.md` §4: "egress is default-denied").

A deployment has its own (local) engine and may enable client providers (engines), each with its
models per role and its own key, which only the gateway reads. The administrator names each role's
default engine; an analyst may name another per request. **The route decides, in this order:**

1. a named engine the administrator did not enable, or one with no key (or no model for the role),
   is refused in words (`EngineRefused`) — nothing is sent;
2. material whose handling code is not sendable (`models.sendable_handling_codes`) runs on the
   local engine whatever was named, and is refused in words where there is no local model for the
   role (`ModelEgressRefused`). Material whose handling is not given is treated as not sendable, so
   a caller that forgets it can never cause egress; and naming a provider's model in a request is
   no way round the codes;
3. otherwise it runs on the named engine, else the role's default (a default whose key is not
   present runs locally), else locally.

Every result says which engine and model produced it (`ExtractionResult.engine`, `.model`).

This wraps the model adapter, so every call the Conduit makes goes through it. The Conduit is told
the engines by `harness/render.py` (`OSPREY_MODEL_ENGINES`, `OSPREY_MODEL_DEFAULTS`,
`OSPREY_SENDABLE_HANDLING_CODES`) and whether each key is present by Compose
(`OSPREY_MODEL_KEY_PRESENT_<NAME>`, "yes" or empty) — never a key.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from ports.model import ModelPort
from schemas.admin import EngineStatus, ModelRoleStatus
from schemas.domain import Handling, Vector
from schemas.model import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    OfferedEngine,
    TranscribeRequest,
    Transcript,
    VisionRequest,
)

from .config import DeploymentModels

Role = Literal["extraction", "vision", "transcription", "embedding"]
ROLES: tuple[Role, ...] = ("extraction", "vision", "transcription", "embedding")

#: The deployment's own engine (ADR-135 decision 1).
LOCAL = "local"
LOCAL_LABEL = "This deployment's own model"


class ModelEgressRefused(Exception):
    """Material the deployment may not send, for a role with no local model to run it on."""


class EngineRefused(Exception):
    """A request named an engine it may not use: not enabled, with no key, or with no model for the
    role. The words say which, and nothing was sent."""


@dataclass(frozen=True)
class Engine:
    """An enabled client provider as the Conduit knows it: never its key, only whether it has
    one."""

    name: str
    label: str
    #: Each role it has a model for, as the gateway names it (`provider/model`).
    models: Mapping[Role, str]
    key_present: bool


@dataclass(frozen=True)
class ModelRoutes:
    #: The deployment's own model for each role; `None` where it has none.
    locals: Mapping[Role, str | None]
    engines: Mapping[str, Engine] = field(default_factory=dict)
    #: Each role's default engine as `osprey.yaml` names it; a role not here is `local`.
    defaults: Mapping[Role, str] = field(default_factory=dict)
    sendable: frozenset[str] = frozenset()

    def default_for(self, role: Role) -> str:
        """The engine a request for `role` that names none runs on: the named default, unless it
        has no key or no model for the role, then `local`."""
        named = self.defaults.get(role, LOCAL)
        engine = self.engines.get(named)
        if engine is None or not engine.key_present or role not in engine.models:
            return LOCAL
        return named

    def offered(self) -> list[OfferedEngine]:
        """What an analyst may choose (ADR-135 decision 5): the local engine, where the deployment
        has a local model, and each enabled engine that has a key."""
        out: list[OfferedEngine] = []
        local_roles = [r for r in ROLES if self.locals.get(r)]
        if local_roles:
            out.append(
                OfferedEngine(
                    name=LOCAL,
                    label=LOCAL_LABEL,
                    roles=local_roles,
                    default_for=[r for r in ROLES if self.default_for(r) == LOCAL],
                )
            )
        for engine in self.engines.values():
            if engine.key_present:
                out.append(
                    OfferedEngine(
                        name=engine.name,
                        label=engine.label,
                        roles=[r for r in ROLES if r in engine.models],
                        default_for=[r for r in ROLES if self.default_for(r) == engine.name],
                    )
                )
        return out


@dataclass(frozen=True)
class Choice:
    engine: str
    model: str


class RoutedModel:
    def __init__(self, inner: ModelPort, *, routes: ModelRoutes) -> None:
        self._inner = inner
        self._routes = routes

    @property
    def routes(self) -> ModelRoutes:
        return self._routes

    def choose(
        self, role: Role, asked: str, handling: Handling | None, engine: str | None = None
    ) -> Choice:
        """The engine and model a request for `role` reaches. `asked` is used only where the
        deployment's local model for the role is not known."""
        routes = self._routes
        if engine is not None and engine != LOCAL:
            named = routes.engines.get(engine)
            if named is None:
                choices = ", ".join([LOCAL, *(e.name for e in routes.engines.values())])
                raise EngineRefused(
                    f"{engine} is not an engine this deployment enabled; the engines are: "
                    f"{choices}."
                )
            if not named.key_present:
                raise EngineRefused(
                    f"{named.label} has no key on this deployment, so it is not offered. An "
                    "administrator sets one with ospreyflow models key."
                )
            if role not in named.models:
                raise EngineRefused(f"{named.label} has no {role} model on this deployment.")
        target = engine if engine is not None else routes.default_for(role)
        local = routes.locals[role] if role in routes.locals else asked
        sendable = handling is not None and handling.handling_code in routes.sendable
        if target != LOCAL and sendable:
            return Choice(target, routes.engines[target].models[role])
        if local:
            return Choice(LOCAL, local)
        if target == LOCAL:
            raise EngineRefused(f"This deployment has no local {role} model.")
        code = handling.handling_code if handling is not None else "not given"
        what = (
            f"material with handling code {code}"
            if handling is not None
            else "material whose handling is not given"
        )
        raise ModelEgressRefused(
            f"The {role} model is the client's own provider, and {what} may not be sent to it; "
            f"this deployment has no local {role} model to use instead."
        )

    def model_for(self, role: Role, asked: str, handling: Handling | None) -> str:
        return self.choose(role, asked, handling).model

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        choice = self.choose("extraction", req.model, req.handling, req.engine)
        result = await self._inner.extract(req.model_copy(update={"model": choice.model}))
        return result.model_copy(update={"engine": choice.engine})

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        model = self.model_for("transcription", req.model, req.handling)
        return await self._inner.transcribe(req.model_copy(update={"model": model}))

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        model = self.model_for("vision", req.model, req.handling)
        return await self._inner.describe_image(req.model_copy(update={"model": model}))

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        """Embeddings carry no handling here, so they never leave: always the local model (the
        adapter's own), whatever the provider names."""
        return await self._inner.embed(texts)


def _json(environ: Mapping[str, str], name: str, empty: object) -> object:
    text = environ.get(name, "").strip()
    return json.loads(text) if text else empty


def routes_from_env(local: DeploymentModels, environ: Mapping[str, str]) -> ModelRoutes:
    """Each role's local model, the enabled engines with whether each key is present, each role's
    default, and the sendable codes — as `harness/render.py` and Compose wrote them."""
    locals_: dict[Role, str | None] = {
        "extraction": local.extraction,
        "vision": local.vision,
        "transcription": local.transcription,
        "embedding": local.embedding,
    }
    engines: dict[str, Engine] = {}
    for raw in cast(list[dict[str, object]], _json(environ, "OSPREY_MODEL_ENGINES", [])):
        name = str(raw["name"])
        models = cast(dict[str, str], raw.get("roles") or {})
        engines[name] = Engine(
            name=name,
            label=str(raw.get("label") or name),
            models={r: m for r, m in models.items() if r in ROLES},
            key_present=environ.get(f"OSPREY_MODEL_KEY_PRESENT_{name.upper()}", "") == "yes",
        )
    named = cast(dict[str, str], _json(environ, "OSPREY_MODEL_DEFAULTS", {}))
    defaults: dict[Role, str] = {r: e for r, e in named.items() if r in ROLES}
    codes = frozenset(
        c.strip() for c in environ.get("OSPREY_SENDABLE_HANDLING_CODES", "").split(",") if c.strip()
    )
    return ModelRoutes(locals=locals_, engines=engines, defaults=defaults, sendable=codes)


def model_status(
    routes: ModelRoutes,
) -> tuple[list[ModelRoleStatus], list[EngineStatus], str | None]:
    """Each role's model and where it runs, each engine with its defaults and whether its key is
    present, and the notice the Admin area shows when case content leaves the deployment (ADR-114
    decision 11, ADR-135 decision 5). Built from names only — no key reaches it."""
    statuses: list[ModelRoleStatus] = []
    for role, local in routes.locals.items():
        engine = routes.default_for(role)
        if engine != LOCAL:
            model = routes.engines[engine].models[role]
            statuses.append(
                ModelRoleStatus(role=role, model=model, runs_at=engine, local_model=local)
            )
        else:
            statuses.append(
                ModelRoleStatus(
                    role=role, model=local or "none", runs_at="this deployment", local_model=local
                )
            )
    engines = [
        EngineStatus(
            name=LOCAL,
            label=LOCAL_LABEL,
            models={r: m for r, m in routes.locals.items() if m},
            default_for=[r for r in ROLES if routes.defaults.get(r, LOCAL) == LOCAL],
            key_present=True,
        ),
        *(
            EngineStatus(
                name=e.name,
                label=e.label,
                models={str(r): m for r, m in e.models.items()},
                default_for=[r for r in ROLES if routes.defaults.get(r) == e.name],
                key_present=e.key_present,
            )
            for e in routes.engines.values()
        ),
    ]
    # What may leave: each engine with a key, for the roles it has a model for (embeddings never
    # leave) — "is sent" where it is the role's default, "may be sent" where an analyst may name it.
    sent: dict[str, list[str]] = {}
    may: dict[str, list[str]] = {}
    for e in routes.engines.values():
        if not e.key_present:
            continue
        for role in ROLES:
            if role == "embedding" or role not in e.models:
                continue
            target = sent if routes.default_for(role) == e.name else may
            target.setdefault(e.name, []).append(role)
    if not sent and not may:
        return statuses, engines, None
    codes = ", ".join(sorted(routes.sendable)) or "none"
    plural = "s" if len(routes.sendable) > 1 else ""

    def where(found: dict[str, list[str]]) -> str:
        return "; ".join(f"to {p} for {' and '.join(rs)}" for p, rs in found.items())

    parts = []
    if sent:
        parts.append(f"is sent {where(sent)}")
    if may:
        parts.append(f"may be sent {where(may)} when an analyst chooses it")
    notice = (
        f"Case content with handling code{plural} {codes} {', and '.join(parts)}. Anything else "
        "runs on this deployment's own models."
    )
    return statuses, engines, notice
