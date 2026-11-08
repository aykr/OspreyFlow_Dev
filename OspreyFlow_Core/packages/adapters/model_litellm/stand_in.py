"""A stand-in for the LiteLLM proxy's admin and completion API, for tests only (`06_DECISIONS.md`
ADR-135 Amendment 2; `CLAUDE.md` rule 15: a fixture models the dependency's refusals, not only its
grants).

**Every behaviour here was measured** against the image the product pins
(`ghcr.io/berriai/litellm@sha256:d295634e…`), on 8 November 2026 under the platform lease on test
stack a, with its own database and a stand-in provider (ADR-135 Amendment 2, "Measured first"):

- the proxy's own token: none → 401 "No api key passed in."; a wrong one → 401 "Invalid proxy server
  token passed. Received API Key = sk-...WXYZ", echoing its last four characters;
- `POST /model/new`: an empty body → 500; a duplicate id → 500; otherwise 200 with every
  `litellm_params` value encrypted; **an entry with no key is accepted**;
- `PATCH /model/{id}/update`: an unknown id → 404 "Model … not found on proxy.";
  `POST /model/update` without `model_info` → 400;
- `POST /model/delete`: an unknown id → 400 "Model with id=… not found in db";
- `GET /v2/model/info`: each entry, never its key;
- `POST /chat/completions`: an unknown `model_name` → 400 "Invalid model name passed in
  model=…"; no provider key → **500** "AuthenticationError … api_key client option must be set";
  a wrong key → 401 "AuthenticationError … Incorrect API key provided: sk-PLA****7Q4Z",
  **echoing part of the key**, and the same in the gateway's log; a model the provider does not
  offer → 404 "NotFoundError"; after any of those three the entry is **cooled down**, answering
  429 "No deployments available for selected model … cooldown_list=[…]" for about a minute, even
  once a good key is set;
- `POST /credentials` stores a named key; an entry naming it (`litellm_credential_name`) uses it;
  `PATCH /credentials/{name}` rotates it for every such entry; `DELETE` removes it (unknown: 404),
  and an entry naming a missing credential answers as a missing key; **`GET /credentials` returns
  the key masked to two characters at each end** (`sk****4Z`), which is why the stand-in counts
  every such read (`credential_reads`);
- restarted with a different encryption key, every stored entry and credential is dropped;
- an entry deleted while it is cooled down still answers 429 for its `model_name` until the
  cooldown passes, not "Invalid model name" (measured on 8 November 2026 with the Conduit's own
  client, `GatewayAdmin`, under the platform lease on stack a).

Not measured, so not modelled as refusals and never relied on: `POST /credentials` for a name that
exists, and `PATCH /credentials/{name}` or `PATCH /model/{id}/update` at all. The Conduit's client
asks neither: it removes a credential before making it (`GatewayAdmin.put_credential`) and deletes
an edited engine's entries before making them again (`ModelAdmin._reconcile`).

The stand-in is an `httpx.MockTransport`, so the code under test sends real HTTP requests through
the same `httpx.AsyncClient` it uses against the real gateway. Its own red-then-green proof is
`tests/adapters/model_litellm/test_stand_in_gateway.py`.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class StandInProvider:
    """What a hosted provider accepts: one key, and the models it offers to that key."""

    accepted_key: str
    offered_models: frozenset[str]


def _fragment(secret: str) -> str:
    return f"{secret[:6]}****{secret[-4:]}"


def _seal(salt: str, value: str) -> str:
    """Not real encryption: enough that a stored value is never the plaintext, and that a different
    salt cannot read it back, which is all a test may rely on."""
    pad = hashlib.sha256(salt.encode()).digest()
    raw = value.encode()
    mixed = bytes(b ^ pad[i % len(pad)] for i, b in enumerate(raw))
    return base64.urlsafe_b64encode(hashlib.sha256(salt.encode()).digest()[:4] + mixed).decode()


def _unseal(salt: str, sealed: str) -> str | None:
    raw = base64.urlsafe_b64decode(sealed.encode())
    if raw[:4] != hashlib.sha256(salt.encode()).digest()[:4]:
        return None
    pad = hashlib.sha256(salt.encode()).digest()
    return bytes(b ^ pad[i % len(pad)] for i, b in enumerate(raw[4:])).decode()


@dataclass
class _Stored:
    model_name: str
    sealed: dict[str, str]
    salt: str


@dataclass
class StandInGateway:
    master_key: str
    salt_key: str
    providers: Mapping[str, StandInProvider]
    #: The rendered `litellm.yaml`'s own entries (the local models), by `model_name`.
    config_models: frozenset[str] = frozenset()
    cooldown_seconds: float = 60.0
    clock: Callable[[], float] = field(default=lambda: 0.0)
    log: list[str] = field(default_factory=list)
    #: Every completion asked for, refused or not, by `model_name`.
    asked: list[str] = field(default_factory=list)
    #: How many times anything read the credentials back (masked, but still part of the key).
    credential_reads: int = 0
    #: Every PATCH asked of it: unmeasured on the real gateway, so the Conduit's client sends none.
    patches: list[str] = field(default_factory=list)
    #: When set, `POST /credentials` is refused with this status, as the real gateway refuses a
    #: write its database does not take (measured: 500 on `POST /model/new`).
    refuse_credentials: int | None = None
    #: Every call the gateway made to a provider: the address it went to (None for the provider's
    #: own) and the key it carried, so a test can say where a key was sent.
    sent: list[tuple[str | None, str | None]] = field(default_factory=list)
    _db: dict[str, _Stored] = field(default_factory=dict)
    _creds: dict[str, tuple[str, str]] = field(default_factory=dict)
    _cooled_until: dict[str, float] = field(default_factory=dict)
    #: A deleted entry's name, still cooled down: (its id, until when).
    _cooled_names: dict[str, tuple[str, float]] = field(default_factory=dict)

    # --- what a test may inspect --------------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def stored_ids(self) -> set[str]:
        return {i for i, s in self._db.items() if s.salt == self.salt_key}

    def stored_params(self, model_id: str) -> dict[str, str]:
        """An entry's `litellm_params`, decrypted, as the gateway itself reads them."""
        stored = self._db[model_id]
        out: dict[str, str] = {}
        for name, sealed in stored.sealed.items():
            value = _unseal(self.salt_key, sealed)
            if value is not None:
                out[name] = value
        return out

    def raw_rows(self) -> list[str]:
        """The database rows as stored (encrypted), for a test that looks for plaintext."""
        return [json.dumps(s.sealed) for s in self._db.values()] + [
            sealed for sealed, _ in self._creds.values()
        ]

    def credential(self, name: str) -> str | None:
        """A credential's key, decrypted, as the gateway itself reads it."""
        held = self._creds.get(name)
        if held is None or held[1] != self.salt_key:
            return None
        return _unseal(self.salt_key, held[0])

    def entry_for(self, model_name: str) -> str | None:
        ids = [i for i in self.stored_ids() if self._db[i].model_name == model_name]
        return ids[0] if ids else None

    def restart(self, *, salt_key: str | None = None) -> None:
        """A restart; with another encryption key, every stored entry it cannot read is dropped,
        and the gateway's log says so (measured)."""
        if salt_key is not None:
            self.salt_key = salt_key
        for model_id, stored in list(self._db.items()):
            if stored.salt != self.salt_key:
                self.log.append(f"Error upserting deployment {stored.model_name} (id={model_id})")
                del self._db[model_id]
        for name, (_, salt) in list(self._creds.items()):
            if salt != self.salt_key:
                self.log.append("Error decrypting value for key: api_key")
                del self._creds[name]
        self._cooled_until.clear()
        self._cooled_names.clear()

    # --- the API ------------------------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            return _error(401, "Authentication Error, No api key passed in.", "auth_error")
        if token != self.master_key:
            return _error(
                401,
                "Authentication Error, Invalid proxy server token passed. Received API Key = "
                f"sk-...{token[-4:]}, Key Hash (Token) =0. Unable to find token in cache or "
                "`LiteLLM_VerificationTokenTable`",
                "token_not_found_in_db",
            )
        body: dict[str, Any] = json.loads(request.content or b"{}") if request.content else {}
        path, method = request.url.path, request.method
        if method == "PATCH":
            self.patches.append(path)
        if method == "POST" and path == "/model/new":
            return self._model_new(body)
        if method == "PATCH" and path.startswith("/model/") and path.endswith("/update"):
            return self._model_patch(path.removeprefix("/model/").removesuffix("/update"), body)
        if method == "POST" and path == "/model/update":
            if "model_info" not in body:
                return _error(400, "Authentication Error, model_info not provided", "auth_error")
            return self._model_patch(str(body["model_info"].get("id", "")), body)
        if method == "POST" and path == "/model/delete":
            model_id = str(body.get("id", ""))
            if model_id not in self._db:
                return _error(
                    400, f"{{'error': 'Model with id={model_id} not found in db'}}", "auth_error"
                )
            until = self._cooled_until.get(model_id, -1.0)
            if until > self.clock():
                self._cooled_names[self._db[model_id].model_name] = (model_id, until)
            del self._db[model_id]
            return httpx.Response(200, json={"message": f"Model: {model_id} deleted successfully"})
        if method == "GET" and path in ("/v2/model/info", "/model/info"):
            return httpx.Response(200, json={"data": self._info()})
        if method == "POST" and path == "/chat/completions":
            return self._chat(body)
        if path == "/credentials" and method == "POST" and self.refuse_credentials:
            return _error(
                self.refuse_credentials,
                "{'error': 'Failed to create credential. Check your server logs.'}",
                "internal_server_error",
            )
        if path == "/credentials" and method == "POST":
            name = str(body.get("credential_name", ""))
            key = str(dict(body.get("credential_values") or {}).get("api_key", ""))
            self._creds[name] = (_seal(self.salt_key, key), self.salt_key)
            return httpx.Response(
                200, json={"success": True, "message": "Credential created successfully"}
            )
        if path == "/credentials" and method == "GET" or path.startswith("/credentials/by_name/"):
            self.credential_reads += 1
            masked = [
                {"credential_name": n, "credential_values": {"api_key": f"{k[:2]}****{k[-2:]}"}}
                for n in self._creds
                if (k := self.credential(n)) is not None
            ]
            return httpx.Response(200, json={"success": True, "credentials": masked})
        if path.startswith("/credentials/") and method in ("PATCH", "DELETE"):
            name = path.removeprefix("/credentials/")
            if name not in self._creds:
                return _error(
                    404,
                    f"Credential not found. Got credential name: {name}",
                    "internal_server_error",
                )
            if method == "DELETE":
                del self._creds[name]
                return httpx.Response(
                    200, json={"success": True, "message": "Credential deleted successfully"}
                )
            key = str(dict(body.get("credential_values") or {}).get("api_key", ""))
            self._creds[name] = (_seal(self.salt_key, key), self.salt_key)
            return httpx.Response(
                200, json={"success": True, "message": "Credential updated successfully"}
            )
        return _error(404, "Not Found", "not_found_error")

    def _model_new(self, body: Mapping[str, Any]) -> httpx.Response:
        name = body.get("model_name")
        params = body.get("litellm_params")
        if not isinstance(name, str) or not isinstance(params, dict):
            return httpx.Response(
                500,
                json={
                    "error": {"message": "Internal server error", "type": "internal_server_error"}
                },
            )
        model_id = str(
            (body.get("model_info") or {}).get("id")
            or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        )
        if model_id in self._db:
            return _error(
                500,
                "{'error': 'Failed to add model to db. Check your server logs for more details.'}",
                "auth_error",
            )
        sealed = {k: _seal(self.salt_key, str(v)) for k, v in params.items() if v is not None}
        self._db[model_id] = _Stored(name, sealed, self.salt_key)
        return httpx.Response(
            200,
            json={
                "model_id": model_id,
                "model_name": name,
                "litellm_params": sealed,
                "model_info": {"id": model_id, "db_model": False},
            },
        )

    def _model_patch(self, model_id: str, body: Mapping[str, Any]) -> httpx.Response:
        stored = self._db.get(model_id)
        if stored is None or stored.salt != self.salt_key:
            return _error(404, f"Model {model_id} not found on proxy.", "not_found_error")
        for k, v in dict(body.get("litellm_params") or {}).items():
            if v is None:
                stored.sealed.pop(k, None)
            else:
                stored.sealed[k] = _seal(self.salt_key, str(v))
        if "model_name" in body:
            stored.model_name = str(body["model_name"])
        return httpx.Response(
            200,
            json={
                "model_id": model_id,
                "model_name": stored.model_name,
                "litellm_params": dict(stored.sealed),
            },
        )

    def _info(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = [
            {"model_name": m, "litellm_params": {"model": m}, "model_info": {"db_model": False}}
            for m in sorted(self.config_models)
        ]
        for model_id in sorted(self.stored_ids()):
            params = self.stored_params(model_id)
            params.pop("api_key", None)
            rows.append(
                {
                    "model_name": self._db[model_id].model_name,
                    "litellm_params": params,
                    "model_info": {"id": model_id, "db_model": True},
                }
            )
        return rows

    def _chat(self, body: Mapping[str, Any]) -> httpx.Response:
        model_name = str(body.get("model", ""))
        self.asked.append(model_name)
        if model_name in self.config_models:
            return _ok(model_name)
        ids = [i for i in self.stored_ids() if self._db[i].model_name == model_name]
        gone = self._cooled_names.get(model_name)
        if not ids and gone is not None and gone[1] > self.clock():
            return _error(
                429,
                "No deployments available for selected model, Try again in 5 seconds. Passed "
                f"model={model_name}. pre-call-checks=False, cooldown_list=['{gone[0]}']",
                "internal_server_error",
            )
        if not ids:
            message = (
                f"/chat/completions: Invalid model name passed in model={model_name}. Call "
                "`/v1/models` to view available models for your key."
            )
            return _error(400, message, "invalid_request_error")
        now = self.clock()
        live = [i for i in ids if self._cooled_until.get(i, -1.0) <= now]
        if not live:
            cooled = sorted(i for i, until in self._cooled_until.items() if until > now)
            return _error(
                429,
                "No deployments available for selected model, Try again in 5 seconds. Passed "
                f"model={model_name}. pre-call-checks=False, cooldown_list={cooled}",
                "internal_server_error",
            )
        model_id = live[0]
        params = self.stored_params(model_id)
        provider_model = params.get("model", "")
        provider_name, _, provider_side = provider_model.partition("/")
        provider = self.providers.get(provider_name)
        key = params.get("api_key")
        if "litellm_credential_name" in params:
            key = self.credential(params["litellm_credential_name"])
        group = f". Received Model Group={model_name}\nAvailable Model Group Fallbacks=None"
        self.sent.append((params.get("api_base"), key))
        if provider is None:
            return _error(
                500,
                "litellm.InternalServerError: Connection error." + group,
                "internal_server_error",
            )
        if not key:
            self._cool(model_id, now)
            return _error(
                500,
                "litellm.AuthenticationError: AuthenticationError: OpenAIException - The api_key "
                "client option must be set either by passing api_key to the client or by setting "
                "the OPENAI_API_KEY environment variable" + group,
                "internal_server_error",
            )
        if key != provider.accepted_key:
            self._cool(model_id, now)
            words = (
                "litellm.AuthenticationError: AuthenticationError: OpenAIException - Incorrect API "
                f"key provided: {_fragment(key)}." + group
            )
            self.log.append(words)
            return _error(401, words, "authentication_error")
        if provider_side not in provider.offered_models:
            self._cool(model_id, now)
            return _error(
                404,
                f"litellm.NotFoundError: OpenAIException - The model `{provider_side}` does not "
                "exist" + group,
                "invalid_request_error",
            )
        return _ok(model_name)

    def _cool(self, model_id: str, now: float) -> None:
        self._cooled_until[model_id] = now + self.cooldown_seconds


def _error(status: int, message: str, kind: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"message": message, "type": kind, "param": None, "code": str(status)}},
    )


def _ok(model_name: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "OK"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )
