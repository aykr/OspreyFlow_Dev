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

**Usage and limits** (ADR-135 Amendment 3), measured on 8 November 2026 under two platform leases on
stack a, against the same image (litellm 1.101.0):

- every call is recorded under each of its tags (the body's `tags` or `metadata.tags`, and two
  `User-Agent: …` tags the gateway adds itself) per day: calls, successes, failures, prompt and
  completion tokens; a call refused for an unknown model or an exhausted budget is a failure;
  `GET /tag/daily/activity?start_date&end_date` answers them under `breakdown.entities`, `400`
  without both dates, an empty list for an empty or reversed period, and `401` to any token but
  the master key ("Only proxy admin can be used…"); no prompt or answer text is kept;
- an `rpm`/`tpm` on a model entry is **not** enforced (the default routing reads it as a weight);
- a virtual key (`POST /key/generate`, a chosen `key` value allowed, its `key_alias` unique or
  400) holds `rpm_limit`, `tpm_limit`, `max_budget` and `budget_duration`, all enforced: a request
  once the minute's requests or tokens have reached the limit is refused 429 `throttling_error`
  naming **the key's SHA-256**; once the spend has reached the budget, 429 `budget_exceeded`
  naming the key's alias and **its last four characters**; the call that crosses a limit is
  answered. Spend is each token times the entry's `input_cost_per_token`/`output_cost_per_token`
  (none: 0). A `1d` budget resets at the next midnight UTC after the first spend; `30d` on the
  first of the next month;
- `GET /key/info?key=` (404 "Key not found in database"), `POST /key/update` (404 "Key not
  found."; its answer **carries the key**) and `POST /key/delete` (404 "No keys found"); a call
  with a deleted key is 401, echoing its last four characters and its hash.

Not measured, so not modelled as refusals and never relied on: whether a request refused by a
rate limit is recorded as a failure (the stand-in records it nowhere, and no test reads it);
`POST /credentials` for a name that exists, and `PATCH /credentials/{name}` or
`PATCH /model/{id}/update` at all. The Conduit's client asks neither: it removes a credential
before making it (`GatewayAdmin.put_credential`) and deletes an edited engine's entries before
making them again (`ModelAdmin._reconcile`).

The stand-in is an `httpx.MockTransport`, so the code under test sends real HTTP requests through
the same `httpx.AsyncClient` it uses against the real gateway. Its own red-then-green proof is
`tests/adapters/model_litellm/test_stand_in_gateway.py`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx


@dataclass
class StandInProvider:
    """What a hosted provider accepts: one key, and the models it offers to that key."""

    accepted_key: str
    offered_models: frozenset[str]
    #: The tokens it reports for each answer.
    prompt_tokens: int = 17
    completion_tokens: int = 5


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
class _VirtualKey:
    alias: str | None
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    max_budget: float | None = None
    budget_duration: str | None = None
    spend: float = 0.0
    budget_reset_at: float | None = None
    window_start: float = -1e18
    window_requests: int = 0
    window_tokens: int = 0


_FIGURES = ("api_requests", "successful_requests", "failed_requests", "prompt_tokens",
            "completion_tokens", "total_tokens")  # fmt: skip
_KEY_FIELDS = ("rpm_limit", "tpm_limit", "max_budget", "budget_duration")


def _day(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).date().isoformat()


def _next_reset(at: float, duration: str) -> float:
    """When a budget set for `duration` next resets (measured: `1d` the next midnight UTC, `30d`
    the first of the next month)."""
    now = datetime.fromtimestamp(at, UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if duration == "30d":
        first = midnight.replace(day=1)
        nxt = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(
            month=first.month + 1)  # fmt: skip
        return nxt.timestamp()
    return (midnight + timedelta(days=1)).timestamp()


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
    #: Every chat request body as it arrived, so a test can say what the Conduit sent (a person's
    #: id, a prompt) and with which token.
    received: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    #: Every request as it arrived (method, path with its query, body), whatever it asked.
    seen: list[str] = field(default_factory=list)
    #: What every answer says (an extraction's test sets JSON its schema accepts).
    answer: str = "OK"
    #: The rendered entries' own answers report these tokens.
    local_prompt_tokens: int = 17
    local_completion_tokens: int = 5
    _db: dict[str, _Stored] = field(default_factory=dict)
    _keys: dict[str, _VirtualKey] = field(default_factory=dict)
    #: (day, tag) -> each recorded figure.
    _daily: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)
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

    def virtual_key(self, key: str) -> _VirtualKey | None:
        return self._keys.get(key)

    def virtual_keys(self) -> dict[str, _VirtualKey]:
        return dict(self._keys)

    def record_usage(
        self, day: str, tag: str, *, calls: int, failed: int = 0, prompt: int = 0,
        completion: int = 0,
    ) -> None:  # fmt: skip
        """Plant a day's figures under a tag, as the gateway's own daily table holds them."""
        row = self._daily.setdefault((day, tag), dict.fromkeys(_FIGURES, 0))
        row["api_requests"] += calls
        row["successful_requests"] += calls - failed
        row["failed_requests"] += failed
        row["prompt_tokens"] += prompt
        row["completion_tokens"] += completion
        row["total_tokens"] += prompt + completion

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
        sent = request.content.decode("utf-8", "replace")
        self.seen.append(f"{request.method} {request.url.raw_path.decode()} {sent}")
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            return _error(401, "Authentication Error, No api key passed in.", "auth_error")
        path, method = request.url.path, request.method
        if token != self.master_key and token in self._keys:
            if method == "POST" and path == "/chat/completions":
                return self._chat(self._body(request), token, request)
            return _error(
                401,
                "Authentication Error, Only proxy admin can be used to generate, delete, update "
                f"info for new keys/users/teams. Route={path}. Your role=unknown.",
                "auth_error",
            )
        if token != self.master_key:
            return _error(
                401,
                "Authentication Error, Invalid proxy server token passed. Received API Key = "
                f"sk-...{token[-4:]}, Key Hash (Token) ={_hash(token)}. Unable to find token in "
                "cache or "
                "`LiteLLM_VerificationTokenTable`",
                "token_not_found_in_db",
            )
        body = self._body(request)
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
            return self._chat(body, None, request)
        if method == "GET" and path == "/tag/daily/activity":
            return self._tag_activity(parse_qs(request.url.query.decode()))
        if path.startswith("/key/"):
            return self._key_admin(method, path, body, parse_qs(request.url.query.decode()))
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

    @staticmethod
    def _body(request: httpx.Request) -> dict[str, Any]:
        return json.loads(request.content or b"{}") if request.content else {}

    def _chat(
        self, body: Mapping[str, Any], virtual: str | None, request: httpx.Request
    ) -> httpx.Response:
        self.received.append((virtual or "master", dict(body)))
        tags = _tags(body, request)
        refused = self._limited(virtual, tags)
        if refused is not None:
            return refused
        answer = self._answer(body)
        if answer.status_code == 200:
            usage = json.loads(answer.content)["usage"]
            self._record(tags, ok=True, prompt=usage["prompt_tokens"],
                         completion=usage["completion_tokens"])  # fmt: skip
            if virtual is not None:
                self._spend(virtual, str(body.get("model", "")), usage)
        elif answer.status_code != 429:
            self._record(tags, ok=False)
        return answer

    def _limited(self, virtual: str | None, tags: list[str]) -> httpx.Response | None:
        """A virtual key's limits, checked before the call (measured: the call that crosses a limit
        is answered, the next refused)."""
        if virtual is None:
            return None
        held = self._keys[virtual]
        now = self.clock()
        if held.budget_reset_at is not None and now >= held.budget_reset_at:
            held.spend = 0.0
            held.budget_reset_at = None
        if held.max_budget is not None and held.spend >= held.max_budget:
            self._record(tags, ok=False)
            return _error(
                429,
                f"Budget has been exceeded! Key={held.alias} (sk-...{virtual[-4:]}) Current cost: "
                f"{held.spend}, Max budget: {held.max_budget}",
                "budget_exceeded",
            )
        if now >= held.window_start + 60:
            held.window_start, held.window_requests, held.window_tokens = now, 0, 0
        resets = datetime.fromtimestamp(held.window_start + 60, UTC).strftime("%Y-%m-%d %H:%M:%S")
        for kind, limit, used in (("requests", held.rpm_limit, held.window_requests),
                                  ("tokens", held.tpm_limit, held.window_tokens)):  # fmt: skip
            if limit is not None and used >= limit:
                return _error(
                    429,
                    f"Rate limit exceeded for api_key: {_hash(virtual)}. Limit type: {kind}. "
                    f"Current limit: {limit}, Remaining: 0. Limit resets at: {resets} UTC",
                    "throttling_error",
                )
        held.window_requests += 1
        return None

    def _spend(self, virtual: str, model_name: str, usage: Mapping[str, int]) -> None:
        held = self._keys[virtual]
        held.window_tokens += int(usage["total_tokens"])
        ids = [i for i in self.stored_ids() if self._db[i].model_name == model_name]
        params = self.stored_params(ids[0]) if ids else {}
        cost = usage["prompt_tokens"] * float(params.get("input_cost_per_token", 0) or 0) + usage[
            "completion_tokens"] * float(params.get("output_cost_per_token", 0) or 0)  # fmt: skip
        held.spend += cost
        if held.budget_duration and held.budget_reset_at is None:
            held.budget_reset_at = _next_reset(self.clock(), held.budget_duration)

    def _record(self, tags: list[str], *, ok: bool, prompt: int = 0, completion: int = 0) -> None:
        day = _day(self.clock())
        for tag in tags:
            self.record_usage(day, tag, calls=1, failed=0 if ok else 1, prompt=prompt,
                              completion=completion)  # fmt: skip

    def _tag_activity(self, query: Mapping[str, list[str]]) -> httpx.Response:
        start = (query.get("start_date") or [""])[0]
        end = (query.get("end_date") or [""])[0]
        if not start or not end:
            return httpx.Response(
                400, json={"detail": {"error": "Please provide start_date and end_date"}}
            )
        wanted = set(query.get("tags") or [])
        days: dict[str, dict[str, dict[str, int]]] = {}
        for (day, tag), figures in sorted(self._daily.items()):
            if start <= day <= end and (not wanted or tag in wanted):
                days.setdefault(day, {})[tag] = dict(figures)
        results = []
        for day, entities in days.items():
            total = {f: sum(e[f] for e in entities.values()) for f in _FIGURES}
            results.append({
                "date": day,
                "metrics": {"spend": 0.0, **total},
                "breakdown": {
                    "entities": {t: {"metrics": {"spend": 0.0, **e}, "metadata": {}}
                                 for t, e in entities.items()},
                    "models": {}, "model_groups": {}, "providers": {}, "api_keys": {},
                },
            })  # fmt: skip
        return httpx.Response(
            200,
            json={"results": results,
                  "metadata": {"page": 1, "total_pages": 1 if results else 0, "has_more": False}},
        )  # fmt: skip

    def _key_admin(
        self, method: str, path: str, body: Mapping[str, Any], query: Mapping[str, list[str]]
    ) -> httpx.Response:
        if method == "GET" and path == "/key/info":
            key = (query.get("key") or [""])[0]
            held = self._keys.get(key)
            if held is None:
                return _error(404, "Key not found in database", "not_found_error")
            info = {"key_alias": held.alias, "spend": held.spend,
                    "budget_reset_at": None if held.budget_reset_at is None
                    else datetime.fromtimestamp(held.budget_reset_at, UTC).isoformat(),
                    **{f: getattr(held, f) for f in _KEY_FIELDS}}  # fmt: skip
            return httpx.Response(200, json={"key": key, "info": info})
        if method == "POST" and path == "/key/generate":
            alias = body.get("key_alias")
            if alias is not None and any(k.alias == alias for k in self._keys.values()):
                return _error(
                    400,
                    f"Key with alias '{alias}' already exists. Unique key aliases across all keys "
                    "are required.",
                    "bad_request_error",
                )
            key = str(body.get("key") or f"sk-{secrets.token_urlsafe(16)}")
            self._keys[key] = _VirtualKey(alias=alias)
            for f in _KEY_FIELDS:
                setattr(self._keys[key], f, body.get(f))
            return httpx.Response(200, json={"key": key, "key_alias": alias, "spend": 0.0})
        if method == "POST" and path == "/key/update":
            key = str(body.get("key", ""))
            held = self._keys.get(key)
            if held is None:
                return _error(404, "Key not found.", "not_found_error")
            for f in _KEY_FIELDS:
                if f in body:
                    setattr(held, f, body[f])
            return httpx.Response(200, json={"key": key, "token": _hash(key), "spend": held.spend})
        if method == "POST" and path == "/key/delete":
            keys = [str(k) for k in body.get("keys") or []]
            if not keys or any(k not in self._keys for k in keys):
                return _error(404, "{'error': 'No keys found'}", "internal_server_error")
            for k in keys:
                del self._keys[k]
            return httpx.Response(200, json={"deleted_keys": keys})
        return _error(404, "Not Found", "not_found_error")

    def _answer(self, body: Mapping[str, Any]) -> httpx.Response:
        model_name = str(body.get("model", ""))
        self.asked.append(model_name)
        if model_name in self.config_models:
            return _ok(
                model_name, self.local_prompt_tokens, self.local_completion_tokens, self.answer
            )
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
        return _ok(model_name, provider.prompt_tokens, provider.completion_tokens, self.answer)

    def _cool(self, model_id: str, now: float) -> None:
        self._cooled_until[model_id] = now + self.cooldown_seconds


def _error(status: int, message: str, kind: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"message": message, "type": kind, "param": None, "code": str(status)}},
    )


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _tags(body: Mapping[str, Any], request: httpx.Request) -> list[str]:
    """A call's tags as the gateway records them: the body's, then the two it adds from the
    request's `User-Agent` (measured)."""
    named = list(body.get("tags") or dict(body.get("metadata") or {}).get("tags") or [])
    agent = request.headers.get("user-agent", "")
    if agent:
        named += [f"User-Agent: {agent.split('/')[0]}", f"User-Agent: {agent}"]
    return [str(t) for t in named]


def _ok(
    model_name: str, prompt: int = 1, completion: int = 1, answer: str = "OK"
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": f"chatcmpl-{secrets.token_hex(8)}",
            "object": "chat.completion",
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": answer},
                }
            ],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
        },
    )
