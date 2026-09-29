"""`email` — `01_DOMAIN_MODEL.md` §7. Case and unicode domains normalise;
plus-addressing is preserved verbatim in the local part rather than folded
away — whether `user+tag@` and `user@` are the same mailbox is a
mail-provider convention, not a universal rule, and folding it here would
silently merge two addresses that are not always the same one.
"""

from __future__ import annotations

from .errors import NormalisationError


def email(raw: str) -> str:
    stripped = raw.strip()
    if stripped.count("@") != 1:
        raise NormalisationError("email", raw, "must contain exactly one '@'")
    local, _, domain = stripped.partition("@")
    if not local or not domain:
        raise NormalisationError("email", raw, "missing local part or domain")
    try:
        punycode_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise NormalisationError("email", raw, f"domain cannot be encoded: {exc}") from exc
    return f"{local.lower()}@{punycode_domain.lower()}"
