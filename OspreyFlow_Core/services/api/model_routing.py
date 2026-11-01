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
3. (ADR-136 decision 3) material any of whose datasets does not allow the engine runs on the local
   engine the same way, and is refused in words the same way. A dataset's egress is `none` (never
   to a hosted engine, the default), `contracted` (only to a provider marked `privacy_contract`) or
   `any`. Datasets not given, not found, or a router given no way to read egress, are `none`, so
   nothing leaves by omission;
4. otherwise it runs on the named engine, else the role's default (a default whose key is not
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
from typing import Literal, Protocol, cast

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
from .datasets import Dataset

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
    #: ADR-136 decision 1: the organisation holds a data-processing agreement covering this key.
    privacy_contract: bool = False
    contract_reference: str | None = None


class DatasetEgressReader(Protocol):
    """Where the routing reads each dataset's egress (`datasets.DatasetStore` is one). A dataset
    missing from the answer is `none`."""

    async def egress_of(self, dataset_ids: Sequence[str]) -> Mapping[str, Dataset]: ...


def dataset_refusal(
    engine: Engine, datasets: Sequence[str] | None, held: Mapping[str, Dataset]
) -> str | None:
    """Why `engine` may not be sent material from `datasets` (ADR-136 decision 3), in words; `None`
    when every dataset allows it. Not known is `none`: no datasets, or one `held` does not have."""
    if not datasets:
        return (
            f"the datasets this material comes from are not known, so it is not sent to "
            f"{engine.label}"
        )
    none: list[str] = []
    contracted: list[str] = []
    for dataset_id in dict.fromkeys(datasets):
        dataset = held.get(dataset_id)
        egress = dataset.egress if dataset is not None else "none"
        name = f"“{dataset.name}”" if dataset is not None else "a dataset not known here"
        if egress == "any" or (egress == "contracted" and engine.privacy_contract):
            continue
        (contracted if egress == "contracted" else none).append(name)
    if none:
        return (
            f"{_names(none)} {'is' if len(none) == 1 else 'are'} set to egress none, never sent "
            f"to a hosted engine such as {engine.label}"
        )
    if contracted:
        return (
            f"{_names(contracted)} may go only to a provider under a privacy contract, and "
            f"{engine.label} has none on this deployment"
        )
    return None


def _names(names: Sequence[str]) -> str:
    listed = list(names)
    return listed[0] if len(listed) == 1 else f"{', '.join(listed[:-1])} and {listed[-1]}"


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

    def offered(
        self,
        case_datasets: Sequence[str] | None = None,
        held: Mapping[str, Dataset] | None = None,
    ) -> list[OfferedEngine]:
        """What an analyst may choose (ADR-135 decision 5): the local engine, where the deployment
        has a local model, and each enabled engine that has a key, with its contract mark. Given a
        case's datasets (ADR-136 decision 3), an engine the case's data may not reach is listed
        unavailable, with the reason in words; the local engine is always available."""
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
                reason = (
                    self.case_refusal(engine, case_datasets, held or {})
                    if case_datasets is not None
                    else None
                )
                out.append(
                    OfferedEngine(
                        name=engine.name,
                        label=engine.label,
                        roles=[r for r in ROLES if r in engine.models],
                        default_for=[r for r in ROLES if self.default_for(r) == engine.name],
                        privacy_contract=engine.privacy_contract,
                        available=reason is None,
                        reason=reason,
                    )
                )
        return out

    def case_refusal(
        self, engine: Engine, case_datasets: Sequence[str], held: Mapping[str, Dataset]
    ) -> str | None:
        """Why nothing of a case reading `case_datasets` may reach `engine`, as a sentence; `None`
        when its data may (each request is still decided by its own handling code)."""
        if not self.sendable:
            return (
                "Not available: no handling code on this deployment may be sent to a hosted "
                "engine, so everything runs on this deployment's own model."
            )
        why = dataset_refusal(engine, case_datasets, held)
        if why is None:
            return None
        return f"Not available for this case: {why}."


@dataclass(frozen=True)
class Choice:
    engine: str
    model: str


class RoutedModel:
    def __init__(
        self,
        inner: ModelPort,
        *,
        routes: ModelRoutes,
        egress: DatasetEgressReader | None = None,
    ) -> None:
        self._inner = inner
        self._routes = routes
        #: ADR-136: where each dataset's egress is read. With none, every dataset is `none`.
        self._egress = egress

    @property
    def routes(self) -> ModelRoutes:
        return self._routes

    async def held(self, datasets: Sequence[str] | None) -> Mapping[str, Dataset]:
        """Each of `datasets` this router can read the egress of; the rest are `none`."""
        if not datasets or self._egress is None:
            return {}
        return await self._egress.egress_of(list(dict.fromkeys(datasets)))

    def choose(
        self,
        role: Role,
        asked: str,
        handling: Handling | None,
        engine: str | None = None,
        datasets: Sequence[str] | None = None,
        held: Mapping[str, Dataset] | None = None,
    ) -> Choice:
        """The engine and model a request for `role` reaches. `asked` is used only where the
        deployment's local model for the role is not known. `datasets` are those the material comes
        from, and `held` their egress as `held()` read it (ADR-136)."""
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
        refused_by_dataset: str | None = None
        if target != LOCAL and sendable:
            hosted = routes.engines[target]
            refused_by_dataset = dataset_refusal(hosted, datasets, held or {})
            if refused_by_dataset is None:
                return Choice(target, hosted.models[role])
        if local:
            return Choice(LOCAL, local)
        if target == LOCAL:
            raise EngineRefused(f"This deployment has no local {role} model.")
        if refused_by_dataset is not None:
            raise ModelEgressRefused(
                f"The {role} model is {routes.engines[target].label}, and {refused_by_dataset}; "
                f"this deployment has no local {role} model to use instead."
            )
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

    async def decide(
        self,
        role: Role,
        asked: str,
        handling: Handling | None,
        engine: str | None = None,
        datasets: Sequence[str] | None = None,
    ) -> Choice:
        """`choose`, with the datasets' egress read first."""
        return self.choose(role, asked, handling, engine, datasets, await self.held(datasets))

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        choice = await self.decide("extraction", req.model, req.handling, req.engine, req.datasets)
        result = await self._inner.extract(req.model_copy(update={"model": choice.model}))
        return result.model_copy(update={"engine": choice.engine})

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        choice = await self.decide("transcription", req.model, req.handling, None, req.datasets)
        return await self._inner.transcribe(req.model_copy(update={"model": choice.model}))

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        choice = await self.decide("vision", req.model, req.handling, None, req.datasets)
        return await self._inner.describe_image(req.model_copy(update={"model": choice.model}))

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
        reference = raw.get("contract_reference")
        engines[name] = Engine(
            name=name,
            label=str(raw.get("label") or name),
            models={r: m for r, m in models.items() if r in ROLES},
            key_present=environ.get(f"OSPREY_MODEL_KEY_PRESENT_{name.upper()}", "") == "yes",
            # ADR-136: only a literal `true` marks a contract; anything else is none.
            privacy_contract=raw.get("privacy_contract") is True,
            contract_reference=str(reference) if reference else None,
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
                privacy_contract=e.privacy_contract,
                contract_reference=e.contract_reference,
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
        f"Case content with handling code{plural} {codes} {', and '.join(parts)}, but only from "
        "a dataset whose egress allows it (Admin, Datasets; every dataset is none until an "
        "administrator changes it). Anything else runs on this deployment's own models."
    )
    return statuses, engines, notice
