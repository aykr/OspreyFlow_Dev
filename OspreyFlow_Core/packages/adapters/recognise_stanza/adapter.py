"""The `ner` sidecar's client (`services/ner/app.py`, ADR-098 decision 2). One call, `POST
/v1/recognise`; a refusal of the text (422, past the sidecar's limit) is `RecogniserRefusedError`,
and an unreachable or failing sidecar `RecogniserUnavailableError`, so the Conduit can say which."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from ports.recognise import (
    RecogniseResult,
    RecogniserRefusedError,
    RecogniserUnavailableError,
)


@dataclass(frozen=True)
class RecogniserConfig:
    base_url: str = "http://ner:8000"
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> RecogniserConfig:
        return cls(
            base_url=os.environ.get("OSPREY_RECOGNISER_URL", "http://ner:8000"),
            timeout_seconds=float(os.environ.get("OSPREY_RECOGNISER_TIMEOUT_SECONDS", "60")),
        )


class RecogniseStanzaAdapter:
    def __init__(self, config: RecogniserConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(timeout=config.timeout_seconds)

    async def recognise(self, text: str) -> RecogniseResult:
        try:
            response = await self._client.post(
                f"{self._config.base_url}/v1/recognise", json={"text": text}
            )
        except httpx.HTTPError as error:
            raise RecogniserUnavailableError(str(error)) from error
        if response.status_code == 422:
            raise RecogniserRefusedError("the text is past the recogniser's limit")
        if response.status_code != 200:
            raise RecogniserUnavailableError(f"the recogniser answered {response.status_code}")
        return RecogniseResult.model_validate(response.json())

    async def aclose(self) -> None:
        await self._client.aclose()
