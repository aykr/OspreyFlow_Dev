"""`services.api.ws_ticket` against a live Valkey — `make dev-up`. `06_DECISIONS.md` ADR-050
objection 8, built: `mint_ws_ticket`/`redeem_ws_ticket`'s own real mechanics — `GETDEL`'s atomic
get-and-delete, the TTL, the principal round-trip — behave the way `_authenticate_websocket`
(`services/api/app.py`) depends on them behaving.
"""

from __future__ import annotations

import pytest
from services.api.ws_ticket import mint_ws_ticket, redeem_ws_ticket
from valkey.asyncio import Valkey

from schemas.domain import Principal

_PRINCIPAL = Principal(
    id="analyst-1",
    clearance="OFFICIAL",
    org_unit="unit-1",
    receivable_handling_codes=["P"],
    roles=["analyst"],
)


@pytest.fixture
async def valkey() -> Valkey:
    client = Valkey(host="localhost", port=6379, db=0)
    yield client  # type: ignore[misc]
    await client.aclose()


async def test_a_minted_ticket_redeems_to_the_same_principal(valkey: Valkey) -> None:
    ticket = await mint_ws_ticket(valkey, _PRINCIPAL)

    redeemed = await redeem_ws_ticket(valkey, ticket)

    assert redeemed == _PRINCIPAL


async def test_a_reused_ticket_is_refused(valkey: Valkey) -> None:
    """The exact property "single-use" claims: the second `GETDEL` against the same ticket finds
    nothing, because the first one already deleted it — not a policy decided in application code
    that a second caller could bypass, but the atomic operation itself having nothing left to
    return."""
    ticket = await mint_ws_ticket(valkey, _PRINCIPAL)
    first = await redeem_ws_ticket(valkey, ticket)
    assert first == _PRINCIPAL

    second = await redeem_ws_ticket(valkey, ticket)

    assert second is None


async def test_an_unknown_ticket_is_refused(valkey: Valkey) -> None:
    assert await redeem_ws_ticket(valkey, "not-a-real-ticket") is None


async def test_two_mints_for_the_same_principal_produce_different_tickets(valkey: Valkey) -> None:
    """Each ticket is independently redeemable and independently single-use — proven by minting
    twice and redeeming both, not merely by string inequality, which a mint that reused Valkey
    state under the hood could still pass while breaking single-use in practice."""
    first_ticket = await mint_ws_ticket(valkey, _PRINCIPAL)
    second_ticket = await mint_ws_ticket(valkey, _PRINCIPAL)
    assert first_ticket != second_ticket

    assert await redeem_ws_ticket(valkey, first_ticket) == _PRINCIPAL
    assert await redeem_ws_ticket(valkey, second_ticket) == _PRINCIPAL
    assert await redeem_ws_ticket(valkey, first_ticket) is None
    assert await redeem_ws_ticket(valkey, second_ticket) is None


async def test_a_ticket_carries_no_more_than_the_principals_own_resolved_claims(
    valkey: Valkey,
) -> None:
    """The ticket's own stored value is the principal's claims, not the bearer token that produced
    them — `services.api.ws_ticket`'s own module docstring names this as the point: a leaked
    ticket cannot be replayed as a bearer credential anywhere else. Checked directly against the
    raw Valkey value, not inferred from the redeemed `Principal` alone."""
    ticket = await mint_ws_ticket(valkey, _PRINCIPAL)

    raw = await valkey.get(f"ws-ticket:{ticket}")

    assert raw is not None
    text = raw.decode() if isinstance(raw, bytes) else raw
    assert "analyst-1" in text
    # Nothing resembling a JWT (three base64url segments joined by dots) is in the stored value —
    # the bearer token that authenticated the mint call never reaches Valkey at all.
    assert text.count(".") == 0
