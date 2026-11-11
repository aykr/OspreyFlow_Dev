"""A stand-in for Laurium's service (`services/laurium/app.py`), for the adapter's offline tests.

**It refuses what the real service refuses** (rule 15's second worked example), each the same way:
no gateway token (401), a text over the service's limit (413), a schema outside Laurium's subset (400,
by the service's own `schema_map`, not a copy), and every gateway refusal (502 with the gateway's
status, and for a 429 the gateway's error so the adapter can read a limit). The gateway behind it is
the measured stand-in (`adapters/model_litellm/stand_in.py`), called in-process with the token the
adapter sent, so a wrong key, an unknown model and a limit are the gateway's own refusals. The same
refusals are asked of the real service, through the same stand-in served over HTTP, in
`tests/conformance/model_port/test_laurium_service.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError, create_model

from adapters.model_litellm.stand_in import StandInGateway
from services.laurium.app_contract import MAX_CHARS
from services.laurium.schema_map import UnsupportedSchema, laurium_schema, output_for


@dataclass
class FakeLauriumService:
    gateway: StandInGateway
    #: Every request body the adapter sent, with its token.
    received: list[tuple[str | None, dict[str, Any]]] = field(default_factory=list)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/v1/extract" or request.method != "POST":
            return httpx.Response(404, json={"detail": "Not Found"})
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() or None
        body = json.loads(request.content)
        self.received.append((token, body))
        if token is None:
            return httpx.Response(401, json={"refusal": "no_gateway_token"})
        if len(body["text"]) > MAX_CHARS:
            return httpx.Response(413, json={"refusal": "too_long"})
        try:
            fields = laurium_schema(body["json_schema"])
        except UnsupportedSchema as exc:
            return httpx.Response(400, json={"refusal": "unsupported_schema", "words": str(exc)})
        chat: dict[str, Any] = {
            "model": body["model"],
            "messages": [{"role": "user", "content": body["text"]}],
        }
        if body.get("tag"):
            chat["metadata"] = {"tags": [body["tag"]]}
        with httpx.Client(transport=self.gateway.transport(), base_url="http://litellm:4000") as c:
            answer = c.post(
                "/chat/completions", json=chat, headers={"Authorization": f"Bearer {token}"}
            )
        if answer.status_code != 200:
            refusal: dict[str, Any] = {"refusal": "gateway", "gateway_status": answer.status_code}
            if answer.status_code == 429:
                refusal["gateway_error"] = answer.json().get("error")
            return httpx.Response(502, json=refusal)
        content = answer.json()["choices"][0]["message"]["content"]
        model = create_model(  # type: ignore[call-overload]
            "Answer", **{name: (kind, ...) for name, kind in fields.items()}
        )
        try:
            parsed = model.model_validate_json(content)
        except ValidationError:
            return httpx.Response(502, json={"refusal": "unparseable"})
        return httpx.Response(
            200,
            json={
                "document_id": body["document_id"],
                "model": body["model"],
                "data": output_for(parsed, body["json_schema"]),
                "engine": "laurium:0.6.0",
            },
        )
