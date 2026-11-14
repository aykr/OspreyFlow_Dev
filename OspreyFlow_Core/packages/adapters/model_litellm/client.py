"""Thin async HTTP client over the LiteLLM proxy's OpenAI-compatible `/chat/completions` route.

`spec/00_ARCHITECTURE.md` §2.4: the Conduit talks to one OpenAI-compatible base URL; LiteLLM
resolves the `model` name to whatever backend `deploy/compose/dev.yaml`'s `litellm` service is
configured with (Ollama locally, vLLM on the cluster profile) — this client never talks to Ollama
directly, so swapping the backend is a proxy config change, not a code change (ADR-005's "model
flexible" requirement).

Schema conformance is enforced two ways, not one. Before any network call, `response_schema` is
checked against the JSON Schema meta-schema — a malformed schema is rejected deterministically, in
this client's own code, rather than however the proxy or backend happens to fail on one
(`InvalidExtractionSchemaError`, no model call spent on it). A syntactically valid schema is then
handed to the backend for constrained decoding *and* the returned content is validated again on
this side (`jsonschema.validate`) before being trusted — constrained decoding makes a violation
unlikely, not impossible (a truncated response, a backend that ignores `response_format`), and
`ModelPort`'s whole contract is that a caller never has to guess whether the shape it got back is
real.

`embed()` is a second, separate model call — a text-embedding model, not the extraction model —
routed through the same proxy and the same `/embeddings` OpenAI-compatible route. It has no JSON
Schema to validate against; the one thing worth checking is that the count of vectors returned
matches the count of texts sent, in order.

`describe_image()` reuses `extract_json`'s exact schema-constrained-decoding path with an image
attached to the same chat message, in the standard OpenAI vision content-part shape
(`{"type": "image_url", "image_url": {"url": "data:<mime>;base64,..."}}`) — confirmed directly
against a live LiteLLM/Ollama vision model that this translates correctly to Ollama's own
`images` field, so this client never needs a second, image-specific code path for schema
conformance or retries.

**Each call names its engine and job** (ADR-135 Amendment 3): inside `usage.calling(engine, job)`,
set by the routing, a chat call carries one tag, `osprey:<engine>/<job>`, which the gateway records
its usage under, and a hosted engine's call goes with that engine's own gateway key
(`usage.engine_key`), whose limits the gateway enforces; a call outside it, or for `local`, goes
with the master key, untagged. A limit's refusal is `ModelLimitReached`, never the gateway's words.
No call carries a person's id (`user`) or anything else about who asked.

`transcribe()` is architecturally different from the other three: Whisper's `/audio/transcriptions`
is a multipart upload, not a JSON chat completion, and its response shape is fixed (segments, word
timings) rather than caller-schema-driven, so there is nothing to validate here the way
`extract_json`/`embed` validate theirs — only that the proxy call itself succeeded.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .errors import (
    EmbeddingFailedError,
    ExtractionFailedError,
    InvalidExtractionSchemaError,
    ModelEngineRefused,
    ModelUnavailableError,
    TranscriptionFailedError,
)
from .usage import (
    LOCAL,
    current_call,
    engine_key,
    limit_refusal,
    provider_refusal,
    usage_tag,
)

_MAX_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class LiteLLMConfig:
    host: str = "localhost"
    port: int = 4000
    #: Dev-only fixed key, the same pattern as every other dev-compose credential
    #: (`arcadedb`'s `playwithdata123`, `postgres`'s `osprey`/`playwithdata123`) — never a
    #: production secret, and never read from anywhere but the environment in a real deployment
    #: (`05_DEPLOYMENT.md` §7).
    api_key: str = "sk-ospreyflow-dev"
    #: How long one model call may take (ADR-095): a 7B model on a CPU-only Docker host reads a
    #: long email and writes its answer in minutes, not seconds. A deployment may set it.
    timeout_seconds: float = 900.0
    #: How long a hosted engine's call may take (ADR-135 Amendment 13): a provider answers in
    #: seconds, so a person is not left fifteen minutes on a hosted engine that has stopped. The
    #: deployment's own model keeps `timeout_seconds`.
    hosted_timeout_seconds: float = 120.0

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> LiteLLMConfig:
        return cls(
            host=os.environ.get("LITELLM_HOST", "localhost"),
            port=int(os.environ.get("LITELLM_PORT", "4000")),
            api_key=os.environ.get("LITELLM_API_KEY", "sk-ospreyflow-dev"),
            timeout_seconds=float(os.environ.get("OSPREY_MODEL_TIMEOUT_SECONDS", "900")),
            hosted_timeout_seconds=float(
                os.environ.get("OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS", "120")
            ),
        )


class LiteLLMClient:
    def __init__(
        self, config: LiteLLMConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._master = config.api_key
        self._timeout = config.timeout_seconds
        self._hosted_timeout = config.hosted_timeout_seconds
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=config.timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _routed(self, body: dict[str, Any] | None = None) -> dict[str, str]:
        """The headers for the current call (its engine's key, or none to keep the master key),
        and its tag added to `body`."""
        call = current_call()
        if call is None:
            return {}
        if body is not None:
            body["metadata"] = {"tags": [usage_tag(call.engine, call.job)]}
        if call.engine == LOCAL:
            return {}
        return {"Authorization": f"Bearer {engine_key(self._master, call.engine)}"}

    def _bound(self) -> float:
        """The current call's time bound: a hosted engine's own, or the deployment's model's."""
        call = current_call()
        hosted = call is not None and call.engine != LOCAL
        return self._hosted_timeout if hosted else self._timeout

    async def extract_json(
        self,
        *,
        model: str,
        text: str,
        response_schema: dict[str, Any],
        image: bytes | None = None,
        image_mime_type: str = "image/png",
    ) -> dict[str, Any]:
        """Schema-constrained decoding: `text` (plus an optional `image`) in, an object validating
        against `response_schema` out. Raises `InvalidExtractionSchemaError` for a schema this
        method cannot even attempt, `ExtractionFailedError` if every attempt at a conforming
        response is exhausted."""
        self._check_schema(response_schema)

        last_error: Exception | None = None
        attempts = 0
        for _ in range(_MAX_ATTEMPTS):
            attempts += 1
            try:
                content = await self._chat_completion(
                    model, text, response_schema, image, image_mime_type
                )
                data: dict[str, Any] = json.loads(content)
                Draft202012Validator(response_schema).validate(data)
                return data
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                continue
            except httpx.ReadTimeout:
                # ADR-135 Amendment 13: measured as the client meets a slow engine. Not asked
                # again: a second wait as long helps no one.
                raise ModelEngineRefused("timed_out", timeout_seconds=self._bound()) from None
            except httpx.HTTPStatusError as exc:
                last_error = exc
                limit = limit_refusal(exc.response)
                if limit is not None:
                    raise limit from None
                # ADR-135 Amendment 13: the engine's own refusal, passed on by the gateway, which
                # has already tried it three times (measured), so it is not asked again.
                refused = provider_refusal(exc.response)
                if refused is not None:
                    raise refused from None
                if exc.response.status_code == 404:
                    raise ModelUnavailableError(
                        f"model {model!r} is not available from the model proxy: not routed, "
                        "or not yet downloaded"
                    ) from exc
                if exc.response.status_code < 500:
                    break  # a 4xx from the proxy will not succeed on retry
                continue

        raise ExtractionFailedError(
            f"model {model!r} did not return a response conforming to the given schema "
            f"after {attempts} attempt(s): {last_error}"
        ) from last_error

    async def _chat_completion(
        self,
        model: str,
        text: str,
        response_schema: dict[str, Any],
        image: bytes | None,
        image_mime_type: str,
    ) -> str:
        content: str | list[dict[str, Any]] = text
        if image is not None:
            encoded = base64.b64encode(image).decode("ascii")
            content = [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_mime_type};base64,{encoded}"},
                },
            ]
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction",
                    "schema": response_schema,
                    "strict": True,
                },
            },
        }
        headers = self._routed(body)
        resp = await self._http.post(
            "/chat/completions", json=body, headers=headers, timeout=self._bound()
        )
        resp.raise_for_status()
        body = resp.json()
        return str(body["choices"][0]["message"]["content"])

    async def transcribe(self, *, model: str, audio: bytes, language: str | None) -> dict[str, Any]:
        """`/audio/transcriptions` — a multipart upload, not a JSON chat completion. Returns the
        raw OpenAI-Whisper-shaped response body (`text`, `language`, `segments`, each segment's
        `words` when word-level timestamps are requested); `ModelLiteLLMAdapter.transcribe()` is
        what maps this onto `schemas.model.Transcript`."""
        data: dict[str, str] = {
            "model": model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        if language is not None:
            data["language"] = language
        try:
            # Untagged: whether the gateway reads a tag from a multipart form was not measured, so
            # none is sent (ADR-135 Amendment 3, "Left"); the engine's key still carries its limits.
            resp = await self._http.post(
                "/audio/transcriptions",
                data=data,
                files={"file": ("audio.wav", audio, "audio/wav")},
                headers=self._routed(),
            )
            limit = limit_refusal(resp)
            if limit is not None:
                raise limit
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TranscriptionFailedError(
                f"model {model!r} transcription call failed: {exc}"
            ) from exc
        result: dict[str, Any] = resp.json()
        return result

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        """`/embeddings` — no schema to validate, no constrained decoding: an embedding model's
        response shape is fixed (a vector per input), so the only thing worth checking is that the
        proxy actually returned one vector per input, in order."""
        if not texts:
            return []
        body: dict[str, Any] = {"model": model, "input": list(texts)}
        # Untagged: a tag on `/embeddings` was not measured (ADR-135 Amendment 3, "Left").
        resp = await self._http.post("/embeddings", json=body, headers=self._routed())
        limit = limit_refusal(resp)
        if limit is not None:
            raise limit
        resp.raise_for_status()
        body = resp.json()
        by_index = sorted(body["data"], key=lambda row: row["index"])
        vectors: list[list[float]] = [row["embedding"] for row in by_index]
        if len(vectors) != len(texts):
            raise EmbeddingFailedError(
                f"model {model!r} returned {len(vectors)} embedding(s) for {len(texts)} input(s)"
            )
        return vectors

    @staticmethod
    def _check_schema(response_schema: dict[str, Any]) -> None:
        try:
            Draft202012Validator.check_schema(response_schema)
        except SchemaError as exc:
            raise InvalidExtractionSchemaError(
                f"not a valid JSON Schema (Draft 2020-12): {exc.message}"
            ) from exc
