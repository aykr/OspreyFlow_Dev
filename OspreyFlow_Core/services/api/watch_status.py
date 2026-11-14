"""ADR-044 Amendment 1: why a hotlist or watch is stopped, in words for its owner, from the reason
kept beside its binary status. Each sentence names no id (rule 7), and none repeats *Stopped*, which
the badge it is shown beside already says."""

from __future__ import annotations

from principal_auth import (
    PEOPLE_SECTION,
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
    "not_held": f"Its owner is not held in {PEOPLE_SECTION}.",
    "refused": "The identity provider refused to act as its owner.",
    "unreachable": (
        "Its owner's sign-in could not be checked at the last load. It is tried again at the next."
    ),
    "unresolved": "Its owner could not be acted as at the last load.",
    "pattern_gone": "Its saved pattern is no longer its owner's.",
}


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


__all__ = ["STOPPED_WHY", "reason_of", "stopped_why"]
