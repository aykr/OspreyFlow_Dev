"""ADR-044 Amendment 1: why a hotlist or watch is stopped, in words for its owner, from the reason
kept beside its binary status. Each sentence names no id (rule 7): the owner reads their own watch's
reason, and an administrator reads it in Admin."""

from __future__ import annotations

from principal_auth import (
    ACCESS_OUT_OF_DATE_WORDS,
    OwnerRecordUnavailable,
    PrincipalAccessOutOfDate,
    PrincipalExchangeError,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalRevoked,
)
from schemas.domain import StoppedReason

STOPPED_WHY: dict[str, str] = {
    "revoked": "Stopped: its owner can no longer sign in to OspreyFlow.",
    "out_of_date": (
        f"Stopped: its owner {ACCESS_OUT_OF_DATE_WORDS}. It is active again at the first load "
        "after they sign in."
    ),
    "refused": "Stopped: the identity provider refused to act as its owner.",
    "unreachable": (
        "Stopped: its owner's sign-in could not be checked at the last load. It is tried again at "
        "the next."
    ),
    "unresolved": "Stopped: its owner could not be acted as at the last load.",
    "pattern_gone": "Stopped: its saved pattern is no longer its owner's.",
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
    if isinstance(error, PrincipalExchangeRefused):
        return "refused"
    if isinstance(error, (OwnerRecordUnavailable, PrincipalExchangeUnavailable)):
        return "unreachable"
    return "unresolved"


__all__ = ["STOPPED_WHY", "reason_of", "stopped_why"]
