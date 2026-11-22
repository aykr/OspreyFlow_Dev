"""Sign-ins are recorded by the product, with no change to any identity provider's configuration
(SE8c; `RULINGS.md` SE8: "sign-ins are recorded by the product, with no change to any identity
provider's configuration: the page service at its sign-in callback and sign-out, and the Conduit the
first time it sees a new session. An organisation's own sign-in service cannot be reconfigured by
the product, so the design must not depend on it. Refused sign-in attempts stay in the identity
provider's own log").

**Three rows, one audit stream** (`audit_log`, written by the one `AuditWriter`; classified in
`audit_section.READS_AND_OTHER`, words withheld):

- `sign_in_seen`: the first time this Conduit (or any replica) sees a session, written from
  `get_principal`, the one gate every authenticated request passes (`note_seen`);
- `sign_in` and `sign_out`: reported by the page service from its callback and its sign-out, to
  `POST /v1/session-events` (`record_event`), with the person's own token.

**How a session is identified without recording the token.** The row's `resolved_query` holds
`session`, `basis` and `channel` and nothing else. `session` is the first 128 bits of
HMAC-SHA-256, keyed by a per-deployment secret, over the person's id, the token's issuer and the
token's own session claim, in this order of preference: `sid` (the identity provider's session
id, which renewed tokens of one sign-in keep: Keycloak), else `auth_time` (when the person
authenticated: the same for every token renewed from that sign-in), else `iat` (the token's own
issue time: the token is all there is of a session, so a renewal is then read as a new one, which
over-records and never under-records). `basis` says which was used. `channel` is the client the
token was issued to (`azp`, or `appid` on Entra ID v1.0), kept only if it is a plain identifier: for
the page service's own sign-in it is the page service's own client. **Never recorded: the token or
any part of it, `sid`, `jti`, any claim's value, the issuer's address, the secret.** Why keyed: a
`sid` is a name the identity provider gives its session, and an unkeyed hash of a guessable
`auth_time` or `iat` could be matched against a token by anyone who read the table; keyed, a
reference cannot be worked back to a claim, or matched to a token, without the deployment's secret.

**Where the secret and "seen" are kept.** In Valkey, which every replica shares and which outlives
a Conduit's restart (the working set already depends on it): the secret under
`sign-in-events:secret` (`SET … NX`, so the first replica to ask makes it and the rest read it;
no expiry; read on every use and never held in a process, for Valkey has no persistence: when it is
wiped the first replica to ask makes a new one and every replica, whichever held the old one, keys
with it from its next request, so there is one reference for a session on every replica. The cost of
a wipe is one more row for each live session, as its "seen" keys go too, and never a lost one; a
request that read the old secret an instant before the wipe may write one row more) and each
session under `sign-in-events:seen:<reference>` (`SET … NX EX`, the atomic "first time": exactly one
replica wins) for the token's remaining life plus a minute, and for a `sid` or `auth_time` session
at least twelve hours (the session outlives its tokens), never more than a day. A small per-process
memory of references in front of it spares the "seen" write for every request of a session already
seen (the secret is still read, as above).

**When a store is unreachable: fail open for the request, loudly.** The owner's rule for audit
writes is fail closed, because an audit write there is the record of what the person is doing; the
first sight of a session is not the person's action, and turning a store fault into locking people
out is worse than a row late. So `note_seen` never raises: a Valkey that is down, slow (each call
is bounded by `store_timeout`), or refuses a command, and an audit store that is down, each leave
the request answered, count the miss (`SignInWatch.misses`) and write a warning (the first, then at
most one a minute, with the running count) that names the step and the kind of fault and never a
token, a claim or the store's own words. A session whose row could not be written is forgotten
again, so the next request writes it, whatever ended the write: the writer's own `AuditWriteError`,
but also what it does not wrap (a pool that is closing, a request cancelled in the middle).
`POST /v1/session-events` is the other half: its only purpose is the record, so it fails closed as
every audit write does (503 `audit_unavailable`, nothing recorded, the retry recorded once); with
Valkey down it still writes the row (a duplicate is better than a missing sign-in) with
`session: null`, there being no secret to key a reference with.

**The route.** Open to the page service's own client alone, **checked at the route** (SE8c round 8):
the token's own client claim (`azp`, `appid` on Entra ID v1.0) must name the page service's client
(`pages_client_for`, `from_page_service`), and every other token (the workspace's, Superset's, any
third client's, one that names none) is refused with one status and one body (403,
`SESSION_EVENT_REFUSED`) whatever the reason, before the body is read, the rate window is counted or
anything is written. The doors a request can come in by are not what refuses: the workspace's `/v1/`
proxy and the front proxy carry the route to the Conduit from a browser holding a workspace token
(the page service's own forwarder refuses the path as well, `forward.ts`, a second door shut and not
the defence). Authenticated by the person's own token (`get_principal`), so it records an
event for that token's person and no one else: the body is one field, `kind`, from a closed list of
two, and any other field is refused (422), so a caller cannot name a person, a session or a
channel. The page service's own client credential alone has no person in it and is refused as on
every other route. Idempotent for one report, not for one identity-provider session: the page
service's sign-out ends its own session and not the provider's, so a second sign-in (and sign-out)
of the same provider session carries the same `sid` and a token of its own, and is a row of its
own. What can really repeat is one report, so a keyed hash of the token as sent (kept in the store
for the token's remaining life and a minute, never the token or a part of it) answers a repeat of
that report `recorded: false`; the design over-records and never under-records. Rate-limited per
person (`RATE_LIMIT_PER_MINUTE`, a fixed window kept in Valkey: no other write route of the Conduit
has a limit, so this one is its own).

**Not recorded here: a refused sign-in.** A refusal never reaches the Conduit (the identity provider
refuses before there is a token), so it stays in the provider's own log. A token this Conduit's own
resolver refuses writes nothing and answers as it did before: `note_seen` runs only after the
resolver has accepted the token, so the row is no oracle for a token's validity.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

import jwt
from pydantic import BaseModel, ConfigDict

from conduit_common.valkey_compat import reply
from principal_auth import ClaimMapping
from schemas.domain import Principal

from .audit import AuditWriteError, AuditWriter

_log = logging.getLogger(__name__)

#: What the page service may report: a closed list, and nothing else.
EventKind = Literal["sign_in", "sign_out"]

#: Writes a person's sign-in events in one window: past it the route answers 429.
RATE_LIMIT_PER_MINUTE = 20
RATE_WINDOW_SECONDS = 60

#: How long a session with its own session claim is remembered at least: it outlives its tokens
#: (Keycloak's default SSO session maximum is ten hours), and never more than a day.
SESSION_MEMORY_SECONDS = 12 * 60 * 60
MAX_MEMORY_SECONDS = 24 * 60 * 60
#: A token's remaining life is kept a minute longer: the resolver's own leeway.
LEEWAY_SECONDS = 60

#: Seconds one call to Valkey may take before it counts as a miss: a store that never answers must
#: not hold a request.
STORE_TIMEOUT_SECONDS = 0.5
#: The most references one process remembers; past it the oldest go (Valkey still has them).
LOCAL_MEMORY = 20_000
#: At most one warning in this many seconds, with the running count of misses.
WARN_EVERY_SECONDS = 60

#: The page service's own client, as the page service itself names it
#: (`apps/pages/server/config.ts`, `OSPREY_PAGES_CLIENT_ID`; `harness/realm.py`'s
#: `PAGES_CLIENT_ID`): what the route is open to on Keycloak, where the resolver names no client.
PAGES_CLIENT_ENV = "OSPREY_PAGES_CLIENT_ID"
DEFAULT_PAGES_CLIENT = "osprey-pages"

#: What a token that is not the page service's is told, whatever the reason: one status and one
#: body, naming no claim, no client and no check.
SESSION_EVENT_REFUSED = "this route is not open to this sign-in"

_PREFIX = "sign-in-events:"
_SECRET_KEY = f"{_PREFIX}secret"
_CHANNEL = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_SID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


class SessionEvent(BaseModel):
    """The body of `POST /v1/session-events`: one kind, from the list, and no other field: a caller
    cannot say whose event it is, which session, or through which channel."""

    model_config = ConfigDict(extra="forbid")

    kind: EventKind


class SessionEventResponse(BaseModel):
    #: False for a session whose event of this kind was recorded already (a repeated callback).
    recorded: bool


def claims_of(token: str) -> dict[str, Any]:
    """A token's claims, read without checking its signature. **Only for a token the resolver has
    accepted just before**: it is how this module reads the session claim the resolver does not
    return, and decides nothing about whether a token is valid."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return {}
    return claims if isinstance(claims, dict) else {}


def pages_client_for(mapping: ClaimMapping, environ: Mapping[str, str] | None = None) -> str | None:
    """The client the page service signs a person in as, which is the only client whose token may
    report a sign-in or a sign-out; None where it cannot be known, and then no token is admitted.

    On Entra ID it is the mapping's own `pages_client_id` (an application id the resolver admits as
    the page service's, CO2) and never the environment's: one that is not set is no client. On
    Keycloak, where the resolver names no client, it is the page service's own
    `OSPREY_PAGES_CLIENT_ID` and else its default, `osprey-pages`
    (the realm's client, `harness/realm.py`)."""
    if mapping.is_entra:
        return mapping.pages_client_id
    named = (os.environ if environ is None else environ).get(PAGES_CLIENT_ENV, "").strip()
    return named or DEFAULT_PAGES_CLIENT


def from_page_service(claims: dict[str, Any], pages_client: str | None) -> bool:
    """Whether a token the resolver has accepted was issued to the page service's own client: the
    token's own client claim, `azp` (`appid` on Entra ID v1.0), as the resolver reads it for the
    Glass's, Superset's and the page service's registrations. Every one present must be that client,
    exactly and as a string: a token naming another client in either claim, or none, is not
    the page service's."""
    if not pages_client:
        return False
    named = [claims[c] for c in ("azp", "appid") if c in claims]
    return bool(named) and all(isinstance(c, str) and c == pages_client for c in named)


def _session_claim(claims: dict[str, Any]) -> tuple[str, str] | None:
    """(basis, the claim's value as text) of the session, or None for a token that names none."""
    sid = claims.get("sid")
    if isinstance(sid, str) and _SID.match(sid):
        return "sid", sid
    for basis in ("auth_time", "iat"):
        value = claims.get(basis)
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
            return basis, str(int(value))
    return None


def _channel(claims: dict[str, Any]) -> str:
    for name in ("azp", "appid"):
        value = claims.get(name)
        if isinstance(value, str) and _CHANNEL.match(value):
            return value
    return "unknown"


def _issuer(claims: dict[str, Any]) -> str:
    value = claims.get("iss")
    return value if isinstance(value, str) else ""


class SignInWatch:
    """The Conduit's half of the record of sign-ins. One per process, on `app.state.sign_in_watch`,
    over the Valkey and the audit writer every route already uses."""

    def __init__(
        self,
        valkey: Any,
        audit: AuditWriter,
        *,
        clock: Callable[[], float] = time.time,
        store_timeout: float = STORE_TIMEOUT_SECONDS,
    ) -> None:
        self._valkey = valkey
        self._audit = audit
        self._clock = clock
        self._store_timeout = store_timeout
        #: reference -> until when this process knows the session was seen.
        self._local: dict[str, float] = {}
        self._last_warning: float | None = None
        #: Times a record could not be made: a store fault, never a refusal.
        self.misses = 0
        #: Tokens that name no session at all (no `sid`, `auth_time` or `iat`): not recorded.
        self.unidentified = 0

    # --- the store ---------------------------------------------------------------------------

    async def _store(self, call: Awaitable[Any]) -> Any:
        return await asyncio.wait_for(reply(call), timeout=self._store_timeout)

    async def _deployment_secret(self) -> bytes:
        """The deployment's secret, read from Valkey on every use and never held in this process:
        Valkey keeps nothing across a restart of its container, and a replica that went on keying
        with a secret Valkey had lost would key a session differently from the replicas that made
        the new one (a row for each, and references that no longer tie a session's rows together).
        One `GET` in the steady state; only when the secret is missing is it made (`SET … NX`, so
        that of two replicas asking at once one wins and both read the winner's)."""
        held = await self._store(self._valkey.get(_SECRET_KEY))
        if not held:
            await self._store(self._valkey.set(_SECRET_KEY, secrets.token_hex(32), nx=True))
            held = await self._store(self._valkey.get(_SECRET_KEY))
            if not held:
                raise LookupError("the deployment's secret could not be had")
        return held if isinstance(held, bytes) else str(held).encode()

    def _reference(
        self, secret: bytes, principal: Principal, claims: dict[str, Any], session: tuple[str, str]
    ) -> str:
        basis, value = session
        message = b"\0".join(
            part.encode()
            for part in ("osprey-session-v1", principal.id, _issuer(claims), basis, value)
        )
        return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]

    def _ttl(self, claims: dict[str, Any], basis: str) -> int:
        exp = claims.get("exp")
        life = exp - self._clock() if isinstance(exp, int | float) else 0
        ttl = life + LEEWAY_SECONDS
        if basis in ("sid", "auth_time"):
            ttl = max(ttl, SESSION_MEMORY_SECONDS)
        return int(min(max(ttl, LEEWAY_SECONDS), MAX_MEMORY_SECONDS))

    def _remember(self, reference: str, seconds: int) -> None:
        now = self._clock()
        if len(self._local) >= LOCAL_MEMORY:
            self._local = {r: t for r, t in self._local.items() if t > now}
            if len(self._local) >= LOCAL_MEMORY:
                self._local.clear()
        self._local[reference] = now + seconds

    async def _forget(self, key: str, reference: str | None) -> None:
        """A row that could not be written: the session is not seen after all, so the next request
        writes it. Best effort: if the store is down too, its own expiry is the bound."""
        if reference is not None:
            self._local.pop(reference, None)
        try:
            await self._store(self._valkey.delete(key))
        except Exception:  # noqa: BLE001 - a store that failed once may fail again
            pass

    def _miss(self, step: str, exc: BaseException) -> None:
        """Counted always; said at most once a minute, naming the step and the kind of fault only
        (an exception's own words can hold an address, a claim or a token)."""
        self.misses += 1
        now = self._clock()
        if self._last_warning is None or now - self._last_warning >= WARN_EVERY_SECONDS:
            self._last_warning = now
            _log.warning(
                "sign-in record: could not %s (%s); %d such misses so far; no sign-in is blocked "
                "by it",
                step,
                type(exc).__name__,
                self.misses,
            )

    # --- the Conduit sees a session -------------------------------------------------------------

    async def note_seen(self, token: str, principal: Principal) -> None:
        """Writes one `sign_in_seen` row the first time a session is seen by any replica. Never
        raises: a store that cannot be asked, or an audit store that cannot be written, is a
        miss."""
        try:
            await self._note_seen(token, principal)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail open: a record's fault never locks anyone out
            self._miss("note a session", exc)

    async def _note_seen(self, token: str, principal: Principal) -> None:
        claims = claims_of(token)
        session = _session_claim(claims)
        if session is None:
            self.unidentified += 1
            return
        reference = self._reference(await self._deployment_secret(), principal, claims, session)
        if self._local.get(reference, 0) > self._clock():
            return
        ttl = self._ttl(claims, session[0])
        key = f"{_PREFIX}seen:{reference}"
        # What this call has done to the store, for the clean-up below: None while a `SET` is in
        # flight (it may have been made, whatever happens to its answer), then whether it won.
        won: bool | None = None
        try:
            first = await self._store(self._valkey.set(key, "1", nx=True, ex=ttl))
            self._remember(reference, ttl)
            if not first:
                won = False
                return
            won = True
            await self._audit.record(
                principal=principal,
                action="sign_in_seen",
                resolved_query={
                    "session": reference,
                    "basis": session[0],
                    "channel": _channel(claims),
                },
                result_cardinality=1,
            )
        except BaseException:
            # Whatever ended the write: `AuditWriteError`, but also what the writer does not wrap (a
            # pool that is closing, a request cancelled in the middle). A mark left behind says
            # "seen" for twelve hours with no row, on every replica: forget it, so the next request
            # writes the row. A mark that another replica made (`won` False) is not ours to clear.
            if won is not False:
                await self._forget(key, reference)
            raise

    # --- the page service reports ---------------------------------------------------------------

    async def allow(self, principal: Principal) -> bool:
        """Whether this person may write another event now: `RATE_LIMIT_PER_MINUTE` in a fixed
        window. The window's key is made with its expiry in one command (`SET NX EX`), then counted
        with `INCR`, which keeps the expiry: a process that dies between the two cannot leave a key
        that never ends. A store fault allows (the route's own write is the bound that matters)."""
        key = f"{_PREFIX}rate:{hashlib.sha256(principal.id.encode()).hexdigest()[:32]}"
        try:
            await self._store(self._valkey.set(key, 0, nx=True, ex=RATE_WINDOW_SECONDS))
            count = await self._store(self._valkey.incr(key))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail open
            self._miss("count a person's events", exc)
            return True
        return bool(count <= RATE_LIMIT_PER_MINUTE)

    def _report(self, secret: bytes, kind: EventKind, token: str) -> str:
        """What one report is: the token it was sent with, as a keyed hash (the token itself and any
        part of it stay out of the store). A callback's token cannot be sent again by the page
        service, which never retries, so only one report can repeat; a later sign-in in the same
        identity-provider session carries a token of its own and is a report of its own."""
        message = b"\0".join(part.encode() for part in ("osprey-report-v1", kind, token))
        return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]

    def _report_ttl(self, claims: dict[str, Any]) -> int:
        """A report is remembered as long as its token could still be accepted: its remaining life
        and the resolver's leeway, and never the session's twelve hours."""
        exp = claims.get("exp")
        life = exp - self._clock() if isinstance(exp, int | float) else 0
        return int(min(max(life + LEEWAY_SECONDS, LEEWAY_SECONDS), MAX_MEMORY_SECONDS))

    async def record_event(self, token: str, principal: Principal, kind: EventKind) -> bool:
        """Writes the `sign_in` or `sign_out` row for the person of `token` and no one else; False
        only for a repeat of the same report (the same token, the same kind). Every sign-in and
        every sign-out of the page service is a row, whatever the identity provider's session: the
        row's `session` reference ties it to the Conduit's other rows for that session. Raises
        `AuditWriteError` when the row cannot be written (the route's 503), with the report
        released so that a retry records it."""
        claims = claims_of(token)
        session = _session_claim(claims)
        reference: str | None = None
        key: str | None = None
        try:
            secret = await self._deployment_secret()
            if session is not None:
                reference = self._reference(secret, principal, claims, session)
            key = f"{_PREFIX}{kind}:{self._report(secret, kind, token)}"
            ttl = self._report_ttl(claims)
            if not await self._store(self._valkey.set(key, "1", nx=True, ex=ttl)):
                return False
        except asyncio.CancelledError:
            # Cancelled with the `SET` possibly made: the report is not recorded, so release it
            # (a retry that is then recorded twice is better than one never recorded).
            if key is not None:
                await self._forget(key, None)
            raise
        except Exception as exc:  # noqa: BLE001 - a duplicate row is better than a missing one
            self._miss("tell whether an event was recorded", exc)
            reference, key = None, None
        try:
            await self._audit.record(
                principal=principal,
                action="sign_in" if kind == "sign_in" else "sign_out",
                resolved_query={
                    "session": reference,
                    "basis": None if session is None else session[0],
                    "channel": _channel(claims),
                },
                result_cardinality=1,
            )
        except BaseException as exc:
            # Whatever ended the write releases the report, so a retry records it and is not taken
            # for a repeat; a failure the writer does not wrap (a pool that is closing) is the
            # route's 503 as every audit failure is, with none of the driver's words.
            if key is not None:
                await self._forget(key, None)
            if isinstance(exc, Exception) and not isinstance(exc, AuditWriteError):
                raise AuditWriteError(
                    f"audit write failed for action {kind!r}: {type(exc).__name__}"
                ) from None
            raise
        return True
