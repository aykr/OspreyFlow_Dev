"""SE8c: sign-ins are recorded by the product, with no change to any identity provider's
configuration (`RULINGS.md` SE8; `03_CONDUIT_MIDDLEWARE.md` §6; rules 3, 4, 12 and 15).

The owner's ruling of 21 November 2026: the page service records its sign-in callback and sign-out,
and the Conduit records the first time it sees a new session. An organisation's own sign-in service
cannot be reconfigured by the product, so nothing here depends on one. Refused sign-in attempts stay
in the identity provider's own log: nothing here records them (the page service's side is
`apps/pages/test/server/sign-in-events.test.ts`).

**What is proved, each through the real thing.** Every case runs the real app's routes, the real
`PrincipalResolver` over a real RS256 key and a real JWKS served over loopback HTTP, the real
`AuditWriter` over a pool that captures every column it inserts, and the real `SignInWatch` over a
stand-in for Valkey that REFUSES what Valkey refuses (rule 15, second worked example): a `SET` with
an expiry that is not a positive whole number, an `INCR` of a value that is not a number, a store
that is down, one that never answers. Tokens, cookies, codes, states, client secrets, passwords and
provider addresses are synthetic and made when the test runs.

1. **The Conduit records a session the first time it sees one**: one `sign_in_seen` row; none for
   the same session again, nor for the same session with a renewed token, nor on another replica or
   after a replica's restart (the memory is Valkey's, not the process's); one more for another
   session or person.
2. **The session is identified without recording the token**: a keyed reference (HMAC-SHA-256 under
   a per-deployment secret that lives in Valkey, never in a row) of the person and the token's
   `sid` (else `auth_time`, else `iat`); the row carries the reference, the basis it was made from
   and the channel (the token's `azp`), nothing else.
3. **A refused or unknown token writes nothing and says nothing new**: the answer is byte for byte
   the one a Conduit without the watch gives, and Valkey and the audit store are not asked.
4. **A store fault never locks anyone out**: Valkey down, slow or refusing, or the audit store
   down, and the request is answered; the miss is counted and logged without the token; a row not
   written is written at the next request once the store is back.
5. **`POST /v1/session-events`** (`sign_in` / `sign_out`): authenticated by the person's own token,
   so it records for that token's person and no other; refused without a token, with an expired or
   foreign token, and with the page service's own client credential alone; a closed list of two
   kinds and no free text; idempotent for one session; rate-limited; fails closed (503) when the
   audit store is down, as every audit write does, with the retry still recorded once.
6. **A record never carries** a token or any part of one, a cookie, a code, a state, a client
   secret, a password, an address of the provider, the session's own `sid` or the deployment
   secret: planted in every place a caller controls and looked for in every audit column and every
   log line of each path.
7. **Rule 12**: the same assertions fail for a Conduit that stops writing the first-seen row, and
   for a route that stops writing its row (planted at the call each is made from).
8. **No identity provider configuration changes** (item 5 of the brief): `touched_provider_settings`
   reads the changed file list from `git diff` against the merge-base with `main` (plus the working
   tree and untracked files) and fails on `harness/realm.py`, `harness/keycloak_admin.py`,
   `harness/keycloak_theme.py`, `tools/idp_test_realm.py` and any `realm*.json|yaml` export; it is
   shown red on a scratch repository.

**Folders walked.** `OspreyFlow_Core/services/api/app.py` (read as a syntax tree: the one gate every
authenticated request passes calls the watch; the route is registered and writes through it);
`OspreyFlow_Core/services/api/audit_section.py` (classification, through its own functions); the
repository's own `git diff` file list (item 8). Everything else is run, not read.

**Owed to a live stack** (not proved here; the live step is off): a real Valkey's own refusal of the
commands used (`SET ... NX EX`, `INCR`, `EXPIRE`, `GET`, `DEL`) and a real Postgres insert of the
three rows (the writer is the existing one).
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import re
import secrets
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import valkey.exceptions
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.audit import AuditWriter
from services.api.auth import PrincipalResolver

from tests.conftest import default_claims, sign_token
from tests.services.api.test_auth import _config

REPO = Path(__file__).resolve().parents[4]
CORE = REPO / "OspreyFlow_Core"
ROUTE = "/v1/session-events"
CLIENT = "osprey-pages"

AUDIT_COLUMNS = (
    "recorded_at",
    "principal_id",
    "action",
    "investigation_id",
    "resolved_query",
    "result_cardinality",
    "justification",
    "org_unit",
)


# --- the stand-in for Valkey: it refuses what Valkey refuses (rule 15)
# -------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeValkey:
    """The commands `SignInWatch` uses, as the real client takes and answers them: bytes back, an
    expiry that must be a positive whole number, `INCR` that refuses a value that is not a number,
    `EXPIRE` of a key that is not there answering 0. `down` fails every call as a refused connection
    does; `hang` never answers."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.data: dict[str, tuple[bytes, float | None]] = {}
        self.down = False
        self.hang = False
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def _enter(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if self.hang:
            await asyncio.sleep(3600)
        if self.down:
            raise valkey.exceptions.ConnectionError(
                "Error 111 connecting to the store. Connection refused."
            )
        for key, (_, expires) in list(self.data.items()):
            if expires is not None and expires <= self.clock():
                del self.data[key]

    @staticmethod
    def _key(key: Any) -> str:
        if not isinstance(key, str | bytes) or not key:
            raise valkey.exceptions.DataError(
                "Invalid input of type: a key must be a non-empty string or bytes"
            )
        return key.decode() if isinstance(key, bytes) else key

    @staticmethod
    def _value(value: Any) -> bytes:
        if isinstance(value, bool) or not isinstance(value, str | bytes | int | float):
            raise valkey.exceptions.DataError(f"Invalid input of type: {type(value).__name__!r}")
        return value if isinstance(value, bytes) else str(value).encode()

    def _expiry(self, ex: Any) -> float | None:
        if ex is None:
            return None
        if isinstance(ex, bool) or not isinstance(ex, int) or ex <= 0:
            raise valkey.exceptions.ResponseError("invalid expire time in 'set' command")
        return self.clock() + ex

    async def set(self, key: Any, value: Any, ex: Any = None, nx: bool = False) -> bool | None:
        await self._enter("set", key, ex, nx)
        name, stored, expires = self._key(key), self._value(value), self._expiry(ex)
        if nx and name in self.data:
            return None
        self.data[name] = (stored, expires)
        return True

    async def get(self, key: Any) -> bytes | None:
        await self._enter("get", key)
        held = self.data.get(self._key(key))
        return None if held is None else held[0]

    async def delete(self, *keys: Any) -> int:
        await self._enter("delete", *keys)
        return sum(1 for k in keys if self.data.pop(self._key(k), None) is not None)

    async def incr(self, key: Any) -> int:
        await self._enter("incr", key)
        name = self._key(key)
        held = self.data.get(name)
        if held is not None and not re.fullmatch(rb"-?\d+", held[0]):
            raise valkey.exceptions.ResponseError("value is not an integer or out of range")
        count = (int(held[0]) if held else 0) + 1
        self.data[name] = (str(count).encode(), held[1] if held else None)
        return count

    async def expire(self, key: Any, seconds: Any) -> bool:
        await self._enter("expire", key, seconds)
        name = self._key(key)
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise valkey.exceptions.ResponseError("invalid expire time in 'expire' command")
        if name not in self.data:
            return False
        self.data[name] = (self.data[name][0], self.clock() + seconds)
        return True

    def ttl_of(self, prefix: str) -> list[float]:
        return [
            expires - self.clock()
            for key, (_, expires) in self.data.items()
            if key.startswith(prefix) and expires is not None
        ]

    def salt(self) -> bytes | None:
        """The deployment secret, wherever the product keeps it: any value held with no expiry."""
        held = [v for v, expires in self.data.values() if expires is None and len(v) >= 16]
        return held[0] if held else None


# --- the stand-in for the audit store: every column the real writer inserts
# --------------------------


class _Conn:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def execute(self, sql: str, *args: Any) -> None:
        assert sql.lstrip().startswith("INSERT INTO audit_log"), sql
        if self._pool.down:
            raise OSError("the audit store is down")
        self._pool.rows.append(dict(zip(AUDIT_COLUMNS, args, strict=True)))


class Pool:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.down = False

    @asynccontextmanager
    async def acquire(self) -> Any:
        yield _Conn(self)

    def of(self, action: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["action"] == action]


def events(rig: Rig) -> list[dict[str, Any]]:
    """The rows the route writes (`sign_in`, `sign_out`): a valid token on a refused body still
    writes the first-seen row, which is the Conduit seeing a session and not this route's doing."""
    return [r for r in rig.pool.rows if r["action"] in ("sign_in", "sign_out")]


def detail(row: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(row["resolved_query"])
    assert isinstance(out, dict)
    return out


# --- the rig: the real app, resolver and writer, a watch over the stand-ins
# --------------------------


class Session:
    """One sign-in at the identity provider: a stable `sid`, and a token minted afresh each time."""

    def __init__(self, rig: Rig, person: str, **claims: Any) -> None:
        self.rig, self.person = rig, person
        self.claims = {"sid": secrets.token_hex(16), **claims}

    def token(self, **over: Any) -> str:
        claims = default_claims(
            sub=self.person,
            azp=CLIENT,
            jti=secrets.token_hex(16),
            iss=self.rig.provider,
            **{**self.claims, **over},
        )
        claims = {k: v for k, v in claims.items() if v is not None}
        return sign_token(self.rig.private, claims)

    @property
    def sid(self) -> str:
        return str(self.claims["sid"])


class Rig:
    def __init__(
        self, keypair: Any, jwks_url: str, mod: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.mod = mod
        self.private = keypair[0]
        self.clock = Clock()
        self.provider = (
            f"https://idp-{secrets.token_hex(6)}.example.test/realms/{secrets.token_hex(4)}"
        )
        self.pool = Pool()
        self.valkey = FakeValkey(self.clock)
        self.audit = AuditWriter(self.pool)  # type: ignore[arg-type]
        self.resolver = PrincipalResolver(_config(jwks_url))
        self.watch = self.replica()
        monkeypatch.setattr(app.state, "principal_resolver", self.resolver, raising=False)
        monkeypatch.setattr(app.state, "audit", self.audit, raising=False)
        monkeypatch.setattr(app.state, "sign_in_watch", self.watch, raising=False)
        self.http = TestClient(app, raise_server_exceptions=False)

    def replica(self, **kw: Any) -> Any:
        """Another Conduit process over the same Valkey and the same audit store."""
        return self.mod.SignInWatch(self.valkey, self.audit, clock=self.clock, **kw)

    def use(self, watch: Any) -> None:
        app.state.sign_in_watch = watch

    def session(self, person: str = "analyst-1", **claims: Any) -> Session:
        return Session(self, person, **claims)

    def me(self, token: str | None, **headers: str) -> Any:
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self.http.get("/v1/me", headers=headers)

    def event(self, token: str | None, kind: Any = "sign_in", **extra: Any) -> Any:
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        return self.http.post(ROUTE, json={"kind": kind, **extra}, headers=headers)


@pytest.fixture
def mod() -> Any:
    from services.api import sign_in_events

    return sign_in_events


@pytest.fixture
def rig(
    keypair: Any,
    jwks_url: str,
    mod: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> Rig:
    caplog.set_level(logging.DEBUG)
    return Rig(keypair, jwks_url, mod, monkeypatch)


def logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(f"{r.getMessage()}\n{r.exc_text or ''}\n{r.args}" for r in caplog.records)


# --- what must never be in a record
# ------------------------------------------------------------------


def synthetic() -> dict[str, str]:
    """Made now, written nowhere: one value for each thing a record must never carry."""
    return {
        "cookie": secrets.token_urlsafe(32),
        "code": secrets.token_urlsafe(24),
        "state": secrets.token_urlsafe(24),
        "client secret": secrets.token_urlsafe(32),
        "password": f"Pw-{secrets.token_urlsafe(18)}",
    }


def forbidden(
    token: str, rig: Rig, session: Session | None, extra: dict[str, str]
) -> dict[str, str]:
    """Every value that must be in no audit column and no log line: the token, each part of it, the
    synthetic values, the provider's address, the session's own `sid`, the deployment secret."""
    out = dict(extra)
    out["the token"] = token
    for i, part in enumerate(token.split(".")):
        out[f"token part {i}"] = part
    out["the provider's address"] = rig.provider
    out["the provider's host"] = rig.provider.split("/")[2]
    if session is not None:
        out["the sid"] = session.sid
    salt = rig.valkey.salt()
    if salt is not None:
        out["the deployment secret"] = salt.decode(errors="replace")
    return out


def leaks(rig: Rig, caplog: pytest.LogCaptureFixture, values: dict[str, str]) -> list[str]:
    found = []
    text_of_log = logged(caplog)
    for name, value in values.items():
        for row in rig.pool.rows:
            if any(value in str(v) for v in row.values()):
                found.append(f"{name} in a {row['action']} row")
        if value in text_of_log:
            found.append(f"{name} in a log line")
    return found


def callers_headers(extra: dict[str, str]) -> dict[str, str]:
    """Where a caller can put things: a cookie, a header of its own, the client's Basic
    credential."""
    return {
        "Cookie": f"osprey_pages={extra['cookie']}",
        "X-State": extra["state"],
        "X-Password": extra["password"],
        "X-Client-Secret": extra["client secret"],
    }


# --- 1 and 2: the Conduit records a session the first time it sees one
# ---------------------------------


def first_seen_is_recorded(rig: Rig) -> None:
    """The assertions of the first-seen row, kept as one function so a planted fault can be run
    against them."""
    s = rig.session()
    assert rig.me(s.token()).status_code == 200
    seen = rig.pool.of("sign_in_seen")
    assert len(seen) == 1, rig.pool.rows
    row = seen[0]
    assert row["principal_id"] == "analyst-1" and row["org_unit"] == "unit-1"
    assert (
        row["investigation_id"] is None
        and row["justification"] is None
        and row["result_cardinality"] == 1
    )


def test_the_first_request_of_a_new_session_writes_one_sign_in_seen_row(rig: Rig) -> None:
    first_seen_is_recorded(rig)


def test_the_row_carries_the_session_reference_the_basis_and_the_channel_and_nothing_else(
    rig: Rig,
) -> None:
    s = rig.session()
    rig.me(s.token())
    assert set(detail(rig.pool.of("sign_in_seen")[0])) == {"session", "basis", "channel"}
    d = detail(rig.pool.of("sign_in_seen")[0])
    assert (
        re.fullmatch(r"[0-9a-f]{32}", d["session"])
        and d["basis"] == "sid"
        and d["channel"] == CLIENT
    )


def test_the_same_session_again_writes_nothing_more(rig: Rig) -> None:
    s = rig.session()
    for _ in range(3):
        rig.me(s.token(iat=int(time.time())))
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_a_renewed_token_of_the_same_session_is_not_a_new_session(rig: Rig) -> None:
    """The identity provider renews a token every few minutes: a new `jti`, `iat` and `exp`, the
    same `sid`."""
    s = rig.session()
    rig.me(s.token())
    rig.me(s.token(iat=int(time.time()) + 1, exp=int(time.time()) + 900))
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_another_session_or_another_person_is_recorded_once_each(rig: Rig) -> None:
    a, a2, b = rig.session("analyst-1"), rig.session("analyst-1"), rig.session("analyst-2")
    for s in (a, a2, b, a, a2, b):
        rig.me(s.token())
    seen = rig.pool.of("sign_in_seen")
    assert sorted(r["principal_id"] for r in seen) == ["analyst-1", "analyst-1", "analyst-2"]
    assert len({detail(r)["session"] for r in seen}) == 3


def test_the_same_sid_of_two_people_is_two_sessions(rig: Rig) -> None:
    one = rig.session("analyst-1")
    two = rig.session("analyst-2")
    two.claims["sid"] = one.sid
    rig.me(one.token())
    rig.me(two.token())
    assert len({detail(r)["session"] for r in rig.pool.of("sign_in_seen")}) == 2


def test_another_replica_and_a_restart_do_not_write_it_again(rig: Rig, mod: Any) -> None:
    """The memory is the shared store's, not the process's: a second Conduit, and a Conduit
    restarted
    (a fresh watch with nothing in process memory), both find the session already seen."""
    s = rig.session()
    rig.me(s.token())
    for _ in range(2):
        rig.use(rig.replica())
        rig.me(s.token())
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_the_session_is_remembered_for_at_least_the_tokens_life_and_never_for_ever(
    rig: Rig,
) -> None:
    s = rig.session()
    rig.me(s.token(exp=int(time.time()) + 600))
    ttls = rig.valkey.ttl_of("")
    assert ttls and all(600 - 5 <= t <= 24 * 3600 for t in ttls), ttls


@pytest.mark.parametrize("basis", ["sid", "auth_time", "iat"])
def test_the_session_is_told_from_the_sid_else_the_auth_time_else_the_issue_time(
    rig: Rig, basis: str
) -> None:
    claims: dict[str, Any] = {"sid": None, "auth_time": None}
    if basis == "sid":
        claims["sid"] = secrets.token_hex(16)
    if basis == "auth_time":
        claims["auth_time"] = int(time.time()) - 30
    s = rig.session(**claims)
    rig.me(s.token())
    assert detail(rig.pool.of("sign_in_seen")[0])["basis"] == basis
    # A renewed token: the first two bases are the same session; the third (the token is all there
    # is) is a new one.
    rig.me(s.token(iat=int(time.time()) + 5, exp=int(time.time()) + 900))
    assert len(rig.pool.of("sign_in_seen")) == (2 if basis == "iat" else 1)


def test_the_reference_is_keyed_by_a_secret_the_deployment_holds(
    keypair: Any, jwks_url: str, mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same person, the same issuer and the same `sid` in two deployments give two references,
    and the secret is in no row: a reference cannot be worked back to a `sid`, or matched to a
    token, by anyone who does not hold it (an unkeyed hash of the `sid` is the same in both and
    fails here; the issuer is held the same in both so that it cannot be what tells them apart)."""
    refs = []
    for _ in range(2):
        r = Rig(keypair, jwks_url, mod, monkeypatch)
        r.provider = "https://idp.example.test/realms/osprey"
        s = Session(r, "analyst-1", sid="fixed-sid-0001")
        r.me(s.token())
        refs.append(detail(r.pool.of("sign_in_seen")[0])["session"])
    assert refs[0] != refs[1]
    # And inside one deployment the same inputs give the same reference, whichever replica asks.
    again = Rig(keypair, jwks_url, mod, monkeypatch)
    again.provider = "https://idp.example.test/realms/osprey"
    first = Session(again, "analyst-1", sid="fixed-sid-0001")
    again.me(first.token())
    again.use(again.replica())
    again.event(first.token(), "sign_in")
    assert (
        detail(again.pool.of("sign_in")[0])["session"]
        == detail(again.pool.of("sign_in_seen")[0])["session"]
    )


def test_an_application_identity_admitted_to_named_routes_is_not_a_person_signing_in(
    rig: Rig,
) -> None:
    """A dashboard's app identity (Entra ID) is admitted to named routes alone: it is no person's
    sign-in, so its first sight writes nothing (it would write a row for every token it renews)."""
    from schemas.domain import Principal

    async def application(_: str) -> Principal:
        return Principal(
            id="dashboard-1", clearance="OFFICIAL", org_unit="unit-1", routes=["GET /v1/me"]
        )

    rig.resolver.resolve_principal = application  # type: ignore[method-assign]
    assert rig.me(rig.session().token()).status_code == 200
    assert rig.pool.rows == []


def test_the_deployment_secret_is_shared_by_replicas_and_survives_a_restart(rig: Rig) -> None:
    s = rig.session()
    rig.me(s.token())
    first = detail(rig.pool.of("sign_in_seen")[0])["session"]
    rig.use(rig.replica())
    rig.event(s.token(), "sign_in")
    assert detail(rig.pool.of("sign_in")[0])["session"] == first, (
        "one session, one reference, on any replica"
    )


# --- 3: a refused or unknown token writes nothing and says nothing new
# -------------------------------


SERVICE_TOKEN = "a token with no clearance (the page service's own client credential, as issued)"


def refused_tokens(rig: Rig) -> dict[str, str | None]:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    s = rig.session()
    return {
        "no token at all": None,
        "a token of another key": sign_token(
            other, default_claims(sub="analyst-1", sid=s.sid, azp=CLIENT, iss=rig.provider)
        ),
        "an expired token": s.token(iat=int(time.time()) - 3600, exp=int(time.time()) - 1800),
        SERVICE_TOKEN: sign_token(
            rig.private,
            {
                "sub": "service-account-osprey-pages",
                "azp": CLIENT,
                "preferred_username": "service-account-osprey-pages",
                "sid": s.sid,
                "iss": rig.provider,
                "iat": int(time.time()),
                "exp": int(time.time()) + 300,
            },
        ),
        "a token that is not a token": "not.a.token",
    }


def test_a_refused_token_writes_nothing_and_the_answer_is_the_one_there_was_before(
    rig: Rig, mod: Any
) -> None:
    for name, token in refused_tokens(rig).items():
        rig.use(None)
        before = rig.me(token)
        rig.use(rig.watch)
        calls = len(rig.valkey.calls)
        after = rig.me(token)
        assert after.status_code == before.status_code and after.content == before.content, name
        assert after.status_code in (401, 403), name
        assert rig.pool.rows == [] and len(rig.valkey.calls) == calls, (
            f"{name}: something was asked or written"
        )


def test_a_token_the_resolver_refuses_is_never_a_session_seen_even_for_a_known_sid(
    rig: Rig,
) -> None:
    s = rig.session()
    rig.me(s.token())
    rig.pool.rows.clear()
    assert (
        rig.me(s.token(iat=int(time.time()) - 3600, exp=int(time.time()) - 1800)).status_code == 401
    )
    assert rig.pool.rows == []


# --- 4: a store fault never locks anyone out
# ----------------------------------------------------------


def test_valkey_down_the_request_is_answered_the_miss_is_counted_and_logged_without_the_token(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    s = rig.session()
    token = s.token()
    rig.valkey.down = True
    answered = rig.me(token)
    assert answered.status_code == 200 and answered.json()["id"] == "analyst-1"
    assert rig.pool.rows == []
    assert rig.watch.misses == 1
    said = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and "sign" in r.getMessage().lower()
    ]
    assert said, "a loud line"
    assert leaks(rig, caplog, forbidden(token, rig, s, {})) == []
    # The store comes back: the session was never marked seen, so its row is written now, once.
    rig.valkey.down = False
    rig.me(token)
    rig.me(token)
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_valkey_that_never_answers_does_not_hold_the_request(
    keypair: Any, jwks_url: str, mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = Rig(keypair, jwks_url, mod, monkeypatch)
    quick = r.replica(store_timeout=0.05)
    r.use(quick)
    r.valkey.hang = True
    started = time.monotonic()
    assert r.me(r.session().token()).status_code == 200
    assert time.monotonic() - started < 3
    assert quick.misses == 1 and r.pool.rows == []


def test_valkey_refusing_a_command_is_a_miss_not_a_failed_request(rig: Rig) -> None:
    """The store answers an error to a command (a version that refuses it): still answered."""

    async def refuse(*_: Any, **__: Any) -> None:
        raise valkey.exceptions.ResponseError("ERR syntax error")

    rig.valkey.set = refuse  # type: ignore[method-assign]
    assert rig.me(rig.session().token()).status_code == 200
    assert rig.watch.misses >= 1


def test_the_audit_store_down_the_request_is_answered_and_the_row_is_written_once_it_is_back(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    s = rig.session()
    token = s.token()
    rig.pool.down = True
    assert rig.me(token).status_code == 200
    assert rig.watch.misses == 1 and rig.pool.rows == []
    assert leaks(rig, caplog, forbidden(token, rig, s, {})) == []
    rig.pool.down = False
    rig.me(token)
    rig.me(token)
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_without_a_watch_on_the_app_nothing_is_written_and_nothing_fails(rig: Rig) -> None:
    rig.use(None)
    assert rig.me(rig.session().token()).status_code == 200 and rig.pool.rows == []


# --- 5: the route
# ------------------------------------------------------------------------------------


def a_sign_in_event_is_recorded(rig: Rig) -> None:
    s = rig.session()
    answer = rig.event(s.token(), "sign_in")
    assert answer.status_code == 200 and answer.json() == {"recorded": True}
    rows = rig.pool.of("sign_in")
    assert len(rows) == 1, rig.pool.rows
    assert rows[0]["principal_id"] == "analyst-1" and rows[0]["org_unit"] == "unit-1"
    assert (
        set(detail(rows[0])) == {"session", "basis", "channel"}
        and detail(rows[0])["channel"] == CLIENT
    )


def test_the_page_service_reports_a_sign_in_and_a_sign_out(rig: Rig) -> None:
    a_sign_in_event_is_recorded(rig)
    s = rig.session()
    assert rig.event(s.token(), "sign_out").json() == {"recorded": True}
    assert len(rig.pool.of("sign_out")) == 1


def test_one_session_has_one_reference_in_all_three_rows(rig: Rig) -> None:
    s = rig.session()
    rig.event(s.token(), "sign_in")
    rig.me(s.token())
    rig.event(s.token(), "sign_out")
    refs = {detail(r)["session"] for r in rig.pool.rows}
    assert {r["action"] for r in rig.pool.rows} == {"sign_in", "sign_in_seen", "sign_out"} and len(
        refs
    ) == 1


def test_the_route_refuses_a_request_with_no_token(rig: Rig) -> None:
    answer = rig.event(None)
    assert answer.status_code == 401 and rig.pool.rows == []


def test_the_route_refuses_the_page_services_own_client_credential_alone(rig: Rig) -> None:
    """Its Basic credential with no person's token; its client-credentials token (no clearance)."""
    extra = synthetic()
    basic = rig.http.post(ROUTE, json={"kind": "sign_in"}, auth=(CLIENT, extra["client secret"]))
    assert basic.status_code in (401, 403)
    service = refused_tokens(rig)[SERVICE_TOKEN]
    assert rig.event(service).status_code == 401
    assert rig.pool.rows == []


def test_the_route_refuses_an_expired_token_and_a_token_of_another_key(rig: Rig) -> None:
    for name, token in refused_tokens(rig).items():
        if token is None:
            continue
        assert rig.event(token).status_code in (401, 403), name
    assert rig.pool.rows == []


def test_the_route_records_for_the_person_of_the_token_and_never_for_another(rig: Rig) -> None:
    alice, bob = rig.session("analyst-1"), rig.session("analyst-2")
    rig.event(bob.token(), "sign_in")
    assert [r["principal_id"] for r in rig.pool.rows] == ["analyst-2", "analyst-2"]
    assert "analyst-1" not in json.dumps(rig.pool.rows, default=str)
    rig.event(alice.token(), "sign_out")
    assert {(r["action"], r["principal_id"]) for r in events(rig)} == {
        ("sign_in", "analyst-2"),
        ("sign_out", "analyst-1"),
    }


@pytest.mark.parametrize(
    "field", ["principal_id", "principal", "sub", "user", "person", "id", "session", "channel"]
)
def test_a_caller_cannot_name_a_person_a_session_or_a_channel(rig: Rig, field: str) -> None:
    """The body is the event kind and nothing else: a field naming whose event it is, is refused,
    not ignored."""
    s = rig.session("analyst-2")
    answer = rig.event(s.token(), "sign_in", **{field: "analyst-1"})
    assert answer.status_code == 422 and events(rig) == []


@pytest.mark.parametrize(
    "kind",
    [
        "sign_in_seen",
        "login",
        "SIGN_IN",
        " sign_in",
        "sign_in ",
        "",
        None,
        1,
        ["sign_in"],
        {"a": 1},
    ],
)
def test_the_event_kind_is_a_closed_list_of_two(rig: Rig, kind: Any) -> None:
    assert rig.event(rig.session().token(), kind).status_code == 422 and events(rig) == []


def test_free_text_in_the_kind_is_stored_nowhere_and_logged_nowhere(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    text = f"note-{secrets.token_urlsafe(24)}"
    s = rig.session()
    for body in (
        {"kind": text},
        {"kind": "sign_in", "note": text},
        {"kind": "sign_in", "detail": {"x": text}},
    ):
        answer = rig.http.post(ROUTE, json=body, headers={"Authorization": f"Bearer {s.token()}"})
        assert answer.status_code == 422
    assert events(rig) == [] and leaks(rig, caplog, {"the caller's text": text}) == []


def test_the_route_takes_a_json_body_of_the_one_field_only(rig: Rig) -> None:
    s = rig.session()
    headers = {"Authorization": f"Bearer {s.token()}"}
    for content in ("kind=sign_in", "", "[]", '"sign_in"', "{"):
        assert rig.http.post(ROUTE, content=content, headers=headers).status_code == 422
    assert rig.http.post(ROUTE, headers=headers).status_code == 422
    assert events(rig) == []


def test_a_repeated_report_of_one_callback_records_it_once(rig: Rig) -> None:
    """What can really repeat is one report: the same callback's token sent twice. Idempotence is
    keyed on that token (as a keyed hash, in the store only), not on the identity provider's
    session."""
    s = rig.session()
    token = s.token()
    assert rig.event(token, "sign_in").json() == {"recorded": True}
    assert rig.event(token, "sign_in").json() == {"recorded": False}
    assert len(rig.pool.of("sign_in")) == 1
    out = s.token()
    assert rig.event(out, "sign_out").json() == {"recorded": True}
    assert rig.event(out, "sign_out").json() == {"recorded": False}
    assert len(rig.pool.of("sign_out")) == 1


def test_sign_in_sign_out_sign_in_again_records_every_one_of_them(rig: Rig) -> None:
    """The page service's sign-out ends its own session and not the identity provider's, so the
    next sign-in carries the same `sid` and a token of its own. Each callback and each sign-out
    is a row: the design over-records and never under-records."""
    s = rig.session()
    for _ in range(3):
        assert rig.event(s.token(), "sign_in").json() == {"recorded": True}
        assert rig.event(s.token(), "sign_out").json() == {"recorded": True}
    assert len(rig.pool.of("sign_in")) == 3 and len(rig.pool.of("sign_out")) == 3
    assert len({detail(r)["session"] for r in events(rig)}) == 1, (
        "one provider session keeps one reference in every row"
    )


def test_a_token_renewed_within_one_session_is_a_report_of_its_own(rig: Rig) -> None:
    """A different token is a different report, however it came about: nothing here guesses that
    it was a renewal."""
    s = rig.session()
    assert rig.event(s.token(), "sign_in").json() == {"recorded": True}
    renewed = s.token(iat=int(time.time()) + 3, exp=int(time.time()) + 900)
    assert rig.event(renewed, "sign_in").json() == {"recorded": True}
    assert len(rig.pool.of("sign_in")) == 2


def test_a_token_that_names_no_session_is_still_one_report_once(rig: Rig) -> None:
    s = rig.session(sid=None, auth_time=None, iat=None)
    token = s.token()
    assert rig.event(token, "sign_in").json() == {"recorded": True}
    assert rig.event(token, "sign_in").json() == {"recorded": False}
    assert rig.event(s.token(), "sign_in").json() == {"recorded": True}
    assert len(rig.pool.of("sign_in")) == 2


def test_a_report_is_remembered_no_longer_than_its_token_lives(rig: Rig) -> None:
    s = rig.session()
    assert rig.event(s.token(), "sign_in").json() == {"recorded": True}
    reported = rig.valkey.ttl_of("sign-in-events:sign_in:")
    assert len(reported) == 1 and 0 < reported[0] <= 300 + 60, reported


def test_the_route_is_rate_limited_per_person(rig: Rig, mod: Any) -> None:
    limit = mod.RATE_LIMIT_PER_MINUTE
    for _ in range(limit):
        assert rig.event(rig.session("analyst-1").token(), "sign_in").status_code == 200
    over = rig.event(rig.session("analyst-1").token(), "sign_in")
    assert over.status_code == 429 and len(rig.pool.of("sign_in")) == limit
    assert rig.event(rig.session("analyst-2").token(), "sign_in").status_code == 200, (
        "another person is unaffected"
    )
    rig.clock.advance(61)
    assert rig.event(rig.session("analyst-1").token(), "sign_in").status_code == 200


def test_the_route_fails_closed_when_the_audit_store_is_down_and_the_retry_records_once(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    s = rig.session()
    token = s.token()
    rig.pool.down = True
    answer = rig.event(token, "sign_in")
    assert answer.status_code == 503 and answer.json()["error"] == "audit_unavailable"
    assert rig.pool.rows == []
    rig.pool.down = False
    assert rig.event(token, "sign_in").json() == {"recorded": True}
    assert rig.event(token, "sign_in").json() == {"recorded": False}
    assert len(rig.pool.of("sign_in")) == 1


def test_the_route_records_even_when_valkey_is_down_a_duplicate_over_a_missing_row(
    rig: Rig,
) -> None:
    s = rig.session()
    rig.valkey.down = True
    assert rig.event(s.token(), "sign_in").status_code == 200
    assert len(rig.pool.of("sign_in")) == 1
    assert detail(events(rig)[0])["session"] is None, (
        "no secret to key the reference with: said so, not guessed"
    )


def test_a_session_event_route_is_registered_and_takes_one_method() -> None:
    routes = [r for r in app.routes if getattr(r, "path", "") == ROUTE]
    assert len(routes) == 1 and routes[0].methods == {"POST"}  # type: ignore[attr-defined]


# --- 6: a record never carries what must not be in it
# ------------------------------------------------


def exercise(rig: Rig, path: str, s: Session, token: str, extra: dict[str, str]) -> None:
    headers = callers_headers(extra)
    query = f"?code={extra['code']}&state={extra['state']}"
    if path == "first sight":
        rig.http.get("/v1/me" + query, headers={**headers, "Authorization": f"Bearer {token}"})
    elif path == "sign_in":
        rig.http.post(
            ROUTE + query,
            json={"kind": "sign_in"},
            headers={**headers, "Authorization": f"Bearer {token}"},
        )
    elif path == "sign_out":
        rig.http.post(
            ROUTE + query,
            json={"kind": "sign_out"},
            headers={**headers, "Authorization": f"Bearer {token}"},
        )
    elif path == "a body with free text":
        rig.http.post(
            ROUTE + query,
            json={"kind": "sign_in", "note": extra["password"], "code": extra["code"]},
            headers={**headers, "Authorization": f"Bearer {token}"},
        )
    elif path == "a refused token":
        rig.http.post(
            ROUTE + query,
            json={"kind": "sign_in"},
            headers={**headers, "Authorization": f"Bearer {token[:-4]}abcd"},
        )
    elif path == "a store down":
        rig.valkey.down = True
        rig.http.get("/v1/me" + query, headers={**headers, "Authorization": f"Bearer {token}"})
        rig.valkey.down = False
    elif path == "the audit store down":
        rig.pool.down = True
        rig.http.get("/v1/me" + query, headers={**headers, "Authorization": f"Bearer {token}"})
        rig.http.post(
            ROUTE + query,
            json={"kind": "sign_in"},
            headers={**headers, "Authorization": f"Bearer {token}"},
        )
        rig.pool.down = False


PATHS = [
    "first sight",
    "sign_in",
    "sign_out",
    "a body with free text",
    "a refused token",
    "a store down",
    "the audit store down",
]


@pytest.mark.parametrize("path", PATHS)
def test_no_record_and_no_log_line_carries_a_token_a_cookie_a_code_a_state_a_secret_or_an_address(
    rig: Rig, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    extra = synthetic()
    s = rig.session()
    token = s.token()
    exercise(rig, path, s, token, extra)
    if path in ("first sight", "sign_in", "sign_out"):
        assert rig.pool.rows, (
            f"{path}: the control, a row was written, so 'nothing in it' means something"
        )
    assert leaks(rig, caplog, forbidden(token, rig, s, extra)) == [], path


def test_the_scan_itself_finds_a_token_written_where_the_product_would_write_it(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """Planted at the shape the code writes: a token in an audit row's detail, and in a log line."""
    s = rig.session()
    token = s.token()
    rig.pool.rows.append(
        {"action": "sign_in", "resolved_query": json.dumps({"session": token.split(".")[1]})}
    )
    logging.getLogger("services.api.sign_in_events").warning("sign-in not recorded for %s", token)
    found = leaks(rig, caplog, forbidden(token, rig, s, {}))
    assert "token part 1 in a sign_in row" in found and "the token in a log line" in found


# --- 7: rule 12, the planted faults
# -------------------------------------------------------------------


def test_the_first_seen_assertions_fail_for_a_conduit_that_stops_writing_the_row(
    keypair: Any, jwks_url: str, mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forgets(self: Any, token: str, principal: Any) -> None:
        return None

    with monkeypatch.context() as m:
        m.setattr(mod.SignInWatch, "note_seen", forgets)
        r = Rig(keypair, jwks_url, mod, monkeypatch)
        with pytest.raises(AssertionError):
            first_seen_is_recorded(r)
    first_seen_is_recorded(Rig(keypair, jwks_url, mod, monkeypatch))


def test_the_route_assertions_fail_for_a_route_that_stops_writing_its_row(
    keypair: Any, jwks_url: str, mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forgets(self: Any, token: str, principal: Any, kind: str) -> bool:
        return True

    with monkeypatch.context() as m:
        m.setattr(mod.SignInWatch, "record_event", forgets)
        r = Rig(keypair, jwks_url, mod, monkeypatch)
        with pytest.raises(AssertionError):
            a_sign_in_event_is_recorded(r)
    a_sign_in_event_is_recorded(Rig(keypair, jwks_url, mod, monkeypatch))


def _function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    return next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)


def test_the_one_gate_every_authenticated_request_passes_calls_the_watch() -> None:
    """Read as a syntax tree: `get_principal` is what every route's principal comes through
    (`app.py`'s own docstring), and it must call `note_seen` after the resolver accepts the token,
    and only for a principal admitted to every route (a dashboard's app identity is no person's
    sign-in)."""
    tree = ast.parse((CORE / "services/api/app.py").read_text())
    gate = _function(tree, "get_principal")
    calls = [
        n
        for n in ast.walk(gate)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("resolve_principal", "note_seen")
    ]
    assert [c.func.attr for c in calls] == ["resolve_principal", "note_seen"]  # type: ignore[attr-defined]
    assert "routes is None" in ast.unparse(gate)


def test_the_session_events_route_is_the_one_that_writes_its_rows() -> None:
    tree = ast.parse((CORE / "services/api/app.py").read_text())
    handler = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
        and any(ROUTE in ast.unparse(d) for d in n.decorator_list)
    )
    assert "record_event" in ast.unparse(handler) and "PrincipalDep" in ast.unparse(handler)


def test_the_three_actions_are_classified_and_their_words_are_withheld() -> None:
    from services.api.audit_section import READS_AND_OTHER, kind_of, words_shown

    from schemas.rights import Right

    for action in ("sign_in_seen", "sign_in", "sign_out"):
        assert action in READS_AND_OTHER
        assert not words_shown(kind_of(action), frozenset(Right))


# --- 8: no identity provider configuration changes ---------------------------------------------

#: What configures an identity provider or a realm: the realm builder, the admin client, the login
#: theme, the test realm's builder; and any realm export (`REALM_EXPORT`).
PROVIDER_FILES = (
    "OspreyFlow_Core/harness/realm.py",
    "OspreyFlow_Core/harness/keycloak_admin.py",
    "OspreyFlow_Core/harness/keycloak_theme.py",
    "OspreyFlow_Build/tools/idp_test_realm.py",
)
REALM_EXPORT = re.compile(r"(^|/)[^/]*realm[^/]*\.(json|ya?ml)$", re.IGNORECASE)


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def changed_files(repo: Path, main: str) -> list[str]:
    """Every file this branch changes against `main`: committed since the merge-base, staged,
    edited, untracked."""
    base = _git(repo, "merge-base", "HEAD", main).strip()
    names = _git(repo, "diff", "--name-only", base).splitlines()
    names += _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(names))


def touched_provider_settings(paths: list[str]) -> list[str]:
    return [p for p in paths if p in PROVIDER_FILES or REALM_EXPORT.search(p)]


def _main_ref(repo: Path) -> str | None:
    for ref in ("main", "origin/main"):
        try:
            _git(repo, "rev-parse", "--verify", "--quiet", ref)
            return ref
        except RuntimeError:
            continue
    return None


def test_no_identity_provider_setting_is_changed_by_this_branch() -> None:
    main = _main_ref(REPO)
    if main is None:
        pytest.skip(
            "no `main` to compare with in this checkout (a shallow clone): the branch's run does"
        )
    assert touched_provider_settings(changed_files(REPO, main)) == []


def _scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    for rel in (*PROVIDER_FILES, "OspreyFlow_Core/services/api/app.py"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("original\n")
    for step in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-qm", "base"],
        ["checkout", "-q", "-b", "lane/x"],
    ):
        _git(repo, *step)
    return repo


@pytest.mark.parametrize("how", ["committed", "edited", "staged"])
@pytest.mark.parametrize("file", PROVIDER_FILES)
def test_the_provider_setting_check_is_red_for_each_way_a_file_can_change(
    tmp_path: Path, how: str, file: str
) -> None:
    """Planted in a scratch repository, at the shape the check reads: `git diff` against `main`."""
    repo = _scratch_repo(tmp_path)
    (repo / file).write_text("changed\n")
    if how in ("committed", "staged"):
        _git(repo, "add", "-A")
    if how == "committed":
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-qm", "x")
    assert touched_provider_settings(changed_files(repo, "main")) == [file]


@pytest.mark.parametrize(
    "name", ["realm-osprey.json", "osprey-realm.yaml", "realm_export.yml", "realm.json"]
)
def test_the_provider_setting_check_is_red_for_a_new_realm_export(
    tmp_path: Path, name: str
) -> None:
    repo = _scratch_repo(tmp_path)
    (repo / "OspreyFlow_Core/harness").joinpath(name).write_text("{}\n")
    assert touched_provider_settings(changed_files(repo, "main")) == [
        f"OspreyFlow_Core/harness/{name}"
    ]


def test_the_provider_setting_check_is_green_for_a_change_that_touches_none(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    (repo / "OspreyFlow_Core/services/api/app.py").write_text("changed\n")
    (repo / "OspreyFlow_Core/services/api/sign_in_events.py").write_text("new\n")
    assert changed_files(repo, "main") == [
        "OspreyFlow_Core/services/api/app.py",
        "OspreyFlow_Core/services/api/sign_in_events.py",
    ]
    assert touched_provider_settings(changed_files(repo, "main")) == []


def test_the_provider_files_named_here_exist_so_the_check_cannot_pass_for_a_renamed_one() -> None:
    for rel in PROVIDER_FILES:
        assert (REPO / rel).is_file(), f"{rel} has moved: name its new path in PROVIDER_FILES"
