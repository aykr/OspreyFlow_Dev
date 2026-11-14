"""ADR-044 Amendment 1: why a hotlist or watch is stopped, in words for its owner, from the reason
kept beside its binary status. Each sentence names no id (rule 7), and none repeats *Stopped*, which
the badge it is shown beside already says."""

from __future__ import annotations

from principal_auth import (
    ACCESS_OUT_OF_DATE_WORDS,
    OwnerNotHeld,
    OwnerRecordUnavailable,
    PrincipalAccessOutOfDate,
    PrincipalExchangeError,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalRevoked,
)
from schemas.domain import StoppedReason

STOPPED_WHY: dict[str, str] = {
    "revoked": "Its owner can no longer sign in to OspreyFlow.",
    "out_of_date": (
        f"Its owner {ACCESS_OUT_OF_DATE_WORDS}. It is active again at the first load after they "
        "sign in."
    ),
    # On Entra ID: Admin › People does not hold them, and Entra was not asked (ADR-148 Am 16).
    "not_held": "Its owner is not a person Admin › People holds.",
    "refused": "The identity provider refused to act as its owner.",
    # ADR-044 Amendment 2: only the third load in a row stops it (`UNREACHABLE_STOPS_AT`).
    "unreachable": (
        "Its owner's sign-in could not be checked at three loads in a row. It is tried again at the next."
    ),
    "unresolved": "Its owner could not be acted as at the last load.",
    "pattern_gone": "Its saved pattern is no longer its owner's.",
}


#: ADR-044 Amendment 2 (the owner's ruling, 14 November 2026): a load that cannot check its owner's sign-in
#: (`unreachable`) stops a hotlist or a watch only when it is the third in a row; the first two leave it active,
#: matching nothing, and a load that can act as its owner puts the count back to 0.
UNREACHABLE_STOPS_AT = 3


def active_note(unreachable_in_a_row: int) -> str | None:
    """The owner's words beside an active badge while loads have missed its owner's sign-in, `None` with none.
    No id (rule 7)."""
    if unreachable_in_a_row <= 0:
        return None
    if unreachable_in_a_row == 1:
        return (
            "Its owner's sign-in could not be checked at the last load. It stops if that happens at three "
            "loads in a row."
        )
    return (
        "Its owner's sign-in could not be checked at the last two loads. It stops if the next is the third "
        "in a row."
    )


def stopped_why(reason: str | None) -> str | None:
    """The owner's words for a stored reason; `None` for none, and for a reason this release does
    not know (a value written by a later one), never a guess."""
    return STOPPED_WHY.get(reason) if reason else None


def reason_of(error: PrincipalExchangeError) -> StoppedReason:
    """Which reason a refusal to act as an owner is (`resolve_for_owner_detailed`'s raises)."""
    if isinstance(error, PrincipalAccessOutOfDate):
        return "out_of_date"
    if isinstance(error, PrincipalRevoked):
        return "revoked"
    if isinstance(error, OwnerNotHeld):
        return "not_held"
    if isinstance(error, PrincipalExchangeRefused):
        return "refused"
    if isinstance(error, (OwnerRecordUnavailable, PrincipalExchangeUnavailable)):
        return "unreachable"
    return "unresolved"


__all__ = ["STOPPED_WHY", "UNREACHABLE_STOPS_AT", "active_note", "reason_of", "stopped_why"]
