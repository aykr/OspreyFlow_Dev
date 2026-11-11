"""Laurium chosen, at the Conduit's start (`06_DECISIONS.md` ADR-135 Amendment 6, decision 8 and its
"making the key at start, and replacing it when the master key rotates, are part 2's"; P12 part 2).

- **`extract` alone goes to Laurium** when the deployment chose it (`OSPREY_EXTRACTION_ENGINE`,
  rendered from `models.extraction_engine`); `embed`, `transcribe` and `describe_image` stay the
  LiteLLM adapter's. Not chosen, the Conduit's model is exactly the one it was. Chosen without
  Laurium's address, the start is refused in words, never a silent fall back to Deep read.
- **Laurium's key is made at start** on the gateway with the models it is given alone, and **every
  older Laurium key is deleted**: one made from a master key since rotated would otherwise stay
  valid for whoever holds the old master key. Every page is read before anything is deleted, each
  stale key named by its hash alone; an engine's key and an untagged key are someone else's and are
  left alone.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from adapters.extract_laurium.adapter import ExtractLauriumAdapter
from adapters.extract_laurium.composed import (
    LauriumExtracts,
    LauriumNotConfigured,
    extraction_from_env,
    laurium_reads,
)
from adapters.extract_laurium.keys import METADATA, laurium_at_start, laurium_key
from adapters.model_litellm.stand_in import StandInGateway
from adapters.model_litellm.usage import engine_key
from schemas.model import ExtractionRequest, ExtractionResult

MASTER = "sk-planted-master-now"
OLD_MASTER = "sk-planted-master-before"
MODEL = "qwen2.5:7b-instruct"


class _Inner:
    """A `ModelPort` that records which of its operations were called."""

    def __init__(self) -> None:
        self.called: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.called.append("extract")
        return ExtractionResult(document_id=req.document_id, model=req.model, data={"by": "inner"})

    async def transcribe(self, req: Any) -> Any:
        self.called.append("transcribe")
        return "transcript"

    async def describe_image(self, req: Any) -> Any:
        self.called.append("describe_image")
        return "analysis"

    async def embed(self, texts: Sequence[str]) -> Any:
        self.called.append("embed")
        return [[0.0]]


class _Laurium:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.asked.append(req.document_id)
        return ExtractionResult(
            document_id=req.document_id, model=req.model, data={"by": "laurium"}
        )


def _request() -> ExtractionRequest:
    return ExtractionRequest(document_id="d-1", text="Owen Wilson.", json_schema={"type": "object"},
                             model=MODEL)  # fmt: skip


async def test_extract_alone_goes_to_laurium() -> None:
    inner, laurium = _Inner(), _Laurium()
    model = LauriumExtracts(inner, laurium)  # type: ignore[arg-type]
    with laurium_reads():  # the review queue's extraction, the one caller Laurium serves
        result = await model.extract(_request())
    assert result.data == {"by": "laurium"} and laurium.asked == ["d-1"]
    await model.embed(["a"])
    await model.transcribe(object())
    await model.describe_image(object())
    assert inner.called == ["embed", "transcribe", "describe_image"]


def test_not_chosen_the_model_is_the_one_it_was() -> None:
    inner = _Inner()
    for env in ({}, {"OSPREY_EXTRACTION_ENGINE": "deep_read"}):
        assert extraction_from_env(inner, env, master=MASTER) is inner  # type: ignore[arg-type]


def test_chosen_extract_goes_to_lauriums_service_with_the_master_key_held_back() -> None:
    inner = _Inner()
    env = {"OSPREY_EXTRACTION_ENGINE": "laurium", "OSPREY_LAURIUM_URL": "http://laurium:8000"}
    model = extraction_from_env(inner, env, master=MASTER)  # type: ignore[arg-type]
    assert isinstance(model, LauriumExtracts)
    assert isinstance(model.laurium, ExtractLauriumAdapter)
    assert model.laurium.base_url == "http://laurium:8000"


@pytest.mark.parametrize(
    "env",
    [
        {"OSPREY_EXTRACTION_ENGINE": "laurium"},
        {"OSPREY_EXTRACTION_ENGINE": "laurium", "OSPREY_LAURIUM_URL": ""},
        {"OSPREY_EXTRACTION_ENGINE": "Laurium", "OSPREY_LAURIUM_URL": "http://laurium:8000"},
    ],
)
def test_a_choice_it_cannot_honour_is_refused_in_words(env: dict[str, str]) -> None:
    with pytest.raises(LauriumNotConfigured, match="extraction engine"):
        extraction_from_env(_Inner(), env, master=MASTER)  # type: ignore[arg-type]


def _gateway() -> StandInGateway:
    return StandInGateway(
        master_key=MASTER, salt_key="salt", providers={}, config_models=frozenset({MODEL, "other"})
    )


def _hold(gateway: StandInGateway, key: str, metadata: dict[str, str] | None) -> None:
    with httpx.Client(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        resp = c.post(
            "/key/generate",
            json={"key": key, "models": [MODEL], "metadata": metadata or {}},
            headers={"Authorization": f"Bearer {MASTER}"},
        )
    resp.raise_for_status()


async def test_lauriums_key_is_made_and_the_stale_ones_deleted_alone() -> None:
    gateway = _gateway()
    stale = laurium_key(OLD_MASTER)
    engines = engine_key(MASTER, "gemini")
    untagged = "sk-someone-elses"
    _hold(gateway, stale, METADATA)
    _hold(gateway, engines, {"osprey_engine": "gemini"})
    _hold(gateway, untagged, None)
    async with httpx.AsyncClient(
        transport=gateway.transport(), base_url="http://litellm:4000"
    ) as c:
        key = await laurium_at_start(c, MASTER, [MODEL])
        again = await laurium_at_start(c, MASTER, [MODEL])
    assert key == again == laurium_key(MASTER)
    held = {k for k in gateway.virtual_keys()}
    assert held == {key, engines, untagged}, "a stale Laurium key survived, or another was deleted"
    assert gateway.virtual_key(key).models == [MODEL]  # type: ignore[union-attr]
    assert gateway.virtual_key(key).metadata == METADATA  # type: ignore[union-attr]


async def test_stale_keys_are_named_by_their_hash_alone() -> None:
    gateway = _gateway()
    stale = laurium_key(OLD_MASTER)
    _hold(gateway, stale, METADATA)
    sent: list[bytes] = []
    inner = gateway.transport()

    def _record(request: httpx.Request) -> httpx.Response:
        sent.append(request.content)
        return inner.handle_request(request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_record), base_url="http://litellm:4000"
    ) as c:
        await laurium_at_start(c, MASTER, [MODEL])
    deletes = [b for b in sent if b"keys" in b]
    assert deletes and hashlib.sha256(stale.encode()).hexdigest().encode() in deletes[0]
    assert all(stale.encode() not in b for b in sent), "the stale key itself travelled"
