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
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.model_routing import Engine, ModelEgressRefused, ModelRoutes, RoutedModel

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
#: ADR-136: the material comes from a dataset set to `any`, so only the handling codes decide here.
OPEN = InMemoryDatasetStore()
OPEN.add(Dataset(id="open", name="Open", owning_unit="u", created_by="seed", egress="any",
                 created_at="2026-11-01T00:00:00Z"))  # type: ignore[arg-type]  # fmt: skip


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
    """Amendment 6's one provider, as ADR-135 reads it: an engine with a key, the default for the
    one role it takes."""
    openai = Engine(name="openai", label="OpenAI", models={"extraction": PROVIDER},
                    key_present=True)  # fmt: skip
    return RoutedModel(
        inner,  # type: ignore[arg-type]
        egress=OPEN,
        routes=ModelRoutes(
            locals={"extraction": local, "vision": "moondream", "transcription": "whisper"},
            engines={"openai": openai},
            defaults={"extraction": "openai"},
            sendable=frozenset(sendable),
        ),
    )


def _extract(model: str, handling: Handling | None) -> ExtractionRequest:
    return ExtractionRequest(
        document_id="d", text="t", json_schema={}, model=model, handling=handling,
        datasets=["open"],
    )  # fmt: skip


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
                            model=PROVIDER, handling=_handling("P"), datasets=["open"])  # fmt: skip
    await _routed(inner).describe_image(request)
    assert inner.models == ["moondream"]


async def test_with_no_sendable_codes_nothing_is_ever_sent() -> None:
    inner = _Inner()
    await _routed(inner, sendable=()).extract(_extract(LOCAL, _handling("P")))
    assert inner.models == [LOCAL]


def test_the_conduit_reads_its_routes_from_what_the_renderer_wrote() -> None:
    """The names `harness/render.py` writes into `deployment.env` are the ones read here
    (`test_model_engines.py` reads them from the renderer itself)."""
    from services.api.config import DeploymentModels
    from services.api.model_routing import routes_from_env

    local = DeploymentModels(extraction=LOCAL, vision="moondream", transcription="whisper",
                             embedding="minilm")  # fmt: skip
    routes = routes_from_env(
        local,
        {
            "OSPREY_MODEL_ENGINES": '[{"name":"openai","label":"OpenAI",'
            '"roles":{"extraction":"openai/gpt-4o-mini"}}]',
            "OSPREY_MODEL_DEFAULTS": '{"extraction":"openai"}',
            "OSPREY_MODEL_KEY_PRESENT_OPENAI": "yes",
            "OSPREY_SENDABLE_HANDLING_CODES": "P, C",
        },
    )
    assert routes.locals["extraction"] == LOCAL
    assert routes.engines["openai"].models == {"extraction": PROVIDER}
    assert routes.default_for("extraction") == "openai" and routes.default_for("vision") == "local"
    assert routes.sendable == frozenset({"P", "C"})
    bare = routes_from_env(local, {})
    assert bare.engines == {} and bare.sendable == frozenset()
