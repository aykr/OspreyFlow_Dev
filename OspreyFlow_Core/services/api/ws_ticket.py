"""The WebSocket ticket exchange — `06_DECISIONS.md` ADR-050 objection 8, built.

**The gap this closes, in `_authenticate_websocket`'s own words** (`services/api/app.py`): a
browser's native `WebSocket` cannot set an `Authorization` header, so the delta stream took the
same long-lived bearer token as a `?token=` query parameter instead — and a query string is logged.
Measured during the same-origin verification (ADR-050's own objection 8): the full access token
appeared in the workspace's own nginx access log, and `05_DEPLOYMENT.md` §7 puts a TLS-terminating
reverse proxy in front of that, which logs it again. Objection 8 named the fix and declined to
build it in that round; this is that fix.

**The shape.** `POST /v1/ws-ticket`, authenticated the ordinary way (`PrincipalDep`, the same
bearer token every other `/v1` route already requires), mints a random, unguessable, short-lived,
single-use ticket and stores the calling principal's own resolved claims against it in Valkey —
not the bearer token itself, so a leaked ticket cannot be replayed as a bearer credential anywhere
else, and redeeming it needs no second call back to the identity provider. The WebSocket then opens
with `?ticket=...`, never `?token=...`; `_authenticate_websocket` redeems the ticket via Valkey's
`GETDEL` — an atomic get-and-delete, not a separate read then a separate delete, which is what
makes "single-use" true under concurrent connection attempts rather than merely intended. A
30-second TTL is "short-lived": long enough for the browser to receive the mint response and open
the socket, short enough that a ticket sitting in a log line (this is not expected to happen, but
the whole point of a ticket over a bearer token is that it stays true even if it does) is worthless
within the time it would take to notice it.

**Why Valkey, not an in-process cache.** `03_CONDUIT_MIDDLEWARE.md` §1: "stateless... kill one mid-
investigation and the analyst notices nothing." A ticket minted by one Conduit instance must be
redeemable by whichever instance the WebSocket's own connection lands on behind a load balancer —
the same reasoning that already put the delta channel's own pub/sub and the job queue in Valkey
rather than in process memory.
"""

from __future__ import annotations

import secrets

from pydantic import BaseModel
from valkey.asyncio import Valkey

from schemas.domain import Principal

#: `ws-ticket:<opaque>` — namespaced so a Valkey `SCAN`/`KEYS` sweep (an operator's, or a future
#: metrics job's) can tell a ticket apart from every other key class this process writes there.
_KEY_PREFIX = "ws-ticket:"

#: Long enough for the browser to receive the mint response and open the socket; short enough that
#: a ticket which somehow ends up somewhere it should not (a proxy log, a browser history entry) is
#: worthless within the time it would take anyone to notice it. Not configurable: a deployment that
#: needs longer has a slower round trip to fix, not a wider window to open.
TICKET_TTL_SECONDS = 30

#: The single-use token length, `secrets.token_urlsafe`'s own byte count — 256 bits, the same
#: order of magnitude every other opaque, unguessable identifier this codebase mints (client
#: secrets, `generate_client_secret` in `harness/realm.py`) already uses.
_TOKEN_BYTES = 32


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int = TICKET_TTL_SECONDS


async def mint_ws_ticket(valkey: Valkey, principal: Principal) -> str:
    """Stores `principal`'s own already-resolved claims — not the bearer token that produced them
    — against a fresh opaque ticket, and returns the ticket. Redeeming it (`redeem_ws_ticket`)
    needs no further contact with the identity provider, the same way a session cookie would not:
    the expensive verification (signature, audience, issuer) already happened once, in
    `PrincipalResolver.resolve`, to authenticate *this* call."""
    ticket = secrets.token_urlsafe(_TOKEN_BYTES)
    await valkey.set(_KEY_PREFIX + ticket, principal.model_dump_json(), ex=TICKET_TTL_SECONDS)
    return ticket


async def redeem_ws_ticket(valkey: Valkey, ticket: str) -> Principal | None:
    """`GETDEL` — get and delete as one atomic Valkey operation, not a read followed by a separate
    delete. That distinction is the whole of what makes this ticket single-use under concurrency
    rather than merely single-use by convention: two connection attempts racing to redeem the same
    ticket cannot both observe it present, because there is no window between the read and the
    delete for a second `GETDEL` to land in. Returns `None` for a ticket that never existed, already
    expired, or was already redeemed — the caller cannot and does not need to tell those apart."""
    raw = await valkey.getdel(_KEY_PREFIX + ticket)
    if raw is None:
        return None
    return Principal.model_validate_json(raw)
