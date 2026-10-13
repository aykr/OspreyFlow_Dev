"""Which model each request reaches (`06_DECISIONS.md` ADR-114 decision 11, Amendment 6 point 4;
`04_VAULT_BACKEND.md` §4: "egress is default-denied").

A deployment may name a client's own provider for some roles. For those roles the provider
**replaces** the local model — but only for material whose handling code the deployment declared
sendable (`models.sendable_handling_codes`). Anything else runs on the role's local model, or, where
the deployment has none, is refused in words. Material whose handling is not given is treated as not
sendable, so a caller that forgets it can never cause egress; and naming the provider's model in a
request is no way round the codes, since the route, not the caller, decides.

This wraps the model adapter, so every call the Conduit makes goes through it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from ports.model import ModelPort
from schemas.domain import Handling, Vector
from schemas.model import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    VisionRequest,
)

from .config import DeploymentModels

Role = Literal["extraction", "vision", "transcription", "embedding"]


class ModelEgressRefused(Exception):
    """Material the deployment may not send, for a role with no local model to run it on."""


@dataclass(frozen=True)
class RoleRoute:
    #: The deployment's own model for the role; `None` where it has none.
    local: str | None
    #: The client's provider's model for the role (`provider/model`), or `None` if it names none.
    provider: str | None


class RoutedModel:
    def __init__(
        self,
        inner: ModelPort,
        *,
        routes: dict[Role, RoleRoute],
        sendable_handling_codes: frozenset[str],
    ) -> None:
        self._inner = inner
        self._routes = routes
        self._sendable = sendable_handling_codes

    def model_for(self, role: Role, asked: str, handling: Handling | None) -> str:
        """The model a request for `role` reaches. `asked` is used only where no route is known."""
        route = self._routes.get(role)
        if route is None:
            return asked
        sendable = handling is not None and handling.handling_code in self._sendable
        if route.provider is not None and sendable:
            return route.provider
        if route.local is not None:
            return route.local
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

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        model = self.model_for("extraction", req.model, req.handling)
        return await self._inner.extract(req.model_copy(update={"model": model}))

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


def routes_from_env(
    local: DeploymentModels, environ: Mapping[str, str]
) -> tuple[dict[Role, RoleRoute], frozenset[str]]:
    """Each role's local model and, where the deployment names one, the client's provider's
    (`OSPREY_PROVIDER_<ROLE>_MODEL`, written by `harness/render.py`), and the sendable codes."""
    locals_: dict[Role, str] = {
        "extraction": local.extraction,
        "vision": local.vision,
        "transcription": local.transcription,
        "embedding": local.embedding,
    }
    routes: dict[Role, RoleRoute] = {
        role: RoleRoute(local=model, provider=environ.get(f"OSPREY_PROVIDER_{role.upper()}_MODEL"))
        for role, model in locals_.items()
    }
    codes = frozenset(
        c.strip() for c in environ.get("OSPREY_SENDABLE_HANDLING_CODES", "").split(",") if c.strip()
    )
    return routes, codes
