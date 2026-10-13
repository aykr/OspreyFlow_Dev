"""ADR-114 decision 11, Amendment 6 point 4, and 04 §4's "egress is default-denied": a client's own
provider replaces the local model for the roles it names — but only for material whose handling
code the deployment declared sendable. Anything else runs on the local model, or is refused in
words where the deployment has none for that role. Material whose handling is not given is never
sent. A role the provider does not name is never sent, whatever the caller asked for.

The inner adapter here records what it was asked; what matters is which model each request
reached, and that nothing above the sendable codes reached the provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from services.api.model_routing import ModelEgressRefused, RoleRoute, RoutedModel

from schemas.domain import Handling
from schemas.model import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    VisionRequest,
)

LOCAL, PROVIDER = "qwen2.5:7b-instruct", "openai/gpt-4o-mini"


def _handling(code: str) -> Handling:
    return Handling(classification="OFFICIAL", handling_code=code, owning_unit="u", originator="u")


class _Inner:
    def __init__(self) -> None:
        self.models: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.models.append(req.model)
        return ExtractionResult(document_id=req.document_id, model=req.model, data={})

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        self.models.append(req.model)
        return Transcript(document_id=req.document_id, model=req.model, language="en", segments=[])

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        self.models.append(req.model)
        return ImageAnalysis(document_id=req.document_id, model=req.model, data={})

    async def embed(self, texts: Sequence[str]) -> list[Any]:
        return []


def _routed(
    inner: _Inner, *, local: str | None = LOCAL, sendable: Sequence[str] = ("P",)
) -> RoutedModel:
    return RoutedModel(
        inner,  # type: ignore[arg-type]
        routes={
            "extraction": RoleRoute(local=local, provider=PROVIDER),
            "vision": RoleRoute(local="moondream", provider=None),
            "transcription": RoleRoute(local="whisper", provider=None),
        },
        sendable_handling_codes=frozenset(sendable),
    )


def _extract(model: str, handling: Handling | None) -> ExtractionRequest:
    return ExtractionRequest(
        document_id="d", text="t", json_schema={}, model=model, handling=handling
    )


async def test_sendable_material_goes_to_the_clients_provider() -> None:
    inner = _Inner()
    result = await _routed(inner).extract(_extract(LOCAL, _handling("P")))
    assert inner.models == [PROVIDER] and result.model == PROVIDER


async def test_material_above_the_sendable_codes_runs_locally() -> None:
    inner = _Inner()
    await _routed(inner).extract(_extract(LOCAL, _handling("C")))
    assert inner.models == [LOCAL]


async def test_material_with_no_handling_given_is_never_sent() -> None:
    inner = _Inner()
    await _routed(inner).extract(_extract(LOCAL, None))
    assert inner.models == [LOCAL]


async def test_asking_for_the_provider_by_name_does_not_send_unsendable_material() -> None:
    """A caller may name a model (ADR-005); naming the provider is no way round the codes."""
    inner = _Inner()
    await _routed(inner).extract(_extract(PROVIDER, _handling("C")))
    assert inner.models == [LOCAL]


async def test_with_no_local_model_unsendable_material_is_refused_in_words_and_not_sent() -> None:
    inner = _Inner()
    with pytest.raises(ModelEgressRefused, match="handling code C may not be sent"):
        await _routed(inner, local=None).extract(_extract(LOCAL, _handling("C")))
    assert inner.models == []


async def test_a_role_the_provider_does_not_name_is_never_sent() -> None:
    inner = _Inner()
    request = VisionRequest(document_id="d", image=b"x", text="t", json_schema={},
                            model=PROVIDER, handling=_handling("P"))  # fmt: skip
    await _routed(inner).describe_image(request)
    assert inner.models == ["moondream"]


async def test_with_no_sendable_codes_nothing_is_ever_sent() -> None:
    inner = _Inner()
    await _routed(inner, sendable=()).extract(_extract(LOCAL, _handling("P")))
    assert inner.models == [LOCAL]


def test_the_conduit_reads_its_routes_from_what_the_renderer_wrote() -> None:
    """The names `harness/render.py` writes into `deployment.env` are the ones read here."""
    from services.api.config import DeploymentModels
    from services.api.model_routing import routes_from_env

    local = DeploymentModels(extraction=LOCAL, vision="moondream", transcription="whisper",
                             embedding="minilm")  # fmt: skip
    routes, codes = routes_from_env(
        local,
        {"OSPREY_PROVIDER_EXTRACTION_MODEL": PROVIDER, "OSPREY_SENDABLE_HANDLING_CODES": "P, C"},
    )
    assert routes["extraction"] == RoleRoute(local=LOCAL, provider=PROVIDER)
    assert routes["vision"] == RoleRoute(local="moondream", provider=None)
    assert codes == frozenset({"P", "C"})
    routes, codes = routes_from_env(local, {})
    assert all(r.provider is None for r in routes.values()) and codes == frozenset()
