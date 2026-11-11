"""`ExtractLauriumAdapter`: `ModelPort.extract` as a thin client of Laurium's own service
(`06_DECISIONS.md` ADR-135 Amendment 6 decision 3; `services/laurium/app_contract.py` has what the
service answers). Laurium needs Python 3.13 and brings LangChain; the Conduit runs 3.12 and carries
neither, so the library runs in its own container and this adapter is all of it the Conduit holds:
`httpx` and `jsonschema`, as the LiteLLM adapter.

Only `extract`: the other `ModelPort` operations stay with `adapters/model_litellm` (Amendment 5
decision 1). What it holds to, as that adapter does:

- **the request's schema is checked before any call**: a malformed one is
  `InvalidExtractionSchemaError`, and so is one the service says Laurium is not given;
- **the answer is checked against the request's schema before it is trusted**: the service parses
  it with Pydantic types mapped from the schema, which is not every constraint a JSON Schema can
  state;
- **each call names its engine and job** (ADR-135 Amendment 3): inside `usage.calling`, the call
  carries its tag and goes with the engine's own gateway key, which the service uses for that call
  alone; a call for `local`, or outside the routing, goes with the master key;
- **each refusal is a typed error in our words**, never the gateway's, which can name part of a
  key: a limit is `ModelLimitReached` (read by `usage.limit_refusal`, the measured reader), a model
  the provider does not offer `ModelUnavailableError`, anything else `ExtractionFailedError`.

`ExtractionResult.engine` stays `None`: the routing sets it, as for every adapter.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from adapters.model_litellm.errors import (
    ExtractionFailedError,
    InvalidExtractionSchemaError,
    ModelUnavailableError,
)
from adapters.model_litellm.usage import LOCAL, current_call, engine_key, limit_refusal, usage_tag
from schemas.model import ExtractionRequest, ExtractionResult


@dataclass(frozen=True, slots=True)
class LauriumConfig:
    #: Laurium's service, e.g. `http://laurium:8000`.
    base_url: str
    #: The gateway's master key, which the Conduit already holds (`LITELLM_API_KEY`): sent for the
    #: deployment's own models, and the root an engine's own key is derived from.
    gateway_key: str
    #: As the LiteLLM adapter's (ADR-095): a long document on a small model takes minutes.
    timeout_seconds: float = 900.0

    @classmethod
    def from_env(cls) -> LauriumConfig:
        return cls(
            base_url=os.environ.get("OSPREY_LAURIUM_URL", "http://laurium:8000"),
            gateway_key=os.environ.get("LITELLM_API_KEY", "sk-ospreyflow-dev"),
            timeout_seconds=float(os.environ.get("OSPREY_MODEL_TIMEOUT_SECONDS", "900")),
        )


class ExtractLauriumAdapter:
    def __init__(
        self, config: LauriumConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._master = config.gateway_key
        self._http = httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds, transport=transport
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        try:
            Draft202012Validator.check_schema(req.json_schema)
        except SchemaError as exc:
            raise InvalidExtractionSchemaError(
                f"not a valid JSON Schema (Draft 2020-12): {exc.message}"
            ) from exc

        call = current_call()
        token = self._master
        tag: str | None = None
        if call is not None:
            tag = usage_tag(call.engine, call.job)
            if call.engine != LOCAL:
                token = engine_key(self._master, call.engine)

        body: dict[str, Any] = {
            "document_id": req.document_id,
            "text": req.text,
            "json_schema": req.json_schema,
            "model": req.model,
            "tag": tag,
        }
        try:
            resp = await self._http.post(
                "/v1/extract", json=body, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError:
            raise ExtractionFailedError(
                "Laurium's service could not be reached, or did not answer in time."
            ) from None

        if resp.status_code != 200:
            raise _refusal(resp, req.model)

        answer = resp.json()
        data = answer.get("data")
        if not isinstance(data, dict):
            raise ExtractionFailedError("Laurium's service answered without a finding.")
        try:
            Draft202012Validator(req.json_schema).validate(data)
        except ValidationError as exc:
            raise ExtractionFailedError(
                f"Laurium's answer for model {req.model!r} does not conform to the given schema: "
                f"{exc.message}"
            ) from None
        return ExtractionResult(document_id=req.document_id, model=req.model, data=data)


def _refusal(resp: httpx.Response, model: str) -> Exception:
    """The service's refusal as `ModelPort`'s typed error, in our words."""
    try:
        said: dict[str, Any] = dict(resp.json())
    except ValueError:
        said = {}
    kind = said.get("refusal")
    if kind == "unsupported_schema":
        return InvalidExtractionSchemaError(
            f"Laurium is not given this schema: {said.get('words', 'not supported')}"
        )
    if kind == "too_long":
        return ExtractionFailedError(
            "The text is too long for Laurium's service to read in one call."
        )
    if kind == "no_gateway_token":
        return ExtractionFailedError(
            "Laurium's service was called without the gateway's token: a deployment fault."
        )
    if kind == "unparseable":
        return ExtractionFailedError(
            f"Laurium could not read model {model!r}'s answer into the given schema."
        )
    if kind == "gateway_unreachable":
        return ExtractionFailedError(
            "The model gateway could not be reached from Laurium's service, or did not answer in "
            "time."
        )
    if kind == "gateway":
        status = said.get("gateway_status")
        if status == 429:
            limit = limit_refusal(
                httpx.Response(429, json={"error": said.get("gateway_error") or {}})
            )
            if limit is not None:
                return limit
        if status == 404:
            return ModelUnavailableError(
                f"model {model!r} is not available from the model proxy: not routed, or not yet "
                "downloaded"
            )
        return ExtractionFailedError(
            f"The model gateway refused Laurium's call for model {model!r} (HTTP {status})."
        )
    return ExtractionFailedError(
        f"Laurium's service refused the call (HTTP {resp.status_code})."
    )
