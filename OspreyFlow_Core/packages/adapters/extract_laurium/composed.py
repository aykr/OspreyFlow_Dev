"""Laurium as the deployment's extraction engine (`spec/06_DECISIONS.md` ADR-135 Amendments 5 and
6, P12 part 2): `ModelPort.extract` alone goes to Laurium's service; `embed`, `transcribe` and
`describe_image` stay with the adapter the Conduit already has (the LiteLLM adapter). Composed
**inside** the Conduit's routing (`services.api.model_routing.RoutedModel`), so every call still
carries its engine and job and goes with that engine's own key (Amendment 3), and the dataset egress
and handling rules hold for Laurium's calls exactly as for Deep read's.

The choice is the deployment's, rendered from `models.extraction_engine` as
`OSPREY_EXTRACTION_ENGINE`, with Laurium's address as `OSPREY_LAURIUM_URL`
(`harness.laurium.laurium_env`). A choice this cannot honour is refused at start in words, never
read as Deep read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from ports.model import ModelPort
from schemas.domain import Vector
from schemas.model import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    VisionRequest,
)

ENGINE = "OSPREY_EXTRACTION_ENGINE"
URL = "OSPREY_LAURIUM_URL"
DEEP_READ, LAURIUM = "deep_read", "laurium"


class LauriumNotConfigured(Exception):
    """The deployment chose an extraction engine the Conduit cannot run as named; in fixed words."""


class LauriumExtracts:
    """A `ModelPort`: `extract` by Laurium, every other operation by `inner`."""

    def __init__(self, inner: ModelPort, laurium: ExtractLauriumAdapter) -> None:
        self.inner = inner
        self.laurium = laurium

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        return await self.laurium.extract(req)

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        return await self.inner.transcribe(req)

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        return await self.inner.describe_image(req)

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        return await self.inner.embed(texts)

    async def aclose(self) -> None:
        await self.laurium.aclose()


def extraction_from_env(inner: ModelPort, env: Mapping[str, str], *, master: str) -> ModelPort:
    """`inner` itself unless the deployment chose Laurium; then `inner` with Laurium extracting.
    `master` is the gateway's master key the Conduit holds: the root Laurium's own key and each
    engine's are derived from, never itself sent to Laurium's service (decision 8)."""
    engine = env.get(ENGINE, DEEP_READ)
    if engine == DEEP_READ:
        return inner
    if engine != LAURIUM:
        raise LauriumNotConfigured(
            f"The deployment names the extraction engine {engine!r}, which this Conduit does not "
            f"run: {DEEP_READ} or {LAURIUM}."
        )
    url = env.get(URL, "").strip()
    if not url:
        raise LauriumNotConfigured(
            "The deployment chose Laurium as its extraction engine but gives no address for "
            f"Laurium's service ({URL}): render the deployment again."
        )
    defaults = LauriumConfig.from_env()
    config = LauriumConfig(
        base_url=url, gateway_key=master, timeout_seconds=defaults.timeout_seconds
    )
    return LauriumExtracts(inner, ExtractLauriumAdapter(config))
